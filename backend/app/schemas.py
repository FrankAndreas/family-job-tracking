from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import Channel, EventType

PIN_PATTERN = r"^\d{4,8}$"


def clean_email(value: str | None) -> str | None:
    """Trimmed, lower-case address; empty means none."""
    if value is None:
        return None
    value = value.strip().lower()
    if not value:
        return None
    if "@" not in value or value.startswith("@") or value.endswith("@"):
        raise ValueError("Ungültige E-Mail-Adresse")
    return value


def clean_name(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise ValueError("Name fehlt")
    return value


class LoginIn(BaseModel):
    name: str
    pin: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    is_admin: bool
    email: str | None
    wants_reminders: bool


class MePatch(BaseModel):
    email: str | None = None
    wants_reminders: bool | None = None

    check_email = field_validator("email")(clean_email)


class PinChange(BaseModel):
    current_pin: str
    new_pin: str = Field(pattern=PIN_PATTERN)


class PinReset(BaseModel):
    pin: str = Field(pattern=PIN_PATTERN)


class UserCreate(BaseModel):
    name: str = Field(max_length=50)
    pin: str = Field(pattern=PIN_PATTERN)
    is_admin: bool = False
    email: str | None = None

    check_name = field_validator("name")(clean_name)
    check_email = field_validator("email")(clean_email)


class UserPatch(BaseModel):
    name: str | None = Field(None, max_length=50)
    is_admin: bool | None = None
    email: str | None = None
    wants_reminders: bool | None = None

    check_name = field_validator("name")(clean_name)
    check_email = field_validator("email")(clean_email)


def clean_company(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise ValueError("Firma fehlt")
    return value


def lower_strip(value: str | None) -> str | None:
    return None if value is None else value.strip().lower()


class ApplicationIn(BaseModel):
    company: str = Field(max_length=200)
    position: str = Field("", max_length=200)
    location: str = Field("", max_length=200)
    contact_name: str = Field("", max_length=200)
    contact_email: str = Field("", max_length=200)
    contact_phone: str = Field("", max_length=50)
    posting_url: str = Field("", max_length=500)
    channel: Channel = Channel.EMAIL
    notes: str = ""

    check_company = field_validator("company")(clean_company)
    check_contact_email = field_validator("contact_email")(lower_strip)


class ApplicationPatch(BaseModel):
    """Fields left out or sent as null stay unchanged."""

    company: str | None = Field(None, max_length=200)
    position: str | None = Field(None, max_length=200)
    location: str | None = Field(None, max_length=200)
    contact_name: str | None = Field(None, max_length=200)
    contact_email: str | None = Field(None, max_length=200)
    contact_phone: str | None = Field(None, max_length=50)
    posting_url: str | None = Field(None, max_length=500)
    channel: Channel | None = None
    notes: str | None = None
    archived: bool | None = None

    check_company = field_validator("company")(clean_company)
    check_contact_email = field_validator("contact_email")(lower_strip)


class EventPatch(BaseModel):
    type: EventType | None = None
    occurred_at: datetime | None = None
    note: str | None = None


class AssignIn(BaseModel):
    application_id: int
    event_type: EventType | None = None


class InboxApplicationIn(BaseModel):
    company: str = Field(max_length=200)
    position: str = Field("", max_length=200)

    check_company = field_validator("company")(clean_company)
