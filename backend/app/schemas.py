from pydantic import BaseModel, ConfigDict, Field, field_validator

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
