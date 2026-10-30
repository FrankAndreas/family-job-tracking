"""The app's people come from the family hub (spec 2026-10-30), as in the budget app and the meal planner.

Everyone the hub lets use the app gets a row here, linked by `hub_id`; the name follows the hub, and a hub parent is
admin here. A row the hub no longer lists is hidden (`is_active` False) with its e-mail and reminders, until the
person comes back or an admin deletes it here. Rows from before the hub are linked by name the first time."""

import threading
import time

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import hub, models

REFRESH_SECONDS = 60
# After the hub failed to answer, the next try waits this long (requests go on with the people kept here)
BACKOFF_SECONDS = 10

_lock = threading.Lock()
# When the last refresh finished (time.monotonic()); None: not yet. Not 0.0: monotonic counts from the machine's start,
# so on a machine up for less than a minute 0.0 would look like a refresh a moment ago
_last: float | None = None
_running = False


def forget() -> None:
    """Refresh at the next chance (tests)."""
    global _last
    _last = None


def refresh(db: Session, token: str, force: bool = False) -> None:
    """Take the app's people from the hub, at most every REFRESH_SECONDS unless forced. Asked with the token of the
    person using the app; when the hub answers no one (that person has no access), nothing changes. One refresh at a
    time: other requests meanwhile go on with the people kept here instead of waiting for a slow hub."""
    global _last, _running
    with _lock:
        if _running or (not force and _last is not None and time.monotonic() - _last < REFRESH_SECONDS):
            return
        _running = True
    try:
        try:
            people = hub.fetch_people(token)
        except hub.HubUnavailable:
            with _lock:
                _last = time.monotonic() - REFRESH_SECONDS + BACKOFF_SECONDS
            raise
        if not people:
            return
        with _lock:
            try:
                _apply(db, people)
            except IntegrityError:
                # Another process got there first: start from what it wrote
                db.rollback()
                _apply(db, people)
            _last = time.monotonic()
    finally:
        with _lock:
            _running = False


def _set_name(row: models.User, name: str) -> None:
    row.name = name


def _apply(db: Session, people: list[hub.HubPerson]) -> None:
    rows = db.query(models.User).all()
    by_hub: dict[int, models.User] = {int(row.hub_id): row for row in rows if row.hub_id is not None}
    # Rows from before the hub are linked by name at the switch only (while no row has a hub id yet): a hub parent to
    # an admin row, anyone else to a non-admin row. Later a new person with an old name would take over that row
    at_switch = not by_hub
    unlinked = {row.name.strip().casefold(): row for row in rows if at_switch}
    matched: dict[int, models.User] = {}
    for person in people:
        row = by_hub.get(person.id)
        if row is None:
            candidate = unlinked.get(person.name.strip().casefold())
            if candidate is not None and bool(candidate.is_admin) == (person.role == "PARENT"):
                row = unlinked.pop(person.name.strip().casefold())
        if row is not None:
            row.hub_id = person.id
            matched[person.id] = row
    listed = {row.id for row in matched.values()}
    hub_name = {row.id: person.name for person in people if (row := matched.get(person.id)) is not None}

    # Names are unique here too: before renaming, every row in the way steps aside (names may be swapped in the hub,
    # or a hidden person's name taken by someone new, who then keeps it)
    wanted = {name.strip().casefold() for name in hub_name.values()} | {
        person.name.strip().casefold() for person in people if person.id not in matched
    }
    for row in rows:
        if row.id in listed and row.name != hub_name[row.id]:
            _set_name(row, f"~{row.id}")
        elif row.id not in listed and row.name.strip().casefold() in wanted:
            _set_name(row, f"{row.name} ({row.id})")
    db.flush()

    for person in people:
        row = matched.get(person.id)
        if row is None:
            row = models.User(hub_id=person.id)
            db.add(row)
        _set_name(row, person.name)
        row.is_admin = person.role == "PARENT"
        # With the hub sharing addresses, the hub's confirmed one is the address here (one place to keep them);
        # without, the app keeps its own
        if person.email_shared:
            row.email = person.email
        row.email_from_hub = person.email_shared
        row.is_active = True
    for row in rows:
        if row.id not in listed:
            row.is_active = False
    db.commit()
