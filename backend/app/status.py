from datetime import datetime, timedelta
from typing import Iterable, Protocol

STATUSES = ("draft", "open", "in_contact", "closed_offer", "closed_rejection", "closed_withdrawn")
ACTIVE_STATUSES = ("open", "in_contact")

_CLOSING = {"offer": "closed_offer", "rejection": "closed_rejection", "withdrawn": "closed_withdrawn"}
_CONTACT = {"reply_received", "mail_received", "call", "interview", "trial"}


class EventLike(Protocol):
    type: str
    occurred_at: datetime


def latest(events: Iterable[EventLike]) -> EventLike | None:
    return max(events, key=lambda e: e.occurred_at, default=None)


def derive_status(events: Iterable[EventLike]) -> str:
    """An application's status from its timeline; it is never stored."""
    events = list(events)
    closing = [e for e in events if e.type in _CLOSING]
    if closing:
        return _CLOSING[max(closing, key=lambda e: e.occurred_at).type]
    if any(e.type in _CONTACT for e in events):
        return "in_contact"
    if any(e.type == "sent" for e in events):
        return "open"
    return "draft"


def days_since(when: datetime, now: datetime) -> int:
    return max(0, (now - when).days)


def is_due(status: str, archived: bool, events: Iterable[EventLike], followup_days: int, now: datetime) -> bool:
    """Whether to follow up: still active, and nothing has happened for more than followup_days."""
    if archived or status not in ACTIVE_STATUSES:
        return False
    last = latest(events)
    return last is not None and now - last.occurred_at > timedelta(days=followup_days)
