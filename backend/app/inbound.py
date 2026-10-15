import logging

from sqlalchemy.orm import Session

from . import files as filestore
from . import mailparse, models
from .settings_store import get_settings
from .timeutil import local_date, utcnow

logger = logging.getLogger(__name__)

UNREADABLE_SUBJECT = "(konnte nicht gelesen werden)"

# Sender domains that say nothing about the company
FREEMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "gmx.ch",
        "gmx.net",
        "gmx.de",
        "bluewin.ch",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "icloud.com",
        "me.com",
        "yahoo.com",
        "proton.me",
        "protonmail.com",
    }
)


def _user_addresses(db: Session) -> set[str]:
    return {u.email for u in db.query(models.User).filter(models.User.email.isnot(None))}


def create_mail_event(
    db: Session, email: models.Email, application: models.Application, event_type: models.EventType | None = None
) -> models.Event:
    """Add the e-mail to the application's timeline: "Mail gesendet" if one of us sent it, else "Mail erhalten"."""
    if event_type is None:
        own = email.from_addr in _user_addresses(db)
        event_type = models.EventType.MAIL_SENT if own else models.EventType.MAIL_RECEIVED
    event = models.Event(
        application_id=application.id,
        occurred_at=email.received_at,
        type=event_type.value,
        note=email.subject,
        email_id=email.id,
    )
    db.add(event)
    return event


def _save(application: models.Application | None, sender: str, day, name: str, content: bytes) -> str:
    if application is not None:
        return filestore.store_for_company(application.company, day, name, content)
    return filestore.store_in_inbox(mailparse.sender_domain(sender), day, name, content)


def _raw_name(subject: str) -> str:
    return f"mail-{filestore.slugify(subject, lower=False, fallback='ohne-betreff')}.eml"


def process(db: Session, raw: bytes, envelope_to: str | None = None) -> models.Email | None:
    """Store an incoming e-mail, in its application's timeline if it carries a +tag, otherwise in the inbox.

    Returns None when the same Message-ID was stored before (the worker delivered it twice)."""
    settings = get_settings(db)
    now = utcnow()
    settings.last_inbound_at = now
    try:
        mail = mailparse.parse(raw, envelope_to)
    except mailparse.MailParseError as exc:
        return _store_unreadable(db, settings, raw, str(exc), now)
    settings.last_inbound_error = None

    if db.query(models.Email).filter_by(message_id=mail.message_id).first() is not None:
        db.commit()
        return None

    known_tags = {tag for (tag,) in db.query(models.Application.mail_tag)}
    tag = mailparse.find_tag(mail.recipients, known_tags)
    application = db.query(models.Application).filter_by(mail_tag=tag).one() if tag else None

    received = mail.date or now
    day = local_date(received)
    email = models.Email(
        message_id=mail.message_id,
        from_addr=mail.from_addr,
        to_addrs=", ".join(mail.to_addrs),
        subject=mail.subject,
        body_text=mail.body_text,
        received_at=received,
        raw_path=_save(application, mail.from_addr, day, _raw_name(mail.subject), raw),
        application_id=application.id if application else None,
    )
    for attachment in mail.attachments:
        email.attachments.append(
            models.Attachment(
                filename=attachment.filename,
                path=_save(application, mail.from_addr, day, attachment.filename, attachment.content),
                content_type=attachment.content_type,
                size=len(attachment.content),
            )
        )
    db.add(email)
    db.flush()
    if application is not None:
        create_mail_event(db, email, application)
    db.commit()
    return email


def _store_unreadable(
    db: Session, settings: models.Settings, raw: bytes, error: str, now
) -> models.Email | None:
    """Keep a mail we could not read as .eml in the inbox, so nothing is lost."""
    settings.last_inbound_error = error
    message_id = mailparse.fallback_message_id(raw)
    if db.query(models.Email).filter_by(message_id=message_id).first() is not None:
        db.commit()
        return None
    email = models.Email(
        message_id=message_id,
        subject=UNREADABLE_SUBJECT,
        received_at=now,
        raw_path=filestore.store_in_inbox("unbekannt", local_date(now), "mail-unlesbar.eml", raw),
        parse_error=error,
    )
    db.add(email)
    db.commit()
    logger.warning("Stored an unreadable e-mail in the inbox: %s", error)
    return email
