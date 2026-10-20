import csv
import io
import os
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session, selectinload

from . import config, models
from . import status as st
from .settings_store import get_settings
from .timeutil import iso, to_local

TABLES = [
    ("users", models.User),
    ("applications", models.Application),
    ("events", models.Event),
    ("emails", models.Email),
    ("attachments", models.Attachment),
    ("suggestions", models.Suggestion),
    ("documents", models.Document),
]
# Login secrets stay out of the export
EXCLUDED_COLUMNS = {"pin_hash", "failed_logins", "locked_until"}

# German labels for the readable files; keep in sync with frontend/src/labels.ts
STATUS_LABELS = {
    "draft": "Entwurf",
    "open": "Offen",
    "in_contact": "In Kontakt",
    "closed_offer": "Zusage",
    "closed_rejection": "Absage",
    "closed_withdrawn": "Zurückgezogen",
}
EVENT_LABELS = {
    "sent": "Bewerbung gesendet",
    "followed_up": "Nachgefragt",
    "reply_received": "Antwort erhalten",
    "mail_sent": "Mail gesendet",
    "mail_received": "Mail erhalten",
    "call": "Telefonat",
    "interview": "Vorstellungsgespräch",
    "trial": "Schnupperlehre/Probetag",
    "offer": "Zusage",
    "rejection": "Absage",
    "withdrawn": "Zurückgezogen",
    "note": "Notiz",
}
CHANNEL_LABELS = {
    "email": "E-Mail",
    "portal": "Portal",
    "post": "Post",
    "in_person": "Persönlich",
    "other": "Andere",
}

SUGGESTION_LABELS = {"open": "Offen", "applied": "Beworben", "declined": "Nicht interessiert"}


def _cell(value):
    if isinstance(value, datetime):
        return iso(value)
    return "" if value is None else value


def _csv(header: list[str], rows) -> str:
    """CSV that Excel opens correctly with a German or Swiss locale: BOM and semicolons."""
    buffer = io.StringIO()
    buffer.write("﻿")
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue()


def _date(dt: datetime | None) -> str:
    return to_local(dt).strftime("%d.%m.%Y") if dt else ""


def _datetime(dt: datetime) -> str:
    return to_local(dt).strftime("%d.%m.%Y %H:%M")


def _yes_no(value: bool) -> str:
    return "Ja" if value else "Nein"


def _overview(applications: list[models.Application], followup_days: int) -> str:
    header = [
        "Firma", "Stelle", "Ort", "Status", "Kanal", "Beworben am", "Letztes Ereignis", "Letzter Kontakt",
        "Nachfassen ab", "Ereignisse", "Kontaktperson", "Kontakt E-Mail", "Kontakt Telefon", "Inserat",
        "Archiviert", "Notizen",
    ]
    rows = []
    for a in applications:
        events = a.events
        status = st.derive_status(events)
        last = st.latest(events)
        sent = min((e.occurred_at for e in events if e.type == "sent"), default=None)
        follow_up = None
        if last and not a.archived and status in st.ACTIVE_STATUSES:
            follow_up = last.occurred_at + timedelta(days=followup_days)
        rows.append([
            a.company, a.position, a.location, STATUS_LABELS.get(status, status),
            CHANNEL_LABELS.get(a.channel, a.channel), _date(sent),
            EVENT_LABELS.get(last.type, last.type) if last else "", _date(last.occurred_at if last else None),
            _date(follow_up), len(events), a.contact_name, a.contact_email, a.contact_phone, a.posting_url,
            _yes_no(a.archived), a.notes,
        ])
    return _csv(header, rows)


def _timeline(applications: list[models.Application]) -> str:
    header = ["Datum", "Firma", "Stelle", "Ereignis", "Notiz", "Erfasst von", "Mail-Betreff", "Anhänge"]
    events = sorted((e for a in applications for e in a.events), key=lambda e: (e.occurred_at, e.id))
    rows = [
        [
            _datetime(e.occurred_at), e.application.company, e.application.position,
            EVENT_LABELS.get(e.type, e.type), e.note, e.creator.name if e.creator else "",
            e.email.subject if e.email else "",
            ", ".join(f.filename for f in e.attachments + (e.email.attachments if e.email else [])),
        ]
        for e in events
    ]
    return _csv(header, rows)


def _suggestions(db: Session) -> str:
    header = [
        "Status", "Firma", "Stelle", "Ort", "Frist", "Link", "Notiz", "Vorgeschlagen von", "Vorgeschlagen am",
        "Entschieden von", "Entschieden am", "Grund",
    ]
    rows = [
        [
            SUGGESTION_LABELS.get(s.status, s.status), s.company, s.position, s.location,
            s.deadline.strftime("%d.%m.%Y") if s.deadline else "", s.url, s.note,
            s.creator.name if s.creator else "", _datetime(s.created_at),
            s.decider.name if s.decider else "", _datetime(s.decided_at) if s.decided_at else "", s.decline_reason,
        ]
        for s in db.query(models.Suggestion).order_by(models.Suggestion.created_at, models.Suggestion.id)
    ]
    return _csv(header, rows)


def _documents(db: Session) -> str:
    header = [
        "Kategorie", "Titel", "Datum", "Datei", "Grösse (KB)", "Im Dossier", "Veraltet", "Hochgeladen von",
        "Hochgeladen am", "Pfad",
    ]
    rank = {category: i for i, category in enumerate(models.CATEGORY_ORDER)}
    documents = sorted(db.query(models.Document), key=lambda d: (rank.get(d.category, 99), d.position, d.id))
    rows = [
        [
            models.CATEGORY_LABELS.get(d.category, d.category), d.title,
            d.issued_on.strftime("%d.%m.%Y") if d.issued_on else "", d.filename, round(d.size / 1024),
            _yes_no(d.in_dossier), _yes_no(d.outdated), d.creator.name if d.creator else "",
            _datetime(d.created_at), f"files/{d.path}",
        ]
        for d in documents
    ]
    return _csv(header, rows)


def build_zip(db: Session) -> Path:
    """Readable overview and timeline, all tables as CSV and the files folder, in a temporary ZIP the caller deletes."""
    fd, name = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    applications = (
        db.query(models.Application)
        .options(selectinload(models.Application.events))
        .order_by(models.Application.company, models.Application.id)
        .all()
    )
    followup_days = get_settings(db).followup_days
    with zipfile.ZipFile(name, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("uebersicht.csv", _overview(applications, followup_days))
        archive.writestr("zeitleiste.csv", _timeline(applications))
        archive.writestr("vorschlaege.csv", _suggestions(db))
        archive.writestr("unterlagen.csv", _documents(db))
        for table, model in TABLES:
            columns = [c.name for c in model.__table__.columns if c.name not in EXCLUDED_COLUMNS]
            rows = ([_cell(getattr(row, column)) for column in columns] for row in db.query(model).order_by(model.id))
            archive.writestr(f"{table}.csv", _csv(columns, rows))
        root = config.files_dir()
        if root.exists():
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    archive.write(path, f"files/{path.relative_to(root).as_posix()}")
    return Path(name)
