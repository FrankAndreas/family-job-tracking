"""The family hub (FrankAndreas/family-hub): who is logged in, and the people of the job tracking app (spec 2026-10-30).

The hub's login is a token (the `hub_session` cookie at home, Cloudflare Access's token from outside). This app passes it
to the hub and never logs it. Session answers are kept for a minute, so a "log out everywhere" in the hub counts here within a minute."""

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

CACHE_SECONDS = 60
TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class HubPerson:
    id: int
    name: str
    role: str
    color: Optional[str]
    language: str
    # Only when the app's tile in the hub shares them (2026-10-30): the confirmed address, or None
    email: Optional[str] = None
    email_shared: bool = False


class HubUnavailable(Exception):
    """The hub didn't answer, or not as expected: nobody is let in."""


# An empty setting counts as unset (docker-compose passes HUB_URL=${HUB_URL:-})
def hub_url() -> str:
    """How this backend reaches the hub, e.g. http://<NAS_IP>:8086."""
    return (os.getenv("HUB_URL") or "http://localhost:8086").rstrip("/")


def public_url() -> str:
    """Where browsers log in, e.g. https://home.local.<domain>."""
    return (os.getenv("HUB_PUBLIC_URL") or hub_url()).rstrip("/")


def app_key() -> str:
    """This app's key in the hub (Einstellungen → Apps)."""
    return os.getenv("HUB_APP_KEY") or "jobs"


def _person(data: dict) -> HubPerson:
    return HubPerson(
        id=int(data["id"]),
        name=str(data["name"]),
        role=str(data["role"]),
        color=data.get("color"),
        language=str(data.get("language") or "de"),
        email=str(data["email"]).strip().casefold() if data.get("email") else None,
        email_shared="email" in data,
    )


@dataclass(frozen=True)
class Login:
    """A request's login. At home the hub's token; from outside (outside_ip: the visitor's Cf-Connecting-Ip) Cloudflare
    Access's token, which the hub checks against Cloudflare's keys and knows the person by their confirmed e-mail
    address. Where the request came from decides which it is, never the token's text (security review 2026-10-31)."""

    token: str
    outside_ip: Optional[str] = None


def _get(path: str, login: Login) -> tuple[int, object]:
    if login.outside_ip is not None:
        # With Cf-Connecting-Ip the hub takes only Cloudflare's token, whatever else came along (family-hub "For apps")
        headers = {"Cf-Access-Jwt-Assertion": login.token, "Cf-Connecting-Ip": login.outside_ip}
    else:
        headers = {"Authorization": f"Bearer {login.token}"}
    request = urllib.request.Request(f"{hub_url()}{path}", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # nosec B310 - the hub's own URL
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, None
    except (urllib.error.URLError, OSError, ValueError) as error:
        # Only the kind of failure: the URL carries no token, but keep messages short and free of request details
        raise HubUnavailable(type(error).__name__) from None


def fetch_session(login: Login) -> tuple[Optional[HubPerson], bool]:
    """The person the login belongs to and whether they may use this app; (None, False) when it's no valid login."""
    status, body = _get(f"/api/session?app={urllib.parse.quote(app_key())}", login)
    if status != 200 or not isinstance(body, dict):
        raise HubUnavailable(f"session answered {status}")
    if not body.get("valid") or not body.get("person"):
        return None, False
    return _person(body["person"]), bool(body.get("access"))


def fetch_people(login: Login) -> list[HubPerson]:
    """Everyone the hub lets use this app; [] when the login's person may not ask (no access or no login)."""
    status, body = _get(f"/api/apps/{urllib.parse.quote(app_key())}/people", login)
    if status in (401, 403):
        return []
    if status != 200 or not isinstance(body, list):
        raise HubUnavailable(f"people answered {status}")
    return [_person(item) for item in body]


# Made-up logins are remembered only while fewer than this many answers are kept: a flood of them can't fill memory
MAX_REMEMBERED = 1000
_cache: dict[str, tuple[float, tuple[Optional[HubPerson], bool]]] = {}
_lock = threading.Lock()


def _key(login: Login) -> str:
    kind = "outside" if login.outside_ip is not None else "home"
    return hashlib.sha256(f"{kind}:{login.token}".encode()).hexdigest()


def session(login: Login) -> tuple[Optional[HubPerson], bool]:
    """fetch_session, kept for CACHE_SECONDS per login (keyed by a hash, never the token itself). Kept: a valid login
    with access, and no hub login at all (a made-up cookie costs no hub call on every request; such a token never
    becomes valid). Not kept: "no access", so someone given access a moment ago gets in at once; and "no login" from
    outside, which may be an address confirmed a moment ago or a hub that couldn't check Cloudflare's token."""
    key = _key(login)
    now = time.monotonic()
    with _lock:
        for stale in [k for k, (at, _) in _cache.items() if now - at >= CACHE_SECONDS]:
            del _cache[stale]
        if key in _cache:
            return _cache[key][1]
    found = fetch_session(login)
    if found[0] is not None:
        keep = found[1]
    else:
        keep = login.outside_ip is None and len(_cache) < MAX_REMEMBERED
    if keep:
        with _lock:
            _cache[key] = (now, found)
    return found


def forget(login: Optional[Login] = None) -> None:
    """Drop the kept answer for one login (logging out), or all of them (tests)."""
    with _lock:
        if login is None:
            _cache.clear()
        else:
            _cache.pop(_key(login), None)
