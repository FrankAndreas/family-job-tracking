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
    pin_hash = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    email = Column(String(200))
    wants_reminders = Column(Boolean, default=False, nullable=False)
    failed_logins = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime)
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
