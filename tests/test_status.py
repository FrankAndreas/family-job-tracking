from datetime import datetime, timedelta
from types import SimpleNamespace

from app import status as st

NOW = datetime(2026, 10, 15, 12, 0)


def ev(event_type, days_ago):
    return SimpleNamespace(type=event_type, occurred_at=NOW - timedelta(days=days_ago))


def test_no_events_is_draft():
    assert st.derive_status([]) == "draft"
    assert st.derive_status([ev("note", 1)]) == "draft"


def test_sent_is_open():
    assert st.derive_status([ev("sent", 3), ev("followed_up", 1)]) == "open"


def test_any_contact_is_in_contact():
    for contact in ("reply_received", "mail_received", "call", "interview", "trial"):
        assert st.derive_status([ev("sent", 5), ev(contact, 2)]) == "in_contact"


def test_latest_closing_event_wins():
    assert st.derive_status([ev("sent", 9), ev("rejection", 5)]) == "closed_rejection"
    assert st.derive_status([ev("rejection", 5), ev("offer", 1)]) == "closed_offer"
    assert st.derive_status([ev("offer", 5), ev("withdrawn", 1), ev("interview", 0)]) == "closed_withdrawn"


def test_due_after_followup_days():
    events = [ev("sent", 11)]
    assert st.is_due("open", False, events, 10, NOW) is True
    assert st.is_due("open", False, [ev("sent", 9)], 10, NOW) is False


def test_not_due_when_archived_closed_or_draft():
    events = [ev("sent", 30)]
    assert st.is_due("open", True, events, 10, NOW) is False
    assert st.is_due("closed_offer", False, events, 10, NOW) is False
    assert st.is_due("draft", False, [], 10, NOW) is False


def test_latest_and_days_since():
    events = [ev("sent", 5), ev("followed_up", 2)]
    assert st.latest(events).type == "followed_up"
    assert st.latest([]) is None
    assert st.days_since(NOW - timedelta(days=2, hours=3), NOW) == 2
