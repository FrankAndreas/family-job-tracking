import enum

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .database import Base
from .timeutil import utcnow


class EventType(str, enum.Enum):
    SENT = "sent"
    FOLLOWED_UP = "followed_up"
    REPLY_RECEIVED = "reply_received"
    MAIL_SENT = "mail_sent"
    MAIL_RECEIVED = "mail_received"
    CALL = "call"
    INTERVIEW = "interview"
    TRIAL = "trial"
    OFFER = "offer"
    REJECTION = "rejection"
    NO_POSITION = "no_position"  # the company offers no apprenticeship (in this trade or year)
    POSITION_FILLED = "position_filled"
    WITHDRAWN = "withdrawn"
    NOTE = "note"


class Channel(str, enum.Enum):
    EMAIL = "email"
    PORTAL = "portal"
    POST = "post"
    IN_PERSON = "in_person"
    OTHER = "other"


class User(Base):
    __tablename__ = "users"
    # Never reuse ids: login tokens name the user by id, so a deleted user's token must not match a new user
    __table_args__ = {"sqlite_autoincrement": True}

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    # A parent in the family hub (spec 2026-10-30): manages the people's e-mail and the settings here
    is_admin = Column(Boolean, default=False, nullable=False)
    email = Column(String(200))
    wants_reminders = Column(Boolean, default=False, nullable=False)
    # The person in the family hub: login, name and admin come from there. None: a row from before the hub, linked by
    # name at the first sync
    hub_id = Column(Integer, unique=True)
    # False: the hub no longer lists the person here; hidden until an admin deletes them
    is_active = Column(Boolean, default=True, nullable=False)
    # The address comes from the hub (its tile for this app shares them): changed there, not here
    email_from_hub = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True)
    company = Column(String(200), nullable=False)
    position = Column(String(200), default="", nullable=False)
    location = Column(String(200), default="", nullable=False)
    contact_name = Column(String(200), default="", nullable=False)
    contact_email = Column(String(200), default="", nullable=False)
    contact_phone = Column(String(50), default="", nullable=False)
    posting_url = Column(String(500), default="", nullable=False)
    channel = Column(String(20), default=Channel.EMAIL.value, nullable=False)
    notes = Column(Text, default="", nullable=False)
    mail_tag = Column(String(8), unique=True, nullable=False)
    archived = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))

    creator = relationship("User")
    events = relationship("Event", back_populates="application", cascade="all, delete-orphan")
    emails = relationship("Email", back_populates="application", cascade="all, delete-orphan")


class Email(Base):
    __tablename__ = "emails"

    id = Column(Integer, primary_key=True)
    message_id = Column(String(500), unique=True, nullable=False)
    from_addr = Column(String(200), default="", nullable=False)
    to_addrs = Column(Text, default="", nullable=False)
    subject = Column(String(500), default="", nullable=False)
    body_text = Column(Text, default="", nullable=False)
    received_at = Column(DateTime, nullable=False)
    raw_path = Column(String(500))
    application_id = Column(Integer, ForeignKey("applications.id", ondelete="CASCADE"))
    parse_error = Column(Text)
    dismissed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    application = relationship("Application", back_populates="emails")
    attachments = relationship("Attachment", back_populates="email", cascade="all, delete-orphan")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    occurred_at = Column(DateTime, nullable=False)
    type = Column(String(20), nullable=False)
    note = Column(Text, default="", nullable=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    email_id = Column(Integer, ForeignKey("emails.id", ondelete="SET NULL"))
    created_at = Column(DateTime, default=utcnow, nullable=False)

    application = relationship("Application", back_populates="events")
    creator = relationship("User")
    email = relationship("Email")
    attachments = relationship("Attachment", back_populates="event", cascade="all, delete-orphan")


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(Integer, primary_key=True)
    # Exactly one of event_id / email_id is set
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"))
    email_id = Column(Integer, ForeignKey("emails.id", ondelete="CASCADE"))
    filename = Column(String(300), nullable=False)
    path = Column(String(500), nullable=False)  # relative to config.files_dir()
    content_type = Column(String(200), default="application/octet-stream", nullable=False)
    size = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    event = relationship("Event", back_populates="attachments")
    email = relationship("Email", back_populates="attachments")


class Settings(Base):
    """App-wide settings and integration bookkeeping; a single row with id 1."""

    __tablename__ = "settings"

    id = Column(Integer, primary_key=True)
    followup_days = Column(Integer, default=10, nullable=False)
    reminder_time = Column(String(5), default="07:00", nullable=False)  # HH:MM local time
    inbound_address = Column(String(200), default="", nullable=False)
    last_reminder_date = Column(String(10))  # YYYY-MM-DD local date of the last finished run
    last_reminder_attempt_at = Column(DateTime)
    last_reminder_sent_at = Column(DateTime)
    last_reminder_error = Column(Text)
    last_inbound_at = Column(DateTime)
    last_inbound_error = Column(Text)


class SuggestionStatus(str, enum.Enum):
    OPEN = "open"
    APPLIED = "applied"
    DECLINED = "declined"


class Suggestion(Base):
    """A link to an open apprenticeship that someone suggests applying for."""

    __tablename__ = "suggestions"

    id = Column(Integer, primary_key=True)
    url = Column(String(500), nullable=False)
    url_key = Column(String(500), nullable=False, index=True)  # suggestions.normalize_url(url)
    company = Column(String(200), default="", nullable=False)
    position = Column(String(200), default="", nullable=False)
    location = Column(String(200), default="", nullable=False)
    deadline = Column(Date)
    note = Column(Text, default="", nullable=False)
    status = Column(String(20), default=SuggestionStatus.OPEN.value, nullable=False)
    decline_reason = Column(Text, default="", nullable=False)
    application_id = Column(Integer, ForeignKey("applications.id", ondelete="SET NULL"))
    source = Column(String(10), default="app", nullable=False)  # "app" or "mail"
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime, default=utcnow, nullable=False)
    decided_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    decided_at = Column(DateTime)

    application = relationship("Application")
    creator = relationship("User", foreign_keys=[created_by])
    decider = relationship("User", foreign_keys=[decided_by])


class DocumentCategory(str, enum.Enum):
    LETTER = "letter"
    CV = "cv"
    REPORT = "report"
    CERTIFICATE = "certificate"
    OTHER = "other"


# Dossier order, folder under files/_unterlagen/ and German label of each category
CATEGORY_ORDER = [c.value for c in DocumentCategory]
CATEGORY_FOLDERS = {
    "letter": "motivationsschreiben",
    "cv": "lebenslauf",
    "report": "zeugnis",
    "certificate": "zertifikat",
    "other": "andere",
}
CATEGORY_LABELS = {
    "letter": "Motivationsschreiben",
    "cv": "Lebenslauf",
    "report": "Zeugnis",
    "certificate": "Zertifikat/Test",
    "other": "Andere",
}


class Document(Base):
    """An application document of the son's (school report, certificate, CV, ...), for the dossier."""

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    category = Column(String(20), nullable=False)
    title = Column(String(200), nullable=False)
    issued_on = Column(Date)
    note = Column(Text, default="", nullable=False)
    outdated = Column(Boolean, default=False, nullable=False)
    in_dossier = Column(Boolean, default=True, nullable=False)
    position = Column(Integer, default=0, nullable=False)  # order inside the category, ascending
    filename = Column(String(300), nullable=False)
    path = Column(String(500), nullable=False)  # relative to config.files_dir()
    content_type = Column(String(200), default="application/octet-stream", nullable=False)
    size = Column(Integer, default=0, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime, default=utcnow, nullable=False)

    creator = relationship("User")
