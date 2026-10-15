from datetime import date, datetime, timezone

from . import config


def utcnow() -> datetime:
    """Current time as naive UTC, the form stored in the database."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_utc(dt: datetime) -> datetime:
    """Naive UTC from an aware datetime, or from a naive one that means local time (TZ)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=config.tz())
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def to_local(dt: datetime) -> datetime:
    """A stored (naive UTC) datetime in the local time zone."""
    return dt.replace(tzinfo=timezone.utc).astimezone(config.tz())


def local_date(dt: datetime) -> date:
    return to_local(dt).date()


def iso(dt: datetime | None) -> str | None:
    """A stored datetime for the API: ISO 8601 in UTC with a trailing Z."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
