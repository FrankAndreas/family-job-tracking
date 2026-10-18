import logging
import re

from sqlalchemy.orm import Session

from . import files as filestore
from . import mailparse, models, suggestions
from . import status as st
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


_FORWARD_SUBJECT = re.compile(r"^\s*(wg|fwd?)\s*:", re.IGNORECASE)
# The header block a mail client puts above a forwarded mail: "Von: Personal <hr@migros.ch>"
_FORWARDED_FROM = re.compile(r"^[\s>*]*(?:von|from)\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_ADDRESS = re.compile(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+")


def is_forward(subject: str) -> bool:
    return bool(_FORWARD_SUBJECT.match(subject))


def forwarded_sender(body: str) -> str | None:
    """The original sender named in a forwarded mail's text, if there is one."""
    for line in _FORWARDED_FROM.finditer(body):
        bracketed = re.search(r"<([^<>@\s]+@[^<>\s]+)>", line.group(1))
        if bracketed:
            return bracketed.group(1).lower()
        plain = _ADDRESS.search(line.group(1))
        if plain:
            return plain.group(0).lower()
    return None


def create_mail_event(
    db: Session, email: models.Email, application: models.Application, event_type: models.EventType | None = None
) -> models.Event:
    """Add the e-mail to the application's timeline.

    One of us sent it: "Bewerbung gesendet" if the application has none yet (the application mail with the app
    in BCC), else "Mail gesendet". From someone else: "Antwort erhalten" if forwarded, else "Mail erhalten"."""
    if event_type is None:
        if email.from_addr in _user_addresses(db):
            first = not any(e.type == models.EventType.SENT.value for e in application.events)
            event_type = models.EventType.SENT if first else models.EventType.MAIL_SENT
        elif is_forward(email.subject):
            event_type = models.EventType.REPLY_RECEIVED
        else:
            event_type = models.EventType.MAIL_RECEIVED
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


def process(
    db: Session, raw: bytes, envelope_to: str | None = None
) -> models.Email | list[models.Suggestion] | None:
    """Store an incoming e-mail in its application's timeline, otherwise in the inbox.

    The application is the one of the +tag, or for an untagged e-mail the only active one its sender's domain fits.
    A mail from a user to the +vorschlag address turns its links into suggestions instead (returned as a list).

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

    if mailparse.find_tag(mail.recipients, {suggestions.SUGGESTION_TAG}):
        sender = db.query(models.User).filter(models.User.email == mail.from_addr).first()
        links = suggestions.extract_links(mail.body_text, *mail.html_links)
        if sender is not None and links:
            created = suggestions.create_from_mail(db, sender, links, mail.subject)
            db.commit()
            return created
        # From someone else, or without a link: keep it like any untagged mail

    # A reply one of us forwarded: file it under the company that wrote it
    sender = mail.from_addr
    event_type = None
    own = _user_addresses(db)
    if sender in own and is_forward(mail.subject):
        original = forwarded_sender(mail.body_text)
        if original is None or original not in own:
            sender = original or sender
            event_type = models.EventType.REPLY_RECEIVED

    known_tags = {tag for (tag,) in db.query(models.Application.mail_tag)}
    tag = mailparse.find_tag(mail.recipients, known_tags)
    if tag:
        application = db.query(models.Application).filter_by(mail_tag=tag).one()
    else:
        application = _auto_match(db, sender)

    received = mail.date or now
    day = local_date(received)
    email = models.Email(
        message_id=mail.message_id,
        from_addr=sender,
        to_addrs=", ".join(mail.to_addrs),
        subject=mail.subject,
        body_text=mail.body_text,
        received_at=received,
        raw_path=_save(application, sender, day, _raw_name(mail.subject), raw),
        application_id=application.id if application else None,
    )
    for attachment in mail.attachments:
        email.attachments.append(
            models.Attachment(
                filename=attachment.filename,
                path=_save(application, sender, day, attachment.filename, attachment.content),
                content_type=attachment.content_type,
                size=len(attachment.content),
            )
        )
    db.add(email)
    db.flush()
    if application is not None:
        create_mail_event(db, email, application, event_type)
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


def assign(
    db: Session, email: models.Email, application: models.Application, event_type: models.EventType | None = None
) -> models.Event:
    """Link an inbox e-mail to an application: move its files into the company folder and add it to the timeline."""
    _move_files(email, lambda path: filestore.move_to_company(path, application.company))
    email.application_id = application.id
    db.flush()
    return create_mail_event(db, email, application, event_type)


def _candidates(db: Session, sender: str) -> list[models.Application]:
    """Active applications the sender's domain belongs to (contact address or earlier e-mails)."""
    domain = mailparse.sender_domain(sender)
    if not domain or domain in FREEMAIL_DOMAINS:
        return []
    pattern = f"%@{domain}"
    candidates = {
        a.id: a
        for a in db.query(models.Application).filter(
            models.Application.archived.is_(False), models.Application.contact_email.like(pattern)
        )
    }
    earlier = db.query(models.Email).filter(
        models.Email.application_id.isnot(None), models.Email.from_addr.like(pattern)
    )
    for other in earlier:
        if not other.application.archived:
            candidates[other.application.id] = other.application
    return list(candidates.values())


def suggest(db: Session, email: models.Email) -> models.Application | None:
    """The candidate with the most recent activity, as a suggestion for an inbox e-mail."""

    def last_activity(application: models.Application):
        last = st.latest(application.events)
        return last.occurred_at if last else application.created_at

    return max(_candidates(db, email.from_addr), key=last_activity, default=None)


def _auto_match(db: Session, sender: str) -> models.Application | None:
    """The application for an untagged e-mail, if only one fits; a user's own mail (e.g. forwarded) never matches."""
    if sender in _user_addresses(db):
        return None
    candidates = _candidates(db, sender)
    return candidates[0] if len(candidates) == 1 else None


def _move_files(email: models.Email, move) -> None:
    """Move the e-mail's .eml and attachments with move(path) -> new path; all of them, or none on an error."""
    holders = ([(email, "raw_path")] if email.raw_path else []) + [(a, "path") for a in email.attachments]
    moved = []
    try:
        for holder, attr in holders:
            old = getattr(holder, attr)
            new = move(old)
            moved.append((holder, attr, old, new))
            setattr(holder, attr, new)
    except Exception:
        for holder, attr, old, new in reversed(moved):
            if new != old:
                filestore.rename(new, old)
            setattr(holder, attr, old)
        raise


def unassign(email: models.Email) -> None:
    """Put an e-mail back into the inbox, e.g. after its timeline event was deleted."""
    domain = mailparse.sender_domain(email.from_addr)
    _move_files(email, lambda path: filestore.move_to_inbox(path, domain))
    email.application_id = None
