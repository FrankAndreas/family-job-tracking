"""Who is logged in: the family hub's login (spec 2026-10-30), as in the budget app and the meal planner.

At home the browser sends the hub's cookie `hub_session` (set for local.<domain>, so every family app gets it); tests
and scripts may send the same token as `Authorization: Bearer`. The hub says whose login it is and whether they may
use the app; the app's people come from the hub too (hub_people.py). No PINs here any more."""

import logging

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from . import database, hub, hub_people, models

logger = logging.getLogger(__name__)

COOKIE = "hub_session"
# With the cookie, a change must carry this header: another site can make the browser send the cookie (sibling apps
# share the site), but not a custom header without this app allowing it
CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "jobs"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
TUNNEL_HEADER = "Cf-Connecting-Ip"
# From outside, Cloudflare Access sends the login it checked (the person's e-mail code) in this header
CLOUDFLARE_HEADER = "Cf-Access-Jwt-Assertion"
# The hub login is in its last week: the page sends the browser once through the hub, which renews it (api.ts)
RENEW_HEADER = "X-Hub-Renew"


def request_token(request: Request) -> tuple[str | None, bool]:
    """The hub token of the request, and whether it came as the cookie."""
    scheme, _, value = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        return value.strip(), False
    cookie = request.cookies.get(COOKIE)
    return (cookie, True) if cookie else (None, False)


def request_login(request: Request) -> tuple[hub.Login | None, bool]:
    """The request's login, and whether a change needs the header. From outside (Cloudflare sets Cf-Connecting-Ip on
    everything through its tunnel) only Cloudflare Access's login counts: a hub login arriving that way can only be a
    stolen home cookie (family-hub README, "For apps"), and Cloudflare's own cookie comes with every request. At home
    the hub's token; a Cloudflare token there is passed on as one and is no login."""
    outside_ip = request.headers.get(TUNNEL_HEADER)
    if outside_ip is not None:
        assertion = request.headers.get(CLOUDFLARE_HEADER)
        return (hub.Login(assertion, outside_ip=outside_ip) if assertion else None), True
    token, from_cookie = request_token(request)
    return (hub.Login(token) if token else None), from_cookie


def api_error(status_code: int, code: str) -> HTTPException:
    """An error the frontend acts on or shows in German: `detail` is a code."""
    return HTTPException(status_code, code)


def _not_logged_in() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "not_logged_in", headers={"WWW-Authenticate": "Bearer"})


def _active(db: Session, hub_id: int) -> models.User | None:
    return db.query(models.User).filter(models.User.hub_id == hub_id, models.User.is_active.is_(True)).first()


def _resolve(request: Request, db: Session) -> tuple[models.User, bool]:
    """The person behind the request's login, and whether the hub login asks to be renewed. Blocking (the hub, the
    database): runs in a worker thread."""
    login, needs_header = request_login(request)
    outside = TUNNEL_HEADER in request.headers
    if login is None:
        raise _not_logged_in()
    if needs_header and request.method not in SAFE_METHODS and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise api_error(status.HTTP_403_FORBIDDEN, "csrf")
    try:
        session = hub.client.session(login)
        person = session.person
        if person is None:
            # Outside, Cloudflare let the address in, but the hub knows no one with it (not confirmed there)
            raise api_error(status.HTTP_403_FORBIDDEN, "no_access") if outside else _not_logged_in()
        if not session.access:
            raise api_error(status.HTTP_403_FORBIDDEN, "no_access")
        hub_people.refresh(db, login)
        user = _active(db, person.id)
        if user is None:
            # Given access a moment ago: the people kept here are older than that
            hub_people.refresh(db, login, force=True)
            user = _active(db, person.id)
        if user is None:
            # Another request of theirs was refreshing at the same moment: wait for it, then look again
            hub_people.wait_for_running(hub.TIMEOUT_SECONDS)
            user = _active(db, person.id)
        # The hub's role may be newer than the row's (refreshed once a minute). Inside the try: a hub that doesn't
        # answer now is a 503, not an error 500 (app integration review 2026-11-07)
        if user is not None and bool(user.is_admin) != (person.role == "PARENT"):
            hub_people.refresh(db, login, force=True)
            db.refresh(user)
    except hub.HubUnavailable as error:
        logger.warning("The family hub can't be reached (%s)", error)
        raise api_error(status.HTTP_503_SERVICE_UNAVAILABLE, "hub_unavailable") from None
    if user is None:
        raise api_error(status.HTTP_403_FORBIDDEN, "no_access")
    return user, session.renew


async def get_current_user(
    request: Request, response: Response, db: Session = Depends(database.get_db)
) -> models.User:
    user, renew = await run_in_threadpool(_resolve, request, db)
    if renew:
        response.headers[RENEW_HEADER] = "1"
    return user


def require_admin(user: models.User = Depends(get_current_user)) -> models.User:
    """An admin: a parent in the family hub."""
    if not user.is_admin:
        raise api_error(status.HTTP_403_FORBIDDEN, "admins_only")
    return user
