from datetime import date, datetime

from . import models
from . import status as st
from .timeutil import iso


def _name(user: models.User | None) -> str | None:
    return user.name if user else None


def attachment_out(a: models.Attachment) -> dict:
    return {"id": a.id, "filename": a.filename, "content_type": a.content_type, "size": a.size, "path": a.path}


def email_out(e: models.Email) -> dict:
    return {
        "id": e.id,
        "message_id": e.message_id,
        "from_addr": e.from_addr,
        "to_addrs": e.to_addrs,
        "subject": e.subject,
        "body_text": e.body_text,
        "received_at": iso(e.received_at),
        "application_id": e.application_id,
        "parse_error": e.parse_error,
        "attachments": [attachment_out(a) for a in e.attachments],
    }


def event_out(ev: models.Event) -> dict:
    return {
        "id": ev.id,
        "occurred_at": iso(ev.occurred_at),
        "type": ev.type,
        "note": ev.note,
        "created_by_name": _name(ev.creator),
        "email": email_out(ev.email) if ev.email else None,
        "attachments": [attachment_out(a) for a in ev.attachments],
    }


def mail_address(inbound_address: str, tag: str) -> str | None:
    """The application's own address, e.g. bewerbungen+a7k2@example.ch, once the inbound address is set."""
    if "@" not in (inbound_address or ""):
        return None
    local, domain = inbound_address.split("@", 1)
    return f"{local}+{tag}@{domain}"


def summary(application: models.Application, followup_days: int, now: datetime) -> dict:
    events = application.events
    status = st.derive_status(events)
    last = st.latest(events)
    return {
        "id": application.id,
        "company": application.company,
        "position": application.position,
        "location": application.location,
        "status": status,
        "archived": application.archived,
        "due": st.is_due(status, application.archived, events, followup_days, now),
        "last_event_type": last.type if last else None,
        "last_event_at": iso(last.occurred_at) if last else None,
        "days_since_last": st.days_since(last.occurred_at, now) if last else None,
        "mail_tag": application.mail_tag,
    }


def detail(application: models.Application, settings: models.Settings, now: datetime) -> dict:
    events = sorted(application.events, key=lambda e: (e.occurred_at, e.id), reverse=True)
    return summary(application, settings.followup_days, now) | {
        "contact_name": application.contact_name,
        "contact_email": application.contact_email,
        "contact_phone": application.contact_phone,
        "posting_url": application.posting_url,
        "channel": application.channel,
        "notes": application.notes,
        "created_at": iso(application.created_at),
        "created_by_name": _name(application.creator),
        "mail_address": mail_address(settings.inbound_address, application.mail_tag),
        "events": [event_out(e) for e in events],
    }


def suggestion_out(s: models.Suggestion, today: date) -> dict:
    application = s.application
    return {
        "id": s.id,
        "url": s.url,
        "company": s.company,
        "position": s.position,
        "location": s.location,
        "deadline": s.deadline.isoformat() if s.deadline else None,
        "note": s.note,
        "status": s.status,
        "decline_reason": s.decline_reason,
        "source": s.source,
        "created_at": iso(s.created_at),
        "created_by_name": _name(s.creator),
        "decided_at": iso(s.decided_at),
        "decided_by_name": _name(s.decider),
        "application": (
            {"id": application.id, "company": application.company, "position": application.position}
            if application
            else None
        ),
        "deadline_passed": bool(s.deadline and s.deadline < today),
    }


def document_out(d: models.Document) -> dict:
    from . import dossier

    return {
        "id": d.id,
        "category": d.category,
        "title": d.title,
        "issued_on": d.issued_on.isoformat() if d.issued_on else None,
        "note": d.note,
        "outdated": d.outdated,
        "in_dossier": d.in_dossier,
        "position": d.position,
        "filename": d.filename,
        "content_type": d.content_type,
        "size": d.size,
        "created_at": iso(d.created_at),
        "created_by_name": _name(d.creator),
        "dossier_ok": dossier.kind(d.content_type, d.filename) is not None,
    }
