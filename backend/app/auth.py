"""Who is logged in: the family hub's login (spec 2026-10-30), as in the budget app and the meal planner.

At home the browser sends the hub's cookie `hub_session` (set for local.<domain>, so every family app gets it); tests
and scripts may send the same token as `Authorization: Bearer`. The hub says whose login it is and whether they may
use the app; the app's people come from the hub too (hub_people.py). No PINs here any more."""

import logging

from fastapi import Depends, HTTPException, Request, status
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


def request_token(request: Request) -> tuple[str | None, bool]:
    """The hub token of the request, and whether it came as the cookie."""
    scheme, _, value = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        return value.strip(), False
    cookie = request.cookies.get(COOKIE)
    return (cookie, True) if cookie else (None, False)


def api_error(status_code: int, code: str) -> HTTPException:
    """An error the frontend acts on or shows in German: `detail` is a code."""
    return HTTPException(status_code, code)


def _not_logged_in() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "not_logged_in", headers={"WWW-Authenticate": "Bearer"})


def _active(db: Session, hub_id: int) -> models.User | None:
    return db.query(models.User).filter(models.User.hub_id == hub_id, models.User.is_active.is_(True)).first()


def _resolve(request: Request, db: Session) -> models.User:
    """The person behind the request's login. Blocking (the hub, the database): runs in a worker thread."""
    # Home only (2026-10-30): Cloudflare sets this on everything through its tunnel (only the e-mail worker comes that
    # way, with its own secret); a hub login arriving from outside can only be a stolen home cookie (family-hub README,
    # "For apps")
    if TUNNEL_HEADER in request.headers:
        raise _not_logged_in()
    token, from_cookie = request_token(request)
    if not token:
        raise _not_logged_in()
    if from_cookie and request.method not in SAFE_METHODS and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise api_error(status.HTTP_403_FORBIDDEN, "csrf")
    try:
        person, access = hub.session(token)
        if person is None:
            raise _not_logged_in()
        if not access:
            raise api_error(status.HTTP_403_FORBIDDEN, "no_access")
        hub_people.refresh(db, token)
        user = _active(db, person.id)
        if user is None:
            # Given access a moment ago: the people kept here are older than that
            hub_people.refresh(db, token, force=True)
            user = _active(db, person.id)
    except hub.HubUnavailable as error:
        logger.warning("The family hub can't be reached (%s)", error)
        raise api_error(status.HTTP_503_SERVICE_UNAVAILABLE, "hub_unavailable") from None
    if user is None:
        raise api_error(status.HTTP_403_FORBIDDEN, "no_access")
    # The hub's role may be newer than the row's (refreshed once a minute)
    if bool(user.is_admin) != (person.role == "PARENT"):
        hub_people.refresh(db, token, force=True)
        db.refresh(user)
    return user


async def get_current_user(request: Request, db: Session = Depends(database.get_db)) -> models.User:
    return await run_in_threadpool(_resolve, request, db)


def require_admin(user: models.User = Depends(get_current_user)) -> models.User:
    """An admin: a parent in the family hub."""
    if not user.is_admin:
        raise api_error(status.HTTP_403_FORBIDDEN, "admins_only")
    return user
