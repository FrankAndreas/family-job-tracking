# Family Job Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A self-hosted web app on a Synology NAS that tracks job applications with a timeline of every communication. E-mails reach the timeline through a Cloudflare Email Worker, and a daily reminder digest goes out via Resend.

**Architecture:** FastAPI + SQLite backend and a React SPA served by nginx, run as two Docker containers. The setup mirrors the peer project `/home/andreas/work/family-budget-dashboard`. The database and attachments live in the bind-mounted `data/` folder. A separate Cloudflare Worker posts incoming raw e-mails to `/api/inbound`. An in-process background task sends reminder e-mails through the Resend HTTP API when it is configured.

**Tech Stack:** Python 3.14, FastAPI 0.143, SQLAlchemy 2.1, pydantic 2.14, bcrypt, python-jose, pytest; React 19, Vite 8, TypeScript 5.9, Tailwind 4, axios, react-router 7; Cloudflare Workers (TypeScript, wrangler, vitest); Docker Compose, GitHub Actions, GHCR.

**Spec:** `docs/superpowers/specs/2026-10-15-family-job-tracking-design.md`

## Global Constraints

- Backend pins: `fastapi==0.143.0`, `uvicorn==0.54.0`, `sqlalchemy==2.1.4`, `pydantic==2.14.1`, `python-multipart==0.0.32`, `bcrypt==5.0.0`, `python-jose[cryptography]==3.5.0`, `tzdata==2025.2` (the slim image has no zoneinfo database).
- Frontend: same versions as the peer's `frontend/package.json` (React 19.3, Vite 8.3, Tailwind 4, TypeScript ~5.9.3), Node 26 in Docker/CI.
- The UI text is German. Code, comments, docs and commit messages are English. API error `detail` messages are German because the UI shows them.
- All API routes are under `/api`, except `/health`. Errors are `{"detail": "..."}`.
- Datetimes are stored as naive UTC. The API returns ISO 8601 with `Z` (`timeutil.iso`). A naive input is local time in `TZ` (default `Europe/Zurich`).
- `DATA_DIR` (default `./data`) holds `jobs.db` and `files/`. `DATABASE_URL` defaults to `sqlite:///./data/jobs.db`.
- Max size is 25 MB per uploaded file and per inbound e-mail. nginx uses `client_max_body_size 30m`.
- PINs are 4–8 digits. 5 wrong PINs lock the user for 15 minutes. JWTs are valid for 30 days.
- Resend and the inbound worker are optional. A missing or broken integration never stops the app from starting.
- Defaults: NAS port `8082`; containers `jobs-backend` and `jobs-frontend`; images `ghcr.io/frankandreas/family-job-tracking/backend` and `.../frontend`.
- Commit messages are conventional (`feat(backend): ...`) and end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **BCC'd e-mail.** The `+tag` address appears only in the SMTP envelope (`X-Envelope-To`), not in any header. The mail must still be assigned to the application. Test: Task 6 `test_bcc_uses_envelope_recipient`.
2. **Non-ASCII names.** An attachment named `Lebenslauf Müller.pdf` (RFC 2231) and the subject `Einladung zum Gespräch` must come out decoded and readable, and the path must be slugged. Tests: Task 5 `test_decodes_umlauts_in_subject_and_filename`, Task 6 `test_tagged_mail_creates_event_and_files`.
3. **Unusable company names.** A company name that slugifies to nothing (`!!!`, `株式会社`) or one that is very long must still produce a valid folder: fallback `firma`, at most 40 characters. Test: Task 3 `test_slugify_fallback_and_length`.
4. **Missing or garbage `Date` header.** The mail must not be rejected. `received_at` becomes the time of arrival. Tests: Task 5 `test_missing_or_invalid_date_is_none`, Task 6 `test_mail_without_date_uses_arrival_time`.
5. **Deleting a user who logged events.** Their applications and events remain, and "erfasst von" becomes empty. Test: Task 4 `test_deleting_user_keeps_their_events`.

---

## File Structure

```
backend/
  requirements.txt
  Dockerfile
  app/
    __init__.py
    config.py           env access: env(), data_dir(), files_dir(), tz()
    timeutil.py         utcnow(), to_utc(), to_local(), local_date(), iso()
    database.py         engine (SQLite, foreign keys on), SessionLocal, Base, get_db
    models.py           User, Application, Event, Email, Attachment, Settings; EventType, Channel
    settings_store.py   get_settings(db) -> the single Settings row
    auth.py             PIN hashing, JWT, authenticate() with lockout, get_current_user, require_admin
    seed.py             seed_admin(db)
    schemas.py          pydantic request bodies
    status.py           derive_status(), latest(), is_due(), days_since(), STATUSES
    files.py            slugify(), safe_filename(), store_for_company(), store_in_inbox(), move_to_company(), absolute(), delete()
    views.py            dict serializers: summary(), detail(), event_out(), email_out(), attachment_out()
    mailparse.py        parse(raw, envelope_to) -> ParsedMail, find_tag(), sender_domain(), MailParseError
    inbound.py          process(db, raw, envelope_to), assign(), suggest(), create_mail_event()
    reminders.py        build_digest(), render(), run_once(), send_test(), next_run(), loop()
    integrations.py     status(db, now)
    export.py           build_zip(db) -> Path
    users_api.py        /token, /users/public, /me, /users
    applications_api.py /applications, /events, /attachments, /dashboard
    inbox_api.py        /inbound, /inbox, /emails
    settings_api.py     /settings, /integrations, /export
    main.py             app, routers, startup seeding, reminder task lifespan
tests/
  requirements.txt, conftest.py, helpers.py, mails.py
  test_health.py, test_auth.py, test_users.py, test_status.py, test_files.py,
  test_applications.py, test_mailparse.py, test_inbound.py, test_inbox.py,
  test_reminders.py, test_settings.py
frontend/
  package.json, vite.config.ts, index.html, nginx.conf, Dockerfile, eslint/ts/postcss/tailwind configs
  src/
    main.tsx, App.tsx, index.css
    api.ts, types.ts, labels.ts, ui.ts
    AuthContext.tsx, ToastContext.tsx
    components/ Layout.tsx, PinInput.tsx, StatusBadge.tsx, ApplicationForm.tsx, EventForm.tsx, Timeline.tsx
    components/settings/ MyAccount.tsx, AppSettingsForm.tsx, UserManager.tsx, IntegrationCards.tsx
    pages/ Login.tsx, Overview.tsx, ApplicationPage.tsx, Inbox.tsx, SettingsPage.tsx
cloudflare/email-worker/
  package.json, tsconfig.json, wrangler.toml, src/index.ts, test/index.test.ts
docker-compose.yml, .env.example, .deploy.env.example, pytest.ini, data/.gitkeep
scripts/ deploy-nas.sh, nas-update.sh
.github/workflows/ pr-checks.yml, ci-cd.yml
README.md, README_DOCKER.md
```

The peer project referenced in some steps is at `/home/andreas/work/family-budget-dashboard` (shortened to `$PEER` below):

```bash
PEER=/home/andreas/work/family-budget-dashboard
```

---

### Task 1: Backend foundation (config, time, database, models, health)

**Files:**
- Create: `backend/requirements.txt`, `backend/app/__init__.py`, `backend/app/config.py`, `backend/app/timeutil.py`, `backend/app/database.py`, `backend/app/models.py`, `backend/app/settings_store.py`, `backend/app/main.py`
- Create: `pytest.ini`, `tests/requirements.txt`, `tests/conftest.py`, `tests/test_health.py`, `data/.gitkeep`

**Interfaces:**
- Produces:
  - `config.env(name: str, default: str = "") -> str`, `config.data_dir() -> Path`, `config.files_dir() -> Path`, `config.tz() -> ZoneInfo`. All read the environment at call time.
  - `timeutil.utcnow() -> datetime` (naive UTC), `to_utc(dt) -> datetime` (naive UTC; a naive input means local `TZ`), `to_local(dt) -> datetime` (aware, `TZ`), `local_date(dt) -> date`, `iso(dt | None) -> str | None` (`...Z`).
  - `database.engine`, `database.SessionLocal`, `database.Base`, `database.get_db()`.
  - Models `User`, `Application`, `Event`, `Email`, `Attachment`, `Settings` (columns below), enums `EventType`, `Channel` (str enums; columns store `.value`).
  - `settings_store.get_settings(db) -> models.Settings` creates row id 1 on first use.
  - Test fixtures `client` (TestClient) and `db` (Session). Every test gets a fresh database and its own `DATA_DIR` (`tmp_path`).

- [ ] **Step 1: Create the virtualenv, requirements and test config**

`backend/requirements.txt`:
```
fastapi==0.143.0
uvicorn==0.54.0
sqlalchemy==2.1.4
pydantic==2.14.1
python-multipart==0.0.32
bcrypt==5.0.0
python-jose[cryptography]==3.5.0
# Time zone database for zoneinfo; the slim Docker image has none
tzdata==2025.2
```

`tests/requirements.txt`:
```
pytest>=7.4.0
# FastAPI TestClient
httpx>=0.25,<0.28
```

`pytest.ini`:
```ini
[pytest]
testpaths = tests
addopts = -v --tb=short
```

```bash
mkdir -p backend/app tests data && touch backend/app/__init__.py data/.gitkeep
python3 -m venv venv
venv/bin/pip install -r backend/requirements.txt -r tests/requirements.txt
```

- [ ] **Step 2: Write the failing tests**

`tests/conftest.py`:
```python
import os
import sys
import tempfile
from pathlib import Path

# Point the app at a throwaway database and data folder before it is imported, so tests never touch ./data
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["DATA_DIR"] = _tmp
os.environ["SECRET_KEY"] = "test-secret"
os.environ["INITIAL_ADMIN_PIN"] = "1234"
os.environ["TZ"] = "Europe/Zurich"
# Optional integrations start switched off; tests that need them set the variables with monkeypatch
for _name in ("INBOUND_SECRET", "RESEND_API_KEY", "MAIL_FROM", "APP_URL"):
    os.environ.pop(_name, None)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import database, models  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Every test starts with an empty database and its own files folder."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    models.Base.metadata.drop_all(bind=database.engine)
    models.Base.metadata.create_all(bind=database.engine)
    yield


@pytest.fixture
def db():
    with database.SessionLocal() as session:
        yield session


@pytest.fixture
def client():
    return TestClient(app)
```

`tests/test_health.py`:
```python
from datetime import datetime

from app import models
from app.settings_store import get_settings
from app.timeutil import iso, to_utc


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_settings_row_is_created_once(db):
    first = get_settings(db)
    second = get_settings(db)
    assert first.id == second.id == 1
    assert first.followup_days == 10
    assert first.reminder_time == "07:00"
    assert db.query(models.Settings).count() == 1


def test_naive_input_is_local_time():
    # 10:00 in Zurich (summer time, UTC+2) is 08:00 UTC
    assert iso(to_utc(datetime(2026, 7, 1, 10, 0))) == "2026-07-01T08:00:00Z"


def test_deleting_a_user_nulls_created_by(db):
    user = models.User(name="Sohn", pin_hash="x")
    db.add(user)
    db.flush()
    application = models.Application(company="Migros", mail_tag="abcd", created_by=user.id)
    db.add(application)
    db.commit()
    db.delete(user)
    db.commit()
    db.refresh(application)
    assert application.created_by is None
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_health.py`
Expected: ERROR at collection, `ModuleNotFoundError: No module named 'app.database'` (or `app.main`).

- [ ] **Step 4: Implement config, time helpers and database**

`backend/app/config.py`:
```python
import os
from pathlib import Path
from zoneinfo import ZoneInfo


def env(name: str, default: str = "") -> str:
    """An environment variable, stripped; read on every call so tests can change it."""
    return (os.getenv(name) or default).strip()


def data_dir() -> Path:
    return Path(env("DATA_DIR", "./data"))


def files_dir() -> Path:
    """Attachments and raw e-mails, below the data folder."""
    return data_dir() / "files"


def tz() -> ZoneInfo:
    return ZoneInfo(env("TZ", "Europe/Zurich"))
```

`backend/app/timeutil.py`:
```python
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
```

`backend/app/database.py`:
```python
import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/jobs.db")

# check_same_thread is needed for SQLite with FastAPI's thread pool
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _enable_foreign_keys(dbapi_connection, _record):
    # SQLite ignores foreign keys (and ON DELETE SET NULL / CASCADE) unless asked on every connection
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 5: Implement models, settings store and main**

`backend/app/models.py`:
```python
import enum

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
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
```

`backend/app/settings_store.py`:
```python
from sqlalchemy.orm import Session

from . import models


def get_settings(db: Session) -> models.Settings:
    """The single settings row, created with defaults on first use."""
    settings = db.get(models.Settings, 1)
    if settings is None:
        settings = models.Settings(id=1)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings
```

`backend/app/main.py`:
```python
import logging

from fastapi import FastAPI

from . import database, models

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Family Job Tracking API", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_health.py`
Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add backend pytest.ini tests data/.gitkeep
git commit -m "feat(backend): database models, time helpers and health endpoint

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: PIN login, lockout and user management

**Files:**
- Create: `backend/app/auth.py`, `backend/app/seed.py`, `backend/app/schemas.py`, `backend/app/users_api.py`, `tests/helpers.py`, `tests/test_auth.py`, `tests/test_users.py`
- Modify: `backend/app/main.py`, `tests/conftest.py`

**Interfaces:**
- Consumes: `models.User`, `database.get_db`, `config.env`, `timeutil.utcnow`.
- Produces:
  - `auth.get_pin_hash(pin) -> str`, `auth.verify_pin(pin, hash) -> bool`, `auth.create_access_token(user_id: int) -> str`, `auth.authenticate(db, name, pin) -> models.User` (raises 401/429).
  - FastAPI dependencies `auth.get_current_user -> models.User` and `auth.require_admin -> models.User`.
  - `seed.seed_admin(db) -> str | None` returns the created PIN.
  - `schemas.clean_email(value) -> str | None`.
  - Endpoints: `GET /api/users/public`, `POST /api/token` (`{name, pin}` → `{access_token, token_type}`), `GET/PATCH /api/me`, `POST /api/me/pin`, `GET/POST /api/users`, `PATCH/DELETE /api/users/{id}`, `POST /api/users/{id}/pin`.
  - The user JSON is `{id, name, is_admin, email, wants_reminders}`.
  - Test helpers `helpers.ADMIN = "Admin"`, `helpers.ADMIN_PIN = "1234"`, `helpers.login(client, name=ADMIN, pin=ADMIN_PIN) -> dict` (auth headers), `helpers.create_user(client, headers, name, pin="5678", **extra) -> dict`; fixture `admin_headers`.

- [ ] **Step 1: Write the failing tests**

`tests/helpers.py`:
```python
ADMIN = "Admin"
ADMIN_PIN = "1234"


def login(client, name=ADMIN, pin=ADMIN_PIN) -> dict:
    response = client.post("/api/token", json={"name": name, "pin": pin})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_user(client, headers, name, pin="5678", **extra) -> dict:
    response = client.post("/api/users", json={"name": name, "pin": pin, **extra}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()
```

Add to `tests/conftest.py` the import and fixture changes. Replace the `fresh_db` fixture and add `admin_headers`:
```python
from app.seed import seed_admin  # noqa: E402
from helpers import login  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Every test starts like a fresh install: user "Admin" with PIN 1234, and its own files folder."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    models.Base.metadata.drop_all(bind=database.engine)
    models.Base.metadata.create_all(bind=database.engine)
    with database.SessionLocal() as session:
        seed_admin(session)
    yield


@pytest.fixture
def admin_headers(client):
    return login(client)
```

`tests/test_auth.py`:
```python
from datetime import timedelta

from app import models
from app.timeutil import utcnow
from helpers import ADMIN, ADMIN_PIN, login


def test_public_users_lists_admin(client):
    response = client.get("/api/users/public")
    assert response.status_code == 200
    assert [u["name"] for u in response.json()] == [ADMIN]


def test_login_and_me(client):
    headers = login(client)
    me = client.get("/api/me", headers=headers).json()
    assert me["name"] == ADMIN
    assert me["is_admin"] is True
    assert me["email"] is None


def test_wrong_pin_and_unknown_user_are_401(client):
    assert client.post("/api/token", json={"name": ADMIN, "pin": "0000"}).status_code == 401
    assert client.post("/api/token", json={"name": "Niemand", "pin": ADMIN_PIN}).status_code == 401


def test_requests_without_valid_token_are_401(client):
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers={"Authorization": "Bearer kaputt"}).status_code == 401


def test_five_wrong_pins_lock_the_user(client, db):
    for _ in range(5):
        assert client.post("/api/token", json={"name": ADMIN, "pin": "0000"}).status_code == 401
    locked = client.post("/api/token", json={"name": ADMIN, "pin": ADMIN_PIN})
    assert locked.status_code == 429
    assert "Minuten" in locked.json()["detail"]

    # Once the lock has expired the right PIN works again
    user = db.query(models.User).filter_by(name=ADMIN).one()
    user.locked_until = utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.post("/api/token", json={"name": ADMIN, "pin": ADMIN_PIN}).status_code == 200


def test_successful_login_resets_failed_count(client, db):
    for _ in range(4):
        client.post("/api/token", json={"name": ADMIN, "pin": "0000"})
    login(client)
    assert db.query(models.User).filter_by(name=ADMIN).one().failed_logins == 0


def test_change_own_pin(client, admin_headers):
    wrong = client.post("/api/me/pin", json={"current_pin": "9999", "new_pin": "4321"}, headers=admin_headers)
    assert wrong.status_code == 400
    too_short = client.post("/api/me/pin", json={"current_pin": ADMIN_PIN, "new_pin": "12"}, headers=admin_headers)
    assert too_short.status_code == 422
    ok = client.post("/api/me/pin", json={"current_pin": ADMIN_PIN, "new_pin": "43210"}, headers=admin_headers)
    assert ok.status_code == 204
    login(client, pin="43210")


def test_update_own_email_and_reminders(client, admin_headers):
    response = client.patch(
        "/api/me", json={"email": " Papa@Example.CH ", "wants_reminders": True}, headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["email"] == "papa@example.ch"
    assert response.json()["wants_reminders"] is True
    cleared = client.patch("/api/me", json={"email": ""}, headers=admin_headers).json()
    assert cleared["email"] is None
    assert client.patch("/api/me", json={"email": "keine-adresse"}, headers=admin_headers).status_code == 422
```

`tests/test_users.py`:
```python
from helpers import create_user, login


def test_admin_creates_user_who_can_log_in(client, admin_headers):
    user = create_user(client, admin_headers, "Sohn", pin="5678", email="sohn@example.ch")
    assert user["is_admin"] is False
    assert user["email"] == "sohn@example.ch"
    headers = login(client, "Sohn", "5678")
    assert client.get("/api/me", headers=headers).json()["name"] == "Sohn"
    names = [u["name"] for u in client.get("/api/users", headers=admin_headers).json()]
    assert names == ["Admin", "Sohn"]


def test_non_admin_cannot_manage_users(client, admin_headers):
    create_user(client, admin_headers, "Sohn")
    headers = login(client, "Sohn", "5678")
    assert client.get("/api/users", headers=headers).status_code == 403
    assert client.post("/api/users", json={"name": "X", "pin": "1111"}, headers=headers).status_code == 403


def test_duplicate_name_is_409(client, admin_headers):
    create_user(client, admin_headers, "Sohn")
    response = client.post("/api/users", json={"name": "Sohn", "pin": "1111"}, headers=admin_headers)
    assert response.status_code == 409


def test_admin_renames_resets_pin_and_promotes(client, admin_headers):
    user = create_user(client, admin_headers, "Sohn")
    renamed = client.patch(f"/api/users/{user['id']}", json={"name": "Luca", "is_admin": True}, headers=admin_headers)
    assert renamed.json()["name"] == "Luca"
    assert renamed.json()["is_admin"] is True
    assert client.post(f"/api/users/{user['id']}/pin", json={"pin": "2468"}, headers=admin_headers).status_code == 204
    login(client, "Luca", "2468")


def test_last_admin_cannot_be_demoted_and_self_cannot_be_deleted(client, admin_headers):
    me = client.get("/api/me", headers=admin_headers).json()
    demote = client.patch(f"/api/users/{me['id']}", json={"is_admin": False}, headers=admin_headers)
    assert demote.status_code == 400
    assert client.delete(f"/api/users/{me['id']}", headers=admin_headers).status_code == 400


def test_admin_deletes_user(client, admin_headers):
    user = create_user(client, admin_headers, "Sohn")
    assert client.delete(f"/api/users/{user['id']}", headers=admin_headers).status_code == 204
    assert [u["name"] for u in client.get("/api/users/public").json()] == ["Admin"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_auth.py tests/test_users.py`
Expected: ERROR at collection, `ModuleNotFoundError: No module named 'app.seed'`.

- [ ] **Step 3: Implement auth, seed and schemas**

`backend/app/auth.py`:
```python
import logging
import math
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from . import config, database, models
from .timeutil import utcnow

logger = logging.getLogger(__name__)

# Signs the login tokens. Without SECRET_KEY a random key is used, which logs everyone out on every restart.
SECRET_KEY = config.env("SECRET_KEY") or secrets.token_urlsafe(32)
if not config.env("SECRET_KEY"):
    logger.warning("SECRET_KEY is not set; using a random key, so logins won't survive a restart")
ALGORITHM = "HS256"
TOKEN_LIFETIME = timedelta(days=30)
# A 4-digit PIN is guessable, so lock the user after a few wrong tries
MAX_FAILED_LOGINS = 5
LOCK_DURATION = timedelta(minutes=15)

_bearer = HTTPBearer(auto_error=False)


def get_pin_hash(pin: str) -> str:
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()


def verify_pin(pin: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pin.encode(), hashed.encode())
    except ValueError:
        # Not a valid bcrypt hash: treat it like a wrong PIN instead of a server error
        return False


def create_access_token(user_id: int) -> str:
    expires = datetime.now(timezone.utc) + TOKEN_LIFETIME
    return jwt.encode({"sub": str(user_id), "exp": expires}, SECRET_KEY, algorithm=ALGORITHM)


def authenticate(db: Session, name: str, pin: str) -> models.User:
    """The user with this name and PIN; counts wrong PINs and locks the user after too many."""
    wrong = HTTPException(status.HTTP_401_UNAUTHORIZED, "Falscher Name oder PIN")
    user = db.query(models.User).filter(models.User.name == name).first()
    if user is None:
        raise wrong
    now = utcnow()
    if user.locked_until and user.locked_until > now:
        minutes = math.ceil((user.locked_until - now).total_seconds() / 60)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Zu viele Fehlversuche. Bitte in {minutes} Minuten erneut versuchen.",
        )
    if not verify_pin(pin, user.pin_hash):
        user.failed_logins += 1
        if user.failed_logins >= MAX_FAILED_LOGINS:
            user.failed_logins = 0
            user.locked_until = now + LOCK_DURATION
        db.commit()
        raise wrong
    user.failed_logins = 0
    user.locked_until = None
    db.commit()
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(database.get_db),
) -> models.User:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Nicht angemeldet", headers={"WWW-Authenticate": "Bearer"}
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise unauthorized
    user = db.get(models.User, user_id)
    if user is None:
        raise unauthorized
    return user


def require_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur für Admins")
    return user
```

`backend/app/seed.py`:
```python
import logging
import re
import secrets

from sqlalchemy.orm import Session

from . import auth, config, models

logger = logging.getLogger(__name__)


def seed_admin(db: Session) -> str | None:
    """Create the admin "Admin" on an empty database; returns its PIN, or None if users exist."""
    if db.query(models.User).first() is not None:
        return None
    pin = config.env("INITIAL_ADMIN_PIN")
    if not re.fullmatch(r"\d{4,8}", pin):
        if pin:
            logger.warning("INITIAL_ADMIN_PIN must be 4-8 digits; using a random PIN instead")
        pin = f"{secrets.randbelow(10_000):04d}"
    db.add(models.User(name="Admin", pin_hash=auth.get_pin_hash(pin), is_admin=True))
    db.commit()
    return pin
```

`backend/app/schemas.py`:
```python
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
```

- [ ] **Step 4: Implement the users router and wire it up**

`backend/app/users_api.py`:
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from . import auth, models, schemas
from .database import get_db

router = APIRouter(tags=["users"])


def _get_user(db: Session, user_id: int) -> models.User:
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(404, "Benutzer nicht gefunden")
    return user


def _admin_count(db: Session) -> int:
    return db.query(models.User).filter(models.User.is_admin.is_(True)).count()


def _name_taken(db: Session, name: str, except_id: int | None = None) -> bool:
    query = db.query(models.User).filter(models.User.name == name)
    if except_id is not None:
        query = query.filter(models.User.id != except_id)
    return query.first() is not None


@router.get("/users/public", response_model=list[schemas.UserPublic])
def public_users(db: Session = Depends(get_db)):
    """Names for the login screen."""
    return db.query(models.User).order_by(models.User.name).all()


@router.post("/token", response_model=schemas.TokenOut)
def login(body: schemas.LoginIn, db: Session = Depends(get_db)):
    user = auth.authenticate(db, body.name, body.pin)
    return {"access_token": auth.create_access_token(user.id)}


@router.get("/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(auth.get_current_user)):
    return user


@router.patch("/me", response_model=schemas.UserOut)
def update_me(
    body: schemas.MePatch, user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)
):
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user


@router.post("/me/pin", status_code=204)
def change_pin(
    body: schemas.PinChange, user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)
):
    if not auth.verify_pin(body.current_pin, user.pin_hash):
        raise HTTPException(400, "Aktueller PIN ist falsch")
    user.pin_hash = auth.get_pin_hash(body.new_pin)
    db.commit()


@router.get("/users", response_model=list[schemas.UserOut])
def list_users(_admin: models.User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    return db.query(models.User).order_by(models.User.name).all()


@router.post("/users", response_model=schemas.UserOut, status_code=201)
def create_user(
    body: schemas.UserCreate, _admin: models.User = Depends(auth.require_admin), db: Session = Depends(get_db)
):
    if _name_taken(db, body.name):
        raise HTTPException(409, "Name ist schon vergeben")
    user = models.User(
        name=body.name, pin_hash=auth.get_pin_hash(body.pin), is_admin=body.is_admin, email=body.email
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=schemas.UserOut)
def update_user(
    user_id: int,
    body: schemas.UserPatch,
    _admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    user = _get_user(db, user_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("name") and _name_taken(db, data["name"], except_id=user.id):
        raise HTTPException(409, "Name ist schon vergeben")
    if data.get("is_admin") is False and user.is_admin and _admin_count(db) == 1:
        raise HTTPException(400, "Es braucht mindestens einen Admin")
    for key, value in data.items():
        if key in ("name", "is_admin", "wants_reminders") and value is None:
            continue
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user


@router.post("/users/{user_id}/pin", status_code=204)
def reset_pin(
    user_id: int,
    body: schemas.PinReset,
    _admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    user = _get_user(db, user_id)
    user.pin_hash = auth.get_pin_hash(body.pin)
    user.failed_logins = 0
    user.locked_until = None
    db.commit()


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, admin: models.User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    if user.id == admin.id:
        raise HTTPException(400, "Du kannst dich nicht selbst löschen")
    # Their applications and events stay; "created_by" becomes empty (ON DELETE SET NULL)
    db.delete(user)
    db.commit()
```

Replace `backend/app/main.py` with:
```python
import logging

from fastapi import FastAPI

from . import database, models, users_api
from .seed import seed_admin
from .settings_store import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

models.Base.metadata.create_all(bind=database.engine)

# A fresh database gets the settings row and a first admin to log in with
with database.SessionLocal() as _db:
    get_settings(_db)
    _initial_pin = seed_admin(_db)
if _initial_pin:
    logger.warning("Created user 'Admin' with INITIAL PIN %s. Log in and change it in Einstellungen.", _initial_pin)

app = FastAPI(title="Family Job Tracking API", version="0.1.0")
app.include_router(users_api.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `venv/bin/pytest`
Expected: all tests in `test_health.py`, `test_auth.py` and `test_users.py` pass.

- [ ] **Step 6: Commit**

```bash
git add backend tests
git commit -m "feat(backend): PIN login with lockout and user management

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Status rules and file storage

**Files:**
- Create: `backend/app/status.py`, `backend/app/files.py`, `tests/test_status.py`, `tests/test_files.py`

**Interfaces:**
- Consumes: `config.files_dir()`.
- Produces:
  - `status.STATUSES` (tuple of the 6 status strings), `status.derive_status(events) -> str`, `status.latest(events) -> event | None`, `status.is_due(status, archived, events, followup_days, now) -> bool`, `status.days_since(when, now) -> int`. Events are any objects with `.type: str` and `.occurred_at: datetime`.
  - `files.INBOX_FOLDER = "_posteingang"`, `files.slugify(text, *, lower=True, max_len=40, fallback="unbenannt") -> str`, `files.safe_filename(name) -> (stem, ext)`, `files.company_slug(company) -> str`.
  - `files.store_for_company(company, day: date, original_name, content: bytes) -> str` and `files.store_in_inbox(sender_domain, day, original_name, content) -> str`. Both return the path relative to `files_dir()`.
  - `files.move_to_company(rel_path, company) -> str`, `files.absolute(rel_path) -> Path` (raises `ValueError` outside `files_dir()`), `files.delete(rel_path) -> None`.

- [ ] **Step 1: Write the failing tests**

`tests/test_status.py`:
```python
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
```

`tests/test_files.py`:
```python
from datetime import date

import pytest

from app import config, files

DAY = date(2026, 10, 15)


def test_slugify_umlauts_and_symbols():
    assert files.slugify("Müller & Söhne AG") == "mueller-soehne-ag"
    assert files.slugify("Straße Zürich") == "strasse-zuerich"


def test_slugify_fallback_and_length():
    assert files.slugify("!!!", fallback="firma") == "firma"
    assert files.slugify("株式会社", fallback="firma") == "firma"
    long = files.slugify("Sehr " * 30)
    assert len(long) <= 40
    assert not long.endswith("-")


def test_safe_filename_keeps_case():
    assert files.safe_filename("Lebenslauf Müller (final).PDF") == ("Lebenslauf-Mueller-final", ".pdf")
    assert files.safe_filename("../../etc/passwd") == ("passwd", "")
    assert files.safe_filename("") == ("datei", "")


def test_store_for_company_uses_readable_names_and_counter():
    first = files.store_for_company("Migros Genossenschaft", DAY, "Lebenslauf.pdf", b"a")
    second = files.store_for_company("Migros Genossenschaft", DAY, "Lebenslauf.pdf", b"b")
    third = files.store_for_company("Migros Genossenschaft", DAY, "Lebenslauf.pdf", b"c")
    assert first == "migros-genossenschaft/2026-10-15_migros-genossenschaft_Lebenslauf.pdf"
    assert second == "migros-genossenschaft/2026-10-15_migros-genossenschaft_Lebenslauf_2.pdf"
    assert third == "migros-genossenschaft/2026-10-15_migros-genossenschaft_Lebenslauf_3.pdf"
    assert (config.files_dir() / first).read_bytes() == b"a"


def test_unusable_company_name_gets_fallback_folder():
    assert files.store_for_company("!!!", DAY, "cv.pdf", b"x") == "firma/2026-10-15_firma_cv.pdf"


def test_inbox_and_move_to_company():
    rel = files.store_in_inbox("migros.ch", DAY, "Zeugnis.pdf", b"x")
    assert rel == "_posteingang/2026-10-15_migros-ch_Zeugnis.pdf"
    moved = files.move_to_company(rel, "Migros")
    assert moved == "migros/2026-10-15_migros_Zeugnis.pdf"
    assert not (config.files_dir() / rel).exists()
    assert (config.files_dir() / moved).read_bytes() == b"x"


def test_absolute_rejects_paths_outside_files_dir():
    with pytest.raises(ValueError):
        files.absolute("../test.db")


def test_delete_ignores_missing_file():
    files.delete("migros/nicht-da.pdf")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_status.py tests/test_files.py`
Expected: ERROR at collection, `ImportError: cannot import name 'status' from 'app'`.

- [ ] **Step 3: Implement `backend/app/status.py`**

```python
from datetime import datetime, timedelta
from typing import Iterable, Protocol

STATUSES = ("draft", "open", "in_contact", "closed_offer", "closed_rejection", "closed_withdrawn")
ACTIVE_STATUSES = ("open", "in_contact")

_CLOSING = {"offer": "closed_offer", "rejection": "closed_rejection", "withdrawn": "closed_withdrawn"}
_CONTACT = {"reply_received", "mail_received", "call", "interview", "trial"}


class EventLike(Protocol):
    type: str
    occurred_at: datetime


def latest(events: Iterable[EventLike]) -> EventLike | None:
    return max(events, key=lambda e: e.occurred_at, default=None)


def derive_status(events: Iterable[EventLike]) -> str:
    """An application's status from its timeline; it is never stored."""
    events = list(events)
    closing = [e for e in events if e.type in _CLOSING]
    if closing:
        return _CLOSING[max(closing, key=lambda e: e.occurred_at).type]
    if any(e.type in _CONTACT for e in events):
        return "in_contact"
    if any(e.type == "sent" for e in events):
        return "open"
    return "draft"


def days_since(when: datetime, now: datetime) -> int:
    return max(0, (now - when).days)


def is_due(status: str, archived: bool, events: Iterable[EventLike], followup_days: int, now: datetime) -> bool:
    """Whether to follow up: still active, and nothing has happened for more than followup_days."""
    if archived or status not in ACTIVE_STATUSES:
        return False
    last = latest(events)
    return last is not None and now - last.occurred_at > timedelta(days=followup_days)
```

- [ ] **Step 4: Implement `backend/app/files.py`**

```python
import os
import re
import shutil
import unicodedata
from datetime import date
from pathlib import Path

from . import config

# Unassigned e-mails keep their files here until they are assigned to an application
INBOX_FOLDER = "_posteingang"

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"})


def slugify(text: str, *, lower: bool = True, max_len: int = 40, fallback: str = "unbenannt") -> str:
    """ASCII letters, digits and dashes only, for folder and file names that read well in File Station."""
    text = unicodedata.normalize("NFKD", (text or "").translate(_UMLAUTS)).encode("ascii", "ignore").decode()
    if lower:
        text = text.lower()
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")
    return text[:max_len].strip("-") or fallback


def safe_filename(name: str) -> tuple[str, str]:
    """(stem, extension) of an uploaded or attached file name, cleaned for the file system."""
    stem, ext = os.path.splitext(os.path.basename(name or ""))
    ext = re.sub(r"[^a-z0-9.]", "", ext.lower())[:10]
    return slugify(stem, lower=False, max_len=80, fallback="datei"), ext


def company_slug(company: str) -> str:
    return slugify(company, fallback="firma")


def _unique(folder: Path, base: str, ext: str) -> Path:
    candidate = folder / f"{base}{ext}"
    counter = 2
    while candidate.exists():
        candidate = folder / f"{base}_{counter}{ext}"
        counter += 1
    return candidate


def _store(folder_name: str, day: date, prefix: str, original_name: str, content: bytes) -> str:
    root = config.files_dir()
    folder = root / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    stem, ext = safe_filename(original_name)
    path = _unique(folder, f"{day:%Y-%m-%d}_{prefix}_{stem}", ext)
    path.write_bytes(content)
    return path.relative_to(root).as_posix()


def store_for_company(company: str, day: date, original_name: str, content: bytes) -> str:
    """Save a file as <company>/<date>_<company>_<name>.<ext>; returns the path relative to files_dir()."""
    slug = company_slug(company)
    return _store(slug, day, slug, original_name, content)


def store_in_inbox(sender_domain: str, day: date, original_name: str, content: bytes) -> str:
    """Save a file of an unassigned e-mail as _posteingang/<date>_<sender domain>_<name>.<ext>."""
    return _store(INBOX_FOLDER, day, slugify(sender_domain, fallback="unbekannt"), original_name, content)


def absolute(rel_path: str) -> Path:
    root = config.files_dir().resolve()
    path = (root / rel_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Path outside the files folder: {rel_path}")
    return path


def move_to_company(rel_path: str, company: str) -> str:
    """Move a stored file into the company's folder, renamed with the company; returns the new path."""
    source = absolute(rel_path)
    slug = company_slug(company)
    parts = source.name.split("_", 2)
    if len(parts) == 3:
        day, _prefix, rest = parts
    else:
        day, rest = date.today().isoformat(), source.name
    stem, ext = os.path.splitext(rest)
    folder = config.files_dir() / slug
    folder.mkdir(parents=True, exist_ok=True)
    target = _unique(folder, f"{day}_{slug}_{stem}", ext)
    shutil.move(source, target)
    return target.relative_to(config.files_dir()).as_posix()


def delete(rel_path: str) -> None:
    absolute(rel_path).unlink(missing_ok=True)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_status.py tests/test_files.py`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/status.py backend/app/files.py tests/test_status.py tests/test_files.py
git commit -m "feat(backend): derived status, follow-up rule and readable file storage

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Applications, events, attachments and dashboard API

**Files:**
- Create: `backend/app/views.py`, `backend/app/applications_api.py`, `tests/test_applications.py`
- Modify: `backend/app/schemas.py` (append), `backend/app/main.py` (include router), `tests/helpers.py` (append)

**Interfaces:**
- Consumes: Task 1 models and `get_settings`, `timeutil`, Task 2 `auth.get_current_user`, Task 3 `status` and `files`.
- Produces:
  - `views.attachment_out(a)`, `views.email_out(e)`, `views.event_out(ev)`, `views.mail_address(inbound_address, tag) -> str | None`, `views.summary(application, followup_days, now) -> dict`, `views.detail(application, settings, now) -> dict`.
  - `applications_api.get_application(db, id) -> models.Application` (404), `applications_api.new_mail_tag(db) -> str`, `applications_api.MAX_UPLOAD_BYTES`.
  - Summary JSON: `{id, company, position, location, status, archived, due, last_event_type, last_event_at, days_since_last, mail_tag}`. Detail adds `{contact_name, contact_email, contact_phone, posting_url, channel, notes, created_at, created_by_name, mail_address, events: [...]}` (newest first).
  - Event JSON: `{id, occurred_at, type, note, created_by_name, email: Email|null, attachments: [...]}`.
  - Email JSON: `{id, message_id, from_addr, to_addrs, subject, body_text, received_at, application_id, parse_error, attachments}`.
  - Attachment JSON: `{id, filename, content_type, size, path}`.
  - Dashboard JSON: `{counts: {<status>: int}, due: [summary], inbox_count: int}`.
  - Test helpers `create_application(client, headers, company="Migros", **fields) -> dict` and `add_event(client, headers, application_id, event_type="sent", occurred_at=..., note="", files=None) -> dict`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/helpers.py`:
```python


def create_application(client, headers, company="Migros", **fields) -> dict:
    response = client.post("/api/applications", json={"company": company, **fields}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def add_event(
    client, headers, application_id, event_type="sent", occurred_at="2026-10-01T10:00:00+02:00", note="", files=None
) -> dict:
    response = client.post(
        f"/api/applications/{application_id}/events",
        data={"type": event_type, "occurred_at": occurred_at, "note": note},
        files=files,
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()
```

`tests/test_applications.py`:
```python
from datetime import datetime, timedelta, timezone

from app import applications_api, config
from app.settings_store import get_settings
from helpers import add_event, create_application, create_user, login


def ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def get(client, headers, application_id):
    response = client.get(f"/api/applications/{application_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_endpoints_need_login(client):
    assert client.get("/api/applications").status_code == 401
    assert client.get("/api/dashboard").status_code == 401


def test_create_application(client, admin_headers):
    app = create_application(client, admin_headers, "Migros", position="Kaufmann EFZ", channel="portal")
    assert app["status"] == "draft"
    assert app["channel"] == "portal"
    assert len(app["mail_tag"]) == 4
    assert app["mail_address"] is None
    assert app["created_by_name"] == "Admin"
    assert app["events"] == []


def test_mail_address_uses_inbound_address(client, admin_headers, db):
    get_settings(db).inbound_address = "bewerbungen@example.ch"
    db.commit()
    app = create_application(client, admin_headers)
    assert app["mail_address"] == f"bewerbungen+{app['mail_tag']}@example.ch"


def test_blank_company_is_rejected(client, admin_headers):
    assert client.post("/api/applications", json={"company": "   "}, headers=admin_headers).status_code == 422


def test_status_follows_events(client, admin_headers):
    app = create_application(client, admin_headers)
    add_event(client, admin_headers, app["id"], "sent", "2026-10-01T10:00:00+02:00")
    assert get(client, admin_headers, app["id"])["status"] == "open"
    add_event(client, admin_headers, app["id"], "reply_received", "2026-10-03T10:00:00+02:00")
    assert get(client, admin_headers, app["id"])["status"] == "in_contact"
    add_event(client, admin_headers, app["id"], "rejection", "2026-10-05T10:00:00+02:00")
    assert get(client, admin_headers, app["id"])["status"] == "closed_rejection"
    add_event(client, admin_headers, app["id"], "offer", "2026-10-07T10:00:00+02:00")
    detail = get(client, admin_headers, app["id"])
    assert detail["status"] == "closed_offer"
    assert [e["type"] for e in detail["events"]] == ["offer", "rejection", "reply_received", "sent"]


def test_event_time_is_converted_to_utc(client, admin_headers):
    app = create_application(client, admin_headers)
    with_offset = add_event(client, admin_headers, app["id"], occurred_at="2026-10-01T10:00:00+02:00")
    naive_local = add_event(client, admin_headers, app["id"], occurred_at="2026-10-01T10:00:00")
    assert with_offset["occurred_at"] == naive_local["occurred_at"] == "2026-10-01T08:00:00Z"
    bad = client.post(
        f"/api/applications/{app['id']}/events",
        data={"type": "sent", "occurred_at": "gestern"},
        headers=admin_headers,
    )
    assert bad.status_code == 422


def test_event_with_files(client, admin_headers):
    app = create_application(client, admin_headers, "Migros")
    event = add_event(
        client,
        admin_headers,
        app["id"],
        occurred_at="2026-10-15T09:00:00+02:00",
        files=[
            ("files", ("Lebenslauf.pdf", b"%PDF-1", "application/pdf")),
            ("files", ("Lebenslauf.pdf", b"%PDF-2", "application/pdf")),
        ],
    )
    assert event["created_by_name"] == "Admin"
    assert [a["path"] for a in event["attachments"]] == [
        "migros/2026-10-15_migros_Lebenslauf.pdf",
        "migros/2026-10-15_migros_Lebenslauf_2.pdf",
    ]
    download = client.get(f"/api/attachments/{event['attachments'][0]['id']}", headers=admin_headers)
    assert download.status_code == 200
    assert download.content == b"%PDF-1"
    assert "Lebenslauf.pdf" in download.headers["content-disposition"]


def test_too_large_upload_is_413(client, admin_headers, monkeypatch):
    monkeypatch.setattr(applications_api, "MAX_UPLOAD_BYTES", 5)
    app = create_application(client, admin_headers, "Migros")
    response = client.post(
        f"/api/applications/{app['id']}/events",
        data={"type": "sent", "occurred_at": "2026-10-01T10:00:00"},
        files=[("files", ("gross.pdf", b"123456", "application/pdf"))],
        headers=admin_headers,
    )
    assert response.status_code == 413
    assert not (config.files_dir() / "migros").exists()
    assert get(client, admin_headers, app["id"])["events"] == []


def test_update_and_delete_event(client, admin_headers):
    app = create_application(client, admin_headers)
    event = add_event(client, admin_headers, app["id"])
    updated = client.patch(
        f"/api/events/{event['id']}", json={"type": "followed_up", "note": " Telefon "}, headers=admin_headers
    ).json()
    assert updated["type"] == "followed_up"
    assert updated["note"] == "Telefon"
    assert client.delete(f"/api/events/{event['id']}", headers=admin_headers).status_code == 204
    assert get(client, admin_headers, app["id"])["events"] == []


def test_delete_attachment_removes_file(client, admin_headers):
    app = create_application(client, admin_headers)
    event = add_event(client, admin_headers, app["id"], files=[("files", ("cv.pdf", b"x", "application/pdf"))])
    attachment = event["attachments"][0]
    assert client.delete(f"/api/attachments/{attachment['id']}", headers=admin_headers).status_code == 204
    assert not (config.files_dir() / attachment["path"]).exists()
    assert get(client, admin_headers, app["id"])["events"][0]["attachments"] == []


def test_list_filters(client, admin_headers):
    migros = create_application(client, admin_headers, "Migros")
    coop = create_application(client, admin_headers, "Coop", position="Logistiker EFZ")
    add_event(client, admin_headers, migros["id"])
    client.patch(f"/api/applications/{coop['id']}", json={"archived": True}, headers=admin_headers)

    def companies(**params):
        response = client.get("/api/applications", params=params, headers=admin_headers)
        return [a["company"] for a in response.json()]

    assert companies() == ["Migros"]
    assert sorted(companies(include_archived=True)) == ["Coop", "Migros"]
    assert companies(include_archived=True, q="logis") == ["Coop"]
    assert companies(status="open") == ["Migros"]


def test_update_application(client, admin_headers):
    app = create_application(client, admin_headers)
    updated = client.patch(
        f"/api/applications/{app['id']}",
        json={"company": "Migros Aare", "contact_email": " Jobs@Migros.CH ", "position": None},
        headers=admin_headers,
    ).json()
    assert updated["company"] == "Migros Aare"
    assert updated["contact_email"] == "jobs@migros.ch"
    assert updated["position"] == ""


def test_dashboard_counts_and_due(client, admin_headers):
    migros = create_application(client, admin_headers, "Migros")
    add_event(client, admin_headers, migros["id"], occurred_at=ago(20))
    coop = create_application(client, admin_headers, "Coop")
    add_event(client, admin_headers, coop["id"], occurred_at=ago(2))
    dashboard = client.get("/api/dashboard", headers=admin_headers).json()
    assert dashboard["counts"]["open"] == 2
    assert dashboard["counts"]["draft"] == 0
    assert [a["company"] for a in dashboard["due"]] == ["Migros"]
    assert dashboard["due"][0]["days_since_last"] >= 19
    assert dashboard["inbox_count"] == 0


def test_delete_application_removes_files(client, admin_headers):
    app = create_application(client, admin_headers)
    event = add_event(client, admin_headers, app["id"], files=[("files", ("cv.pdf", b"x", "application/pdf"))])
    assert client.delete(f"/api/applications/{app['id']}", headers=admin_headers).status_code == 204
    assert client.get(f"/api/applications/{app['id']}", headers=admin_headers).status_code == 404
    assert not (config.files_dir() / event["attachments"][0]["path"]).exists()


def test_deleting_user_keeps_their_events(client, admin_headers):
    create_user(client, admin_headers, "Sohn")
    son = login(client, "Sohn", "5678")
    app = create_application(client, son)
    add_event(client, son, app["id"])
    son_id = next(u["id"] for u in client.get("/api/users", headers=admin_headers).json() if u["name"] == "Sohn")
    assert client.delete(f"/api/users/{son_id}", headers=admin_headers).status_code == 204
    detail = get(client, admin_headers, app["id"])
    assert detail["created_by_name"] is None
    assert len(detail["events"]) == 1
    assert detail["events"][0]["created_by_name"] is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_applications.py`
Expected: ERROR at collection, `ImportError: cannot import name 'applications_api' from 'app'`.

- [ ] **Step 3: Append the request schemas to `backend/app/schemas.py`**

Add `from datetime import datetime` and `from .models import Channel, EventType` to the imports at the top, then append:
```python


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
```

Note: in `test_update_application`, `"position": None` must leave the position unchanged (`""`), which is the null-means-unchanged rule.

- [ ] **Step 4: Implement `backend/app/views.py`**

```python
from datetime import datetime

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
```

- [ ] **Step 5: Implement `backend/app/applications_api.py`**

```python
import secrets
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, selectinload

from . import auth
from . import files as filestore
from . import models, schemas
from . import status as st
from . import views
from .database import get_db
from .settings_store import get_settings
from .timeutil import local_date, to_utc, utcnow

router = APIRouter(tags=["applications"], dependencies=[Depends(auth.get_current_user)])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
# No 0/o, 1/l/i: the tag is read and typed by people
TAG_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def new_mail_tag(db: Session) -> str:
    while True:
        tag = "".join(secrets.choice(TAG_ALPHABET) for _ in range(4))
        if db.query(models.Application).filter_by(mail_tag=tag).first() is None:
            return tag


def get_application(db: Session, application_id: int) -> models.Application:
    application = db.get(models.Application, application_id)
    if application is None:
        raise HTTPException(404, "Bewerbung nicht gefunden")
    return application


def _get_event(db: Session, event_id: int) -> models.Event:
    event = db.get(models.Event, event_id)
    if event is None:
        raise HTTPException(404, "Ereignis nicht gefunden")
    return event


def _all_applications(db: Session) -> list[models.Application]:
    return db.query(models.Application).options(selectinload(models.Application.events)).all()


def parse_when(value: str) -> datetime:
    try:
        return to_utc(datetime.fromisoformat(value.strip()))
    except ValueError:
        raise HTTPException(422, "Ungültiges Datum")


async def save_uploads(uploads: list[UploadFile], company: str, day: date) -> list[models.Attachment]:
    """Store uploaded files in the company folder; checks every size first so nothing is half-saved."""
    contents = []
    for upload in uploads:
        data = await upload.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"{upload.filename} ist grösser als 25 MB")
        contents.append((upload, data))
    attachments = []
    for upload, data in contents:
        name = upload.filename or "datei"
        attachments.append(
            models.Attachment(
                filename=name,
                path=filestore.store_for_company(company, day, name, data),
                content_type=upload.content_type or "application/octet-stream",
                size=len(data),
            )
        )
    return attachments


def _delete_attachment_files(attachments: list[models.Attachment]) -> None:
    for attachment in attachments:
        filestore.delete(attachment.path)


@router.get("/applications")
def list_applications(
    status: str | None = None, q: str | None = None, include_archived: bool = False, db: Session = Depends(get_db)
):
    settings = get_settings(db)
    now = utcnow()
    items = [
        views.summary(a, settings.followup_days, now)
        for a in _all_applications(db)
        if include_archived or not a.archived
    ]
    if status:
        items = [i for i in items if i["status"] == status]
    if q:
        needle = q.casefold()
        items = [
            i
            for i in items
            if needle in i["company"].casefold()
            or needle in i["position"].casefold()
            or needle in i["location"].casefold()
        ]
    # Most recent activity first; applications without events last
    items.sort(key=lambda i: i["last_event_at"] or "", reverse=True)
    return items


@router.post("/applications", status_code=201)
def create_application(
    body: schemas.ApplicationIn, user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)
):
    application = models.Application(**body.model_dump(mode="json"), mail_tag=new_mail_tag(db), created_by=user.id)
    db.add(application)
    db.commit()
    db.refresh(application)
    return views.detail(application, get_settings(db), utcnow())


@router.get("/applications/{application_id}")
def read_application(application_id: int, db: Session = Depends(get_db)):
    return views.detail(get_application(db, application_id), get_settings(db), utcnow())


@router.patch("/applications/{application_id}")
def update_application(application_id: int, body: schemas.ApplicationPatch, db: Session = Depends(get_db)):
    application = get_application(db, application_id)
    for key, value in body.model_dump(exclude_unset=True, mode="json").items():
        if value is not None:
            setattr(application, key, value)
    db.commit()
    db.refresh(application)
    return views.detail(application, get_settings(db), utcnow())


@router.delete("/applications/{application_id}", status_code=204)
def delete_application(application_id: int, db: Session = Depends(get_db)):
    application = get_application(db, application_id)
    for event in application.events:
        _delete_attachment_files(event.attachments)
    for email in application.emails:
        _delete_attachment_files(email.attachments)
        if email.raw_path:
            filestore.delete(email.raw_path)
    db.delete(application)
    db.commit()


@router.post("/applications/{application_id}/events", status_code=201)
async def create_event(
    application_id: int,
    event_type: models.EventType = Form(..., alias="type"),
    occurred_at: str = Form(...),
    note: str = Form(""),
    files: list[UploadFile] | None = File(None),
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    application = get_application(db, application_id)
    when = parse_when(occurred_at)
    event = models.Event(
        application_id=application.id,
        occurred_at=when,
        type=event_type.value,
        note=note.strip(),
        created_by=user.id,
    )
    event.attachments = await save_uploads(files or [], application.company, local_date(when))
    db.add(event)
    db.commit()
    db.refresh(event)
    return views.event_out(event)


@router.patch("/events/{event_id}")
def update_event(event_id: int, body: schemas.EventPatch, db: Session = Depends(get_db)):
    event = _get_event(db, event_id)
    if body.type is not None:
        event.type = body.type.value
    if body.occurred_at is not None:
        event.occurred_at = to_utc(body.occurred_at)
    if body.note is not None:
        event.note = body.note.strip()
    db.commit()
    db.refresh(event)
    return views.event_out(event)


@router.delete("/events/{event_id}", status_code=204)
def delete_event(event_id: int, db: Session = Depends(get_db)):
    event = _get_event(db, event_id)
    _delete_attachment_files(event.attachments)
    db.delete(event)
    db.commit()


@router.get("/attachments/{attachment_id}")
def download_attachment(attachment_id: int, db: Session = Depends(get_db)):
    attachment = db.get(models.Attachment, attachment_id)
    if attachment is None:
        raise HTTPException(404, "Datei nicht gefunden")
    path = filestore.absolute(attachment.path)
    if not path.exists():
        raise HTTPException(404, "Datei fehlt auf dem NAS")
    return FileResponse(path, media_type=attachment.content_type, filename=attachment.filename)


@router.delete("/attachments/{attachment_id}", status_code=204)
def delete_attachment(attachment_id: int, db: Session = Depends(get_db)):
    attachment = db.get(models.Attachment, attachment_id)
    if attachment is None:
        raise HTTPException(404, "Datei nicht gefunden")
    filestore.delete(attachment.path)
    db.delete(attachment)
    db.commit()


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    settings = get_settings(db)
    now = utcnow()
    items = [views.summary(a, settings.followup_days, now) for a in _all_applications(db) if not a.archived]
    counts = {status: 0 for status in st.STATUSES}
    for item in items:
        counts[item["status"]] += 1
    due = sorted((i for i in items if i["due"]), key=lambda i: i["days_since_last"] or 0, reverse=True)
    inbox_count = (
        db.query(models.Email)
        .filter(models.Email.application_id.is_(None), models.Email.dismissed.is_(False))
        .count()
    )
    return {"counts": counts, "due": due, "inbox_count": inbox_count}
```

In `backend/app/main.py` change the import line to `from . import applications_api, database, models, users_api` and add after the users router:
```python
app.include_router(applications_api.router, prefix="/api")
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `venv/bin/pytest`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend tests
git commit -m "feat(backend): applications, timeline events, attachments and dashboard

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: E-mail parsing

**Files:**
- Create: `backend/app/mailparse.py`, `tests/mails.py`, `tests/test_mailparse.py`

**Interfaces:**
- Consumes: `timeutil.to_utc`.
- Produces:
  - `mailparse.MailParseError`.
  - `mailparse.ParsedAttachment(filename: str, content_type: str, content: bytes)`.
  - `mailparse.ParsedMail(message_id, from_addr, to_addrs: list[str], recipients: list[str], subject, body_text, date: datetime | None, attachments: list[ParsedAttachment])`. All addresses are lower-case. `recipients` holds the envelope recipient first, then To, Cc, Delivered-To and X-Original-To. `date` is naive UTC.
  - `mailparse.parse(raw: bytes, envelope_to: str | None = None) -> ParsedMail` (raises `MailParseError`), `mailparse.find_tag(recipients, known_tags: set[str]) -> str | None`, `mailparse.sender_domain(address) -> str`, `mailparse.fallback_message_id(raw) -> str`, `mailparse.html_to_text(html) -> str`.
  - Test helper `mails.build_mail(...) -> bytes` and `mails.BROKEN_MAIL`.

- [ ] **Step 1: Write the failing tests**

`tests/mails.py`:
```python
from email.message import EmailMessage

# Declares a charset Python doesn't know, so reading the body fails
BROKEN_MAIL = (
    b"From: hr@migros.ch\r\nSubject: kaputt\r\nMessage-ID: <broken@migros.ch>\r\n"
    b"Content-Type: text/plain; charset=x-unbekannt\r\nContent-Transfer-Encoding: base64\r\n\r\nSGFsbG8=\r\n"
)


def build_mail(
    *,
    subject="Ihre Bewerbung",
    sender="Personal <hr@migros.ch>",
    to="bewerbungen+abcd@example.ch",
    cc=None,
    body="Guten Tag",
    html=None,
    attachments=(),
    message_id="<m1@migros.ch>",
    date="Thu, 15 Oct 2026 09:30:00 +0200",
) -> bytes:
    """A raw e-mail as the Cloudflare worker would deliver it; attachments are (name, bytes, content type)."""
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    msg["Subject"] = subject
    if message_id:
        msg["Message-ID"] = message_id
    if date:
        msg["Date"] = date
    if body is not None:
        msg.set_content(body)
        if html:
            msg.add_alternative(html, subtype="html")
    else:
        msg.set_content(html or "", subtype="html")
    for name, content, content_type in attachments:
        maintype, subtype = content_type.split("/")
        msg.add_attachment(content, maintype=maintype, subtype=subtype, filename=name)
    return msg.as_bytes()
```

`tests/test_mailparse.py`:
```python
from datetime import datetime
from email import message_from_bytes, policy
from email.message import EmailMessage

import pytest

from app import mailparse
from mails import BROKEN_MAIL, build_mail


def test_parses_plain_mail():
    mail = mailparse.parse(build_mail(cc="Papa <Papa@Example.ch>"))
    assert mail.message_id == "<m1@migros.ch>"
    assert mail.from_addr == "hr@migros.ch"
    assert mail.to_addrs == ["bewerbungen+abcd@example.ch", "papa@example.ch"]
    assert mail.subject == "Ihre Bewerbung"
    assert mail.body_text == "Guten Tag"
    assert mail.date == datetime(2026, 10, 15, 7, 30)
    assert mail.attachments == []


def test_decodes_umlauts_in_subject_and_filename():
    raw = build_mail(
        subject="Einladung zum Gespräch", attachments=[("Lebenslauf Müller.pdf", b"%PDF", "application/pdf")]
    )
    mail = mailparse.parse(raw)
    assert mail.subject == "Einladung zum Gespräch"
    assert [(a.filename, a.content_type, a.content) for a in mail.attachments] == [
        ("Lebenslauf Müller.pdf", "application/pdf", b"%PDF")
    ]


def test_html_only_mail_becomes_text():
    html = "<html><style>p{}</style><body><p>Guten&nbsp;Tag</p><p>Wir laden Sie <b>ein</b>.</p></body></html>"
    body = mailparse.parse(build_mail(body=None, html=html)).body_text
    assert "Guten" in body
    assert "Wir laden Sie ein." in body
    assert "<" not in body
    assert "p{}" not in body


def test_missing_or_invalid_date_is_none():
    assert mailparse.parse(build_mail(date=None)).date is None
    raw = build_mail(date=None).replace(b"Subject:", b"Date: gestern\nSubject:", 1)
    assert mailparse.parse(raw).date is None


def test_missing_message_id_uses_hash():
    raw = build_mail(message_id=None)
    assert mailparse.parse(raw).message_id == mailparse.fallback_message_id(raw)


def test_envelope_recipient_comes_first():
    mail = mailparse.parse(build_mail(to="hr@migros.ch"), envelope_to="Bewerbungen+ABCD@example.ch")
    assert mail.recipients[0] == "bewerbungen+abcd@example.ch"


def test_find_tag():
    assert mailparse.find_tag(["hr@migros.ch", "bewerbungen+abcd@example.ch"], {"abcd"}) == "abcd"
    assert mailparse.find_tag(["Bewerbungen+ABCD@example.ch"], {"abcd"}) == "abcd"
    assert mailparse.find_tag(["bewerbungen+zzzz@example.ch"], {"abcd"}) is None
    assert mailparse.find_tag(["bewerbungen@example.ch"], {"abcd"}) is None


def test_sender_domain():
    assert mailparse.sender_domain("hr@Migros.ch") == "migros.ch"
    assert mailparse.sender_domain("") == ""


def test_forwarded_mail_as_attachment():
    outer = EmailMessage()
    outer["From"] = "sohn@example.ch"
    outer["To"] = "bewerbungen+abcd@example.ch"
    outer["Subject"] = "Fwd: Original"
    outer.set_content("siehe Anhang")
    outer.add_attachment(message_from_bytes(build_mail(subject="Original"), policy=policy.default))
    mail = mailparse.parse(outer.as_bytes())
    assert mail.attachments[0].filename == "weitergeleitet.eml"
    assert b"Subject: Original" in mail.attachments[0].content


def test_broken_and_empty_mail_raise():
    with pytest.raises(mailparse.MailParseError):
        mailparse.parse(BROKEN_MAIL)
    with pytest.raises(mailparse.MailParseError):
        mailparse.parse(b"  \r\n")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_mailparse.py`
Expected: ERROR at collection, `ImportError: cannot import name 'mailparse' from 'app'`.

- [ ] **Step 3: Implement `backend/app/mailparse.py`**

```python
import hashlib
import mimetypes
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from html.parser import HTMLParser

from .timeutil import to_utc


class MailParseError(Exception):
    """The raw e-mail could not be read."""


@dataclass
class ParsedAttachment:
    filename: str
    content_type: str
    content: bytes


@dataclass
class ParsedMail:
    message_id: str
    from_addr: str
    to_addrs: list[str]
    recipients: list[str]  # envelope recipient first, then To/Cc/Delivered-To/X-Original-To
    subject: str
    body_text: str
    date: datetime | None  # naive UTC; None if missing or unreadable
    attachments: list[ParsedAttachment] = field(default_factory=list)


def fallback_message_id(raw: bytes) -> str:
    """A stable id for mails without Message-ID, so a second delivery is still recognised."""
    return f"<{hashlib.sha256(raw).hexdigest()}@family-job-tracking.local>"


def sender_domain(address: str) -> str:
    return address.rpartition("@")[2].lower() if "@" in address else ""


_TAG = re.compile(r"^[^@+\s]+\+([a-z0-9]+)@", re.IGNORECASE)


def find_tag(recipients: list[str], known_tags: set[str]) -> str | None:
    """The first +tag of a recipient address that belongs to an application."""
    for address in recipients:
        match = _TAG.match(address.strip().lower())
        if match and match.group(1) in known_tags:
            return match.group(1)
    return None


class _TextExtractor(HTMLParser):
    _BLOCKS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    lines = [re.sub(r"\s+", " ", line).strip() for line in "".join(parser.parts).splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _addresses(msg: EmailMessage, *headers: str) -> list[str]:
    values = [str(value) for header in headers for value in msg.get_all(header, [])]
    return [address.lower() for _name, address in getaddresses(values) if address]


def _date(msg: EmailMessage) -> datetime | None:
    try:
        value = msg.get("Date")
        if not value:
            return None
        parsed = parsedate_to_datetime(str(value))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return to_utc(parsed)


def _body(msg: EmailMessage) -> str:
    part = msg.get_body(preferencelist=("plain",))
    if part is not None:
        return part.get_content().strip()
    part = msg.get_body(preferencelist=("html",))
    if part is not None:
        return html_to_text(part.get_content())
    return ""


def _attachments(msg: EmailMessage) -> list[ParsedAttachment]:
    result = []
    for index, part in enumerate(msg.iter_attachments(), start=1):
        content_type = part.get_content_type()
        if content_type == "message/rfc822":
            # A mail forwarded "as attachment": keep it as an .eml file
            content = part.get_content().as_bytes()
            default_name = "weitergeleitet.eml"
        else:
            content = part.get_payload(decode=True) or b""
            default_name = f"anhang-{index}{mimetypes.guess_extension(content_type) or ''}"
        result.append(ParsedAttachment(part.get_filename() or default_name, content_type, content))
    return result


def parse(raw: bytes, envelope_to: str | None = None) -> ParsedMail:
    if not raw.strip():
        raise MailParseError("Leere Nachricht")
    try:
        msg = BytesParser(policy=policy.default).parsebytes(raw)
        to_addrs = _addresses(msg, "To", "Cc")
        envelope = [envelope_to.strip().lower()] if envelope_to else []
        return ParsedMail(
            message_id=str(msg.get("Message-ID", "")).strip() or fallback_message_id(raw),
            from_addr=parseaddr(str(msg.get("From", "")))[1].lower(),
            to_addrs=to_addrs,
            recipients=envelope + to_addrs + _addresses(msg, "Delivered-To", "X-Original-To"),
            subject=" ".join(str(msg.get("Subject", "")).split()),
            body_text=_body(msg),
            date=_date(msg),
            attachments=_attachments(msg),
        )
    except Exception as exc:
        raise MailParseError(f"{type(exc).__name__}: {exc}") from exc
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_mailparse.py`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/mailparse.py tests/mails.py tests/test_mailparse.py
git commit -m "feat(backend): parse raw e-mails with tags, attachments and fallbacks

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Inbound e-mail endpoint

**Files:**
- Create: `backend/app/inbound.py`, `backend/app/inbox_api.py`, `tests/test_inbound.py`
- Modify: `backend/app/main.py` (include router), `tests/mails.py` (append)

**Interfaces:**
- Consumes: `mailparse.*`, `files.store_for_company`, `files.store_in_inbox`, `files.slugify`, `get_settings`, `timeutil`.
- Produces:
  - `inbound.UNREADABLE_SUBJECT`, `inbound.FREEMAIL_DOMAINS`.
  - `inbound.process(db, raw: bytes, envelope_to: str | None) -> models.Email | None` returns None for a duplicate and commits.
  - `inbound.create_mail_event(db, email, application, event_type: models.EventType | None = None) -> models.Event` adds to the session without committing. The default type is `mail_sent` if the sender is a user's e-mail, else `mail_received`.
  - `inbox_api.router`, `inbox_api.MAX_INBOUND_BYTES`.
  - `POST /api/inbound` takes headers `X-Inbound-Secret` and `X-Envelope-To` and the raw body. It answers `{"status": "stored", "email_id", "application_id"}` or `{"status": "duplicate"}`, and 401/413/503 on errors.
  - Test helpers `mails.INBOUND_SECRET = "s3cret"` and `mails.post_mail(client, raw, envelope_to=None, secret=INBOUND_SECRET)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/mails.py`:
```python


INBOUND_SECRET = "s3cret"


def post_mail(client, raw, envelope_to=None, secret=INBOUND_SECRET):
    headers = {"X-Inbound-Secret": secret, "Content-Type": "message/rfc822"}
    if envelope_to:
        headers["X-Envelope-To"] = envelope_to
    return client.post("/api/inbound", content=raw, headers=headers)
```

`tests/test_inbound.py`:
```python
from datetime import timedelta

import pytest

from app import config, inbox_api, models
from app.settings_store import get_settings
from app.timeutil import utcnow
from helpers import create_application, create_user
from mails import BROKEN_MAIL, INBOUND_SECRET, build_mail, post_mail


@pytest.fixture(autouse=True)
def inbound_secret(monkeypatch):
    monkeypatch.setenv("INBOUND_SECRET", INBOUND_SECRET)


def tagged(application):
    return f"bewerbungen+{application['mail_tag']}@example.ch"


def detail(client, headers, application_id):
    return client.get(f"/api/applications/{application_id}", headers=headers).json()


def test_not_configured_is_503(client, monkeypatch):
    monkeypatch.delenv("INBOUND_SECRET")
    assert post_mail(client, build_mail()).status_code == 503


def test_wrong_secret_is_401(client):
    assert post_mail(client, build_mail(), secret="falsch").status_code == 401


def test_tagged_mail_creates_event_and_files(client, admin_headers):
    app = create_application(client, admin_headers, "Migros")
    raw = build_mail(
        to=tagged(app),
        subject="Einladung zum Gespräch",
        attachments=[("Lebenslauf Müller.pdf", b"%PDF", "application/pdf")],
    )
    response = post_mail(client, raw)
    assert response.status_code == 200
    assert response.json()["status"] == "stored"
    assert response.json()["application_id"] == app["id"]

    result = detail(client, admin_headers, app["id"])
    assert result["status"] == "in_contact"
    event = result["events"][0]
    assert event["type"] == "mail_received"
    assert event["note"] == "Einladung zum Gespräch"
    assert event["occurred_at"] == "2026-10-15T07:30:00Z"
    assert event["created_by_name"] is None
    attachment = event["email"]["attachments"][0]
    assert attachment["filename"] == "Lebenslauf Müller.pdf"
    assert attachment["path"] == "migros/2026-10-15_migros_Lebenslauf-Mueller.pdf"
    assert (config.files_dir() / attachment["path"]).read_bytes() == b"%PDF"
    assert [p.name for p in (config.files_dir() / "migros").glob("*.eml")] == [
        "2026-10-15_migros_mail-Einladung-zum-Gespraech.eml"
    ]


def test_bcc_uses_envelope_recipient(client, admin_headers):
    app = create_application(client, admin_headers, "Migros")
    raw = build_mail(sender="sohn@example.ch", to="hr@migros.ch")
    response = post_mail(client, raw, envelope_to=tagged(app))
    assert response.json()["application_id"] == app["id"]


def test_mail_from_a_user_is_mail_sent(client, admin_headers):
    create_user(client, admin_headers, "Sohn", email="sohn@example.ch")
    app = create_application(client, admin_headers, "Migros")
    post_mail(client, build_mail(sender="Sohn <Sohn@Example.ch>", to="hr@migros.ch", cc=tagged(app)))
    assert [e["type"] for e in detail(client, admin_headers, app["id"])["events"]] == ["mail_sent"]


def test_untagged_mail_goes_to_inbox(client, admin_headers, db):
    raw = build_mail(to="bewerbungen@example.ch", attachments=[("Zeugnis.pdf", b"x", "application/pdf")])
    assert post_mail(client, raw).json()["application_id"] is None
    email = db.query(models.Email).one()
    assert email.application_id is None
    assert email.attachments[0].path == "_posteingang/2026-10-15_migros-ch_Zeugnis.pdf"
    assert client.get("/api/dashboard", headers=admin_headers).json()["inbox_count"] == 1


def test_duplicate_message_id_is_ignored(client, db):
    raw = build_mail()
    assert post_mail(client, raw).json()["status"] == "stored"
    assert post_mail(client, raw).json()["status"] == "duplicate"
    assert db.query(models.Email).count() == 1


def test_broken_mail_is_kept_and_reported(client, db):
    response = post_mail(client, BROKEN_MAIL)
    assert response.status_code == 200
    email = db.query(models.Email).one()
    assert email.parse_error
    assert email.subject == "(konnte nicht gelesen werden)"
    assert (config.files_dir() / email.raw_path).read_bytes() == BROKEN_MAIL
    settings = get_settings(db)
    assert settings.last_inbound_error
    assert settings.last_inbound_at is not None

    post_mail(client, build_mail())
    db.expire_all()
    assert get_settings(db).last_inbound_error is None


def test_mail_without_date_uses_arrival_time(client, db):
    before = utcnow() - timedelta(seconds=1)
    post_mail(client, build_mail(date=None))
    email = db.query(models.Email).one()
    assert before <= email.received_at <= utcnow()


def test_oversize_mail_is_413(client, monkeypatch):
    monkeypatch.setattr(inbox_api, "MAX_INBOUND_BYTES", 10)
    assert post_mail(client, build_mail()).status_code == 413
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_inbound.py`
Expected: ERROR at collection, `ImportError: cannot import name 'inbox_api' from 'app'`.

- [ ] **Step 3: Implement `backend/app/inbound.py`**

```python
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
```

- [ ] **Step 4: Implement `backend/app/inbox_api.py` with the inbound route**

```python
import hmac

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import config, inbound
from .database import get_db

router = APIRouter(tags=["inbox"])

MAX_INBOUND_BYTES = 25 * 1024 * 1024


@router.post("/inbound")
async def receive_mail(request: Request, db: Session = Depends(get_db)):
    """Called by the Cloudflare Email Worker with the raw e-mail; protected by a shared secret, not a login."""
    secret = config.env("INBOUND_SECRET")
    if not secret:
        raise HTTPException(503, "Eingehende Mails sind nicht konfiguriert")
    given = request.headers.get("x-inbound-secret", "")
    if not hmac.compare_digest(given.encode(), secret.encode()):
        raise HTTPException(401, "Falsches Inbound-Secret")
    length = request.headers.get("content-length", "")
    if length.isdigit() and int(length) > MAX_INBOUND_BYTES:
        raise HTTPException(413, "Mail ist grösser als 25 MB")
    raw = await request.body()
    if len(raw) > MAX_INBOUND_BYTES:
        raise HTTPException(413, "Mail ist grösser als 25 MB")
    email = inbound.process(db, raw, request.headers.get("x-envelope-to"))
    if email is None:
        return {"status": "duplicate"}
    return {"status": "stored", "email_id": email.id, "application_id": email.application_id}
```

In `backend/app/main.py` change the import line to `from . import applications_api, database, inbox_api, models, users_api` and add:
```python
app.include_router(inbox_api.router, prefix="/api")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `venv/bin/pytest`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend tests
git commit -m "feat(backend): receive e-mails from the Cloudflare worker

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Inbox: suggestions, assign, create, dismiss

**Files:**
- Modify: `backend/app/inbound.py` (append `assign`, `suggest`), `backend/app/inbox_api.py` (append routes), `backend/app/schemas.py` (append)
- Create: `tests/test_inbox.py`

**Interfaces:**
- Consumes: `applications_api.get_application`, `applications_api.new_mail_tag`, `views.email_out`, `files.move_to_company`, `status.latest`.
- Produces:
  - `inbound.assign(db, email, application, event_type=None) -> models.Event` moves the files and adds the event, without committing.
  - `inbound.suggest(db, email) -> models.Application | None`.
  - Endpoints: `GET /api/inbox` (each item is Email JSON plus `suggestion: {id, company, position} | null`), `POST /api/inbox/{id}/assign` (`{application_id, event_type?}` → Email JSON), `POST /api/inbox/{id}/create-application` (`{company, position?}` → 201 `{application_id}`), `POST /api/inbox/{id}/dismiss` (204), `GET /api/emails/{id}` (Email JSON), `GET /api/emails/{id}/raw` (`message/rfc822`).

- [ ] **Step 1: Write the failing tests**

`tests/test_inbox.py`:
```python
import pytest

from app import config
from helpers import create_application
from mails import INBOUND_SECRET, build_mail, post_mail


@pytest.fixture(autouse=True)
def inbound_secret(monkeypatch):
    monkeypatch.setenv("INBOUND_SECRET", INBOUND_SECRET)


def inbox(client, headers):
    response = client.get("/api/inbox", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_inbox_needs_login(client):
    assert client.get("/api/inbox").status_code == 401


def test_inbox_suggests_application_by_sender_domain(client, admin_headers):
    migros = create_application(client, admin_headers, "Migros", contact_email="jobs@migros.ch")
    create_application(client, admin_headers, "Coop", contact_email="jobs@coop.ch")
    post_mail(client, build_mail(to="bewerbungen@example.ch", sender="hr@migros.ch"))
    items = inbox(client, admin_headers)
    assert len(items) == 1
    assert items[0]["subject"] == "Ihre Bewerbung"
    assert items[0]["suggestion"] == {"id": migros["id"], "company": "Migros", "position": ""}


def test_freemail_sender_gets_no_suggestion(client, admin_headers):
    create_application(client, admin_headers, "Garage Meier", contact_email="chef@gmail.com")
    post_mail(client, build_mail(to="bewerbungen@example.ch", sender="chef@gmail.com"))
    assert inbox(client, admin_headers)[0]["suggestion"] is None


def test_assign_moves_files_and_creates_event(client, admin_headers):
    migros = create_application(client, admin_headers, "Migros")
    post_mail(
        client,
        build_mail(to="bewerbungen@example.ch", attachments=[("Zeugnis.pdf", b"x", "application/pdf")]),
    )
    email = inbox(client, admin_headers)[0]
    response = client.post(
        f"/api/inbox/{email['id']}/assign", json={"application_id": migros["id"]}, headers=admin_headers
    )
    assert response.status_code == 200, response.text
    assert inbox(client, admin_headers) == []

    event = client.get(f"/api/applications/{migros['id']}", headers=admin_headers).json()["events"][0]
    assert event["type"] == "mail_received"
    path = event["email"]["attachments"][0]["path"]
    assert path == "migros/2026-10-15_migros_Zeugnis.pdf"
    assert (config.files_dir() / path).exists()
    assert list((config.files_dir() / "_posteingang").iterdir()) == []


def test_assign_with_event_type(client, admin_headers):
    migros = create_application(client, admin_headers, "Migros")
    post_mail(client, build_mail(to="bewerbungen@example.ch"))
    email = inbox(client, admin_headers)[0]
    client.post(
        f"/api/inbox/{email['id']}/assign",
        json={"application_id": migros["id"], "event_type": "reply_received"},
        headers=admin_headers,
    )
    events = client.get(f"/api/applications/{migros['id']}", headers=admin_headers).json()["events"]
    assert [e["type"] for e in events] == ["reply_received"]


def test_assign_twice_is_409(client, admin_headers):
    migros = create_application(client, admin_headers, "Migros")
    post_mail(client, build_mail(to="bewerbungen@example.ch"))
    email_id = inbox(client, admin_headers)[0]["id"]
    body = {"application_id": migros["id"]}
    assert client.post(f"/api/inbox/{email_id}/assign", json=body, headers=admin_headers).status_code == 200
    assert client.post(f"/api/inbox/{email_id}/assign", json=body, headers=admin_headers).status_code == 409


def test_create_application_from_mail(client, admin_headers):
    post_mail(client, build_mail(to="bewerbungen@example.ch", sender="hr@coop.ch"))
    email_id = inbox(client, admin_headers)[0]["id"]
    response = client.post(
        f"/api/inbox/{email_id}/create-application",
        json={"company": "Coop", "position": "Logistiker EFZ"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    application = client.get(f"/api/applications/{response.json()['application_id']}", headers=admin_headers).json()
    assert application["company"] == "Coop"
    assert application["position"] == "Logistiker EFZ"
    assert application["contact_email"] == "hr@coop.ch"
    assert [e["type"] for e in application["events"]] == ["mail_received"]
    assert application["status"] == "in_contact"


def test_dismiss(client, admin_headers):
    post_mail(client, build_mail(to="bewerbungen@example.ch"))
    email_id = inbox(client, admin_headers)[0]["id"]
    assert client.post(f"/api/inbox/{email_id}/dismiss", headers=admin_headers).status_code == 204
    assert inbox(client, admin_headers) == []
    assert client.get("/api/dashboard", headers=admin_headers).json()["inbox_count"] == 0


def test_read_email_and_raw(client, admin_headers):
    raw = build_mail(to="bewerbungen@example.ch")
    post_mail(client, raw)
    email_id = inbox(client, admin_headers)[0]["id"]
    assert client.get(f"/api/emails/{email_id}", headers=admin_headers).json()["body_text"] == "Guten Tag"
    response = client.get(f"/api/emails/{email_id}/raw", headers=admin_headers)
    assert response.status_code == 200
    assert response.content == raw
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_inbox.py`
Expected: FAIL. `test_inbox_needs_login` gets 404 instead of 401, and the other tests fail with 404 from `/api/inbox`.

- [ ] **Step 3: Append the schemas to `backend/app/schemas.py`**

```python


class AssignIn(BaseModel):
    application_id: int
    event_type: EventType | None = None


class InboxApplicationIn(BaseModel):
    company: str = Field(max_length=200)
    position: str = Field("", max_length=200)

    check_company = field_validator("company")(clean_company)
```

- [ ] **Step 4: Append `assign` and `suggest` to `backend/app/inbound.py`**

Add `from . import status as st` to the imports, then append:
```python


def assign(
    db: Session, email: models.Email, application: models.Application, event_type: models.EventType | None = None
) -> models.Event:
    """Link an inbox e-mail to an application: move its files into the company folder and add it to the timeline."""
    if email.raw_path:
        email.raw_path = filestore.move_to_company(email.raw_path, application.company)
    for attachment in email.attachments:
        attachment.path = filestore.move_to_company(attachment.path, application.company)
    email.application_id = application.id
    db.flush()
    return create_mail_event(db, email, application, event_type)


def suggest(db: Session, email: models.Email) -> models.Application | None:
    """The active application the sender's domain belongs to (contact address or earlier e-mails)."""
    domain = mailparse.sender_domain(email.from_addr)
    if not domain or domain in FREEMAIL_DOMAINS:
        return None
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
    if not candidates:
        return None

    def last_activity(application: models.Application):
        last = st.latest(application.events)
        return last.occurred_at if last else application.created_at

    return max(candidates.values(), key=last_activity)
```

- [ ] **Step 5: Append the inbox routes to `backend/app/inbox_api.py`**

Change the imports at the top to:
```python
import hmac
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from . import auth, config
from . import files as filestore
from . import inbound, models, schemas, views
from .applications_api import get_application, new_mail_tag
from .database import get_db
```

Append:
```python


def _get_email(db: Session, email_id: int) -> models.Email:
    email = db.get(models.Email, email_id)
    if email is None:
        raise HTTPException(404, "Mail nicht gefunden")
    return email


def _get_unassigned(db: Session, email_id: int) -> models.Email:
    email = _get_email(db, email_id)
    if email.application_id is not None:
        raise HTTPException(409, "Mail ist schon zugeordnet")
    return email


def _suggestion_out(application: models.Application | None) -> dict | None:
    if application is None:
        return None
    return {"id": application.id, "company": application.company, "position": application.position}


@router.get("/inbox", dependencies=[Depends(auth.get_current_user)])
def list_inbox(db: Session = Depends(get_db)):
    emails = (
        db.query(models.Email)
        .filter(models.Email.application_id.is_(None), models.Email.dismissed.is_(False))
        .order_by(models.Email.received_at.desc())
        .all()
    )
    return [views.email_out(e) | {"suggestion": _suggestion_out(inbound.suggest(db, e))} for e in emails]


@router.post("/inbox/{email_id}/assign", dependencies=[Depends(auth.get_current_user)])
def assign_email(email_id: int, body: schemas.AssignIn, db: Session = Depends(get_db)):
    email = _get_unassigned(db, email_id)
    application = get_application(db, body.application_id)
    inbound.assign(db, email, application, body.event_type)
    db.commit()
    db.refresh(email)
    return views.email_out(email)


@router.post("/inbox/{email_id}/create-application", status_code=201)
def create_application_from_email(
    email_id: int,
    body: schemas.InboxApplicationIn,
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    email = _get_unassigned(db, email_id)
    application = models.Application(
        company=body.company,
        position=body.position,
        contact_email=email.from_addr,
        channel=models.Channel.EMAIL.value,
        mail_tag=new_mail_tag(db),
        created_by=user.id,
    )
    db.add(application)
    db.flush()
    inbound.assign(db, email, application)
    db.commit()
    return {"application_id": application.id}


@router.post("/inbox/{email_id}/dismiss", status_code=204, dependencies=[Depends(auth.get_current_user)])
def dismiss_email(email_id: int, db: Session = Depends(get_db)):
    email = _get_unassigned(db, email_id)
    email.dismissed = True
    db.commit()


@router.get("/emails/{email_id}", dependencies=[Depends(auth.get_current_user)])
def read_email(email_id: int, db: Session = Depends(get_db)):
    return views.email_out(_get_email(db, email_id))


@router.get("/emails/{email_id}/raw", dependencies=[Depends(auth.get_current_user)])
def read_raw_email(email_id: int, db: Session = Depends(get_db)):
    email = _get_email(db, email_id)
    path = filestore.absolute(email.raw_path) if email.raw_path else None
    if path is None or not path.exists():
        raise HTTPException(404, "Originalmail fehlt auf dem NAS")
    return FileResponse(path, media_type="message/rfc822", filename=Path(email.raw_path).name)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `venv/bin/pytest`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend tests
git commit -m "feat(backend): inbox with suggestions, assign, create and dismiss

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Reminder digest via Resend

**Files:**
- Create: `backend/app/reminders.py`, `tests/test_reminders.py`
- Modify: `backend/app/main.py` (startup log lines, lifespan that starts the reminder loop)

**Interfaces:**
- Consumes: `get_settings`, `status.*`, `timeutil.*`, `database.SessionLocal`, `config.env`.
- Produces:
  - `reminders.is_configured() -> bool`.
  - `reminders.Sender = Callable[[mail_from, to: list[str], subject, text, html], None]`.
  - `reminders.resend_send(mail_from, to, subject, text, html_body) -> None` (raises `RuntimeError`).
  - `reminders.DueItem(id, company, position, days)`, `reminders.Digest(due, inbox_count)` with `.empty`.
  - `reminders.build_digest(db, now) -> Digest`, `reminders.render(digest, app_url) -> (subject, text, html)`, `reminders.recipients(db) -> list[str]`.
  - `reminders.run_once(db, now, send=None) -> str` returns one of `not_configured`, `not_due`, `empty`, `no_recipients`, `sent`, `error`. `send=None` means `resend_send`, looked up at call time so tests can monkeypatch it.
  - `reminders.send_test(db, user, now, send=None) -> None` raises `ValueError` for setup problems and re-raises send errors.
  - `reminders.next_run(settings, now) -> datetime` (naive UTC), `reminders.loop()` (coroutine).

- [ ] **Step 1: Write the failing tests**

`tests/test_reminders.py`:
```python
import json
from datetime import datetime, timedelta

import pytest

from app import models, reminders
from app.settings_store import get_settings
from app.timeutil import to_utc


def local(*args):
    """A local (Zurich) wall-clock time as stored naive UTC."""
    return to_utc(datetime(*args))


MORNING = local(2026, 10, 15, 6, 0)
AFTER = local(2026, 10, 15, 7, 5)


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("MAIL_FROM", "Bewerbungen <bewerbungen@example.ch>")
    monkeypatch.setenv("APP_URL", "https://bewerbungen.example.ch")


class Outbox:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    def __call__(self, mail_from, to, subject, text, html):
        if self.fail:
            raise RuntimeError("Resend 422: invalid from")
        self.sent.append({"from": mail_from, "to": to, "subject": subject, "text": text, "html": html})


def add_application(db, company, days_ago, event_type="sent", archived=False):
    application = models.Application(company=company, mail_tag=company[:4].lower(), archived=archived)
    application.events.append(models.Event(type=event_type, occurred_at=AFTER - timedelta(days=days_ago)))
    db.add(application)
    db.commit()
    return application


def add_user(db, name, email, wants=True):
    db.add(models.User(name=name, pin_hash="x", email=email, wants_reminders=wants))
    db.commit()


def test_build_digest(db):
    add_application(db, "Migros", 15)
    add_application(db, "Coop", 3)
    add_application(db, "Lidl", 30, archived=True)
    add_application(db, "Aldi", 30, event_type="rejection")
    db.add(models.Email(message_id="<x@y>", received_at=AFTER))
    db.commit()
    digest = reminders.build_digest(db, AFTER)
    assert [(d.company, d.days) for d in digest.due] == [("Migros", 15)]
    assert digest.inbox_count == 1
    assert not digest.empty


def test_render_with_and_without_links(db):
    application = add_application(db, "Migros", 15)
    digest = reminders.build_digest(db, AFTER)
    subject, text, html = reminders.render(digest, "https://bewerbungen.example.ch/")
    assert subject == "Bewerbungen: 1 Nachfrage fällig"
    url = f"https://bewerbungen.example.ch/bewerbungen/{application.id}"
    assert url in text
    assert url in html
    assert "15 Tage seit dem letzten Kontakt" in text
    _, text_without_links, _ = reminders.render(digest, "")
    assert "http" not in text_without_links


def test_run_once_not_configured(db):
    assert reminders.run_once(db, AFTER, send=Outbox()) == "not_configured"


def test_run_once_sends_once_per_day(db, configured):
    add_user(db, "Papa", "papa@example.ch")
    add_user(db, "Sohn", "sohn@example.ch")
    add_user(db, "Mama", "mama@example.ch", wants=False)
    add_application(db, "Migros", 15)
    outbox = Outbox()
    assert reminders.run_once(db, MORNING, send=outbox) == "not_due"
    assert reminders.run_once(db, AFTER, send=outbox) == "sent"
    assert outbox.sent[0]["to"] == ["papa@example.ch", "sohn@example.ch"]
    assert outbox.sent[0]["from"] == "Bewerbungen <bewerbungen@example.ch>"
    assert reminders.run_once(db, AFTER + timedelta(hours=1), send=outbox) == "not_due"
    assert len(outbox.sent) == 1
    settings = get_settings(db)
    assert settings.last_reminder_date == "2026-10-15"
    assert settings.last_reminder_sent_at == AFTER


def test_empty_digest_sends_nothing(db, configured):
    add_user(db, "Papa", "papa@example.ch")
    outbox = Outbox()
    assert reminders.run_once(db, AFTER, send=outbox) == "empty"
    assert outbox.sent == []
    assert get_settings(db).last_reminder_date == "2026-10-15"


def test_no_recipients(db, configured):
    add_application(db, "Migros", 15)
    assert reminders.run_once(db, AFTER, send=Outbox()) == "no_recipients"


def test_failure_is_recorded_and_retried(db, configured):
    add_user(db, "Papa", "papa@example.ch")
    add_application(db, "Migros", 15)
    assert reminders.run_once(db, AFTER, send=Outbox(fail=True)) == "error"
    settings = get_settings(db)
    assert "Resend 422" in settings.last_reminder_error
    assert settings.last_reminder_date is None
    assert settings.last_reminder_attempt_at == AFTER

    assert reminders.run_once(db, AFTER + timedelta(minutes=15), send=Outbox()) == "sent"
    assert get_settings(db).last_reminder_error is None


def test_next_run(db, configured):
    settings = get_settings(db)
    assert reminders.next_run(settings, MORNING) == local(2026, 10, 15, 7, 0)
    settings.last_reminder_date = "2026-10-15"
    assert reminders.next_run(settings, AFTER) == local(2026, 10, 16, 7, 0)


def test_send_test_requires_email(db, configured):
    admin = db.query(models.User).filter_by(name="Admin").one()
    with pytest.raises(ValueError):
        reminders.send_test(db, admin, AFTER, send=Outbox())
    admin.email = "papa@example.ch"
    db.commit()
    outbox = Outbox()
    reminders.send_test(db, admin, AFTER, send=outbox)
    assert outbox.sent[0]["subject"].startswith("[Test] ")
    assert outbox.sent[0]["to"] == ["papa@example.ch"]


def test_resend_send_posts_json(monkeypatch, configured):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"id": "1"}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data)
        return FakeResponse()

    monkeypatch.setattr(reminders.urllib.request, "urlopen", fake_urlopen)
    reminders.resend_send("a@example.ch", ["b@example.ch"], "Betreff", "Text", "<p>Text</p>")
    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["headers"]["Authorization"] == "Bearer re_test"
    assert captured["body"] == {
        "from": "a@example.ch",
        "to": ["b@example.ch"],
        "subject": "Betreff",
        "text": "Text",
        "html": "<p>Text</p>",
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_reminders.py`
Expected: ERROR at collection, `ImportError: cannot import name 'reminders' from 'app'`.

- [ ] **Step 3: Implement `backend/app/reminders.py`**

```python
import asyncio
import html
import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from sqlalchemy.orm import Session, selectinload

from . import config, database, models
from . import status as st
from .settings_store import get_settings
from .timeutil import to_local, to_utc, utcnow

logger = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"
CHECK_INTERVAL_SECONDS = 15 * 60

# (from, to, subject, text, html)
Sender = Callable[[str, list[str], str, str, str], None]


def is_configured() -> bool:
    return bool(config.env("RESEND_API_KEY") and config.env("MAIL_FROM"))


def resend_send(mail_from: str, to: list[str], subject: str, text: str, html_body: str) -> None:
    payload = json.dumps({"from": mail_from, "to": to, "subject": subject, "text": text, "html": html_body})
    request = urllib.request.Request(
        RESEND_URL,
        data=payload.encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {config.env('RESEND_API_KEY')}",
            "Content-Type": "application/json",
            # Resend sits behind Cloudflare, which rejects requests without a User-Agent
            "User-Agent": "family-job-tracking",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise RuntimeError(f"Resend {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Resend nicht erreichbar: {exc.reason}") from exc


@dataclass
class DueItem:
    id: int
    company: str
    position: str
    days: int


@dataclass
class Digest:
    due: list[DueItem]
    inbox_count: int

    @property
    def empty(self) -> bool:
        return not self.due and self.inbox_count == 0


def build_digest(db: Session, now: datetime) -> Digest:
    settings = get_settings(db)
    applications = (
        db.query(models.Application)
        .options(selectinload(models.Application.events))
        .filter(models.Application.archived.is_(False))
        .all()
    )
    due = []
    for application in applications:
        status = st.derive_status(application.events)
        if st.is_due(status, application.archived, application.events, settings.followup_days, now):
            last = st.latest(application.events)
            due.append(
                DueItem(application.id, application.company, application.position, st.days_since(last.occurred_at, now))
            )
    due.sort(key=lambda item: item.days, reverse=True)
    inbox_count = (
        db.query(models.Email)
        .filter(models.Email.application_id.is_(None), models.Email.dismissed.is_(False))
        .count()
    )
    return Digest(due, inbox_count)


def _plural(count: int, one: str, many: str) -> str:
    return one if count == 1 else many


def render(digest: Digest, app_url: str) -> tuple[str, str, str]:
    """(subject, plain text, HTML) of the reminder e-mail, in German."""
    base = app_url.rstrip("/")

    def link(path: str) -> str:
        return f"{base}{path}" if base else ""

    due_count = len(digest.due)
    if due_count:
        subject = f"Bewerbungen: {due_count} {_plural(due_count, 'Nachfrage', 'Nachfragen')} fällig"
    elif digest.inbox_count:
        subject = f"Bewerbungen: {digest.inbox_count} {_plural(digest.inbox_count, 'Mail', 'Mails')} im Posteingang"
    else:
        subject = "Bewerbungen: nichts fällig"

    text_lines: list[str] = []
    html_parts: list[str] = []
    if digest.due:
        text_lines.append("Nachfragen fällig:")
        html_parts.append("<h2>Nachfragen fällig</h2><ul>")
        for item in digest.due:
            title = item.company + (f" – {item.position}" if item.position else "")
            age = f"{item.days} {_plural(item.days, 'Tag', 'Tage')} seit dem letzten Kontakt"
            url = link(f"/bewerbungen/{item.id}")
            text_lines.append(f"- {title} ({age})" + (f": {url}" if url else ""))
            label = html.escape(title)
            if url:
                html_parts.append(f'<li><a href="{html.escape(url)}">{label}</a> ({age})</li>')
            else:
                html_parts.append(f"<li>{label} ({age})</li>")
        text_lines.append("")
        html_parts.append("</ul>")
    if digest.inbox_count:
        message = (
            f"{digest.inbox_count} {_plural(digest.inbox_count, 'Mail wartet', 'Mails warten')} "
            "im Posteingang auf die Zuordnung."
        )
        url = link("/posteingang")
        text_lines.append(message + (f" {url}" if url else ""))
        anchor = f' <a href="{html.escape(url)}">Zum Posteingang</a>' if url else ""
        html_parts.append(f"<p>{html.escape(message)}{anchor}</p>")
    if digest.empty:
        text_lines.append("Zurzeit ist nichts fällig.")
        html_parts.append("<p>Zurzeit ist nichts fällig.</p>")
    return subject, "\n".join(text_lines).strip() + "\n", "".join(html_parts)


def recipients(db: Session) -> list[str]:
    users = (
        db.query(models.User)
        .filter(models.User.wants_reminders.is_(True), models.User.email.isnot(None))
        .order_by(models.User.name)
        .all()
    )
    return [u.email for u in users]


def _reminder_time(settings: models.Settings) -> time:
    hours, minutes = settings.reminder_time.split(":")
    return time(int(hours), int(minutes))


def _is_due_today(settings: models.Settings, now: datetime) -> bool:
    local_now = to_local(now)
    already_done = settings.last_reminder_date == local_now.date().isoformat()
    return not already_done and local_now.time() >= _reminder_time(settings)


def next_run(settings: models.Settings, now: datetime) -> datetime:
    """When the next digest goes out (naive UTC); now, if today's is still pending."""
    if _is_due_today(settings, now):
        return now
    local_now = to_local(now)
    day = local_now.date()
    if settings.last_reminder_date == day.isoformat():
        day += timedelta(days=1)
    return to_utc(datetime.combine(day, _reminder_time(settings), tzinfo=config.tz()))


def run_once(db: Session, now: datetime, send: Sender | None = None) -> str:
    """Send today's digest if it is time and it has not been sent yet."""
    if not is_configured():
        return "not_configured"
    settings = get_settings(db)
    if not _is_due_today(settings, now):
        return "not_due"
    today = to_local(now).date().isoformat()
    digest = build_digest(db, now)
    to = recipients(db)
    if digest.empty or not to:
        settings.last_reminder_date = today
        db.commit()
        return "empty" if digest.empty else "no_recipients"
    subject, text, html_body = render(digest, config.env("APP_URL"))
    settings.last_reminder_attempt_at = now
    try:
        (send or resend_send)(config.env("MAIL_FROM"), to, subject, text, html_body)
    except Exception as exc:
        logger.error("Sending the reminder failed: %s", exc)
        settings.last_reminder_error = str(exc)[:500]
        db.commit()
        return "error"
    settings.last_reminder_date = today
    settings.last_reminder_sent_at = now
    settings.last_reminder_error = None
    db.commit()
    return "sent"


def send_test(db: Session, user: models.User, now: datetime, send: Sender | None = None) -> None:
    """Send the current digest to one user right away (Einstellungen > Test-Erinnerung)."""
    if not is_configured():
        raise ValueError("Erinnerungen sind nicht konfiguriert (RESEND_API_KEY und MAIL_FROM fehlen)")
    if not user.email:
        raise ValueError("Bitte zuerst eine E-Mail-Adresse speichern")
    subject, text, html_body = render(build_digest(db, now), config.env("APP_URL"))
    settings = get_settings(db)
    settings.last_reminder_attempt_at = now
    try:
        (send or resend_send)(config.env("MAIL_FROM"), [user.email], f"[Test] {subject}", text, html_body)
    except Exception as exc:
        settings.last_reminder_error = str(exc)[:500]
        db.commit()
        raise
    settings.last_reminder_sent_at = now
    settings.last_reminder_error = None
    db.commit()


def _tick() -> None:
    with database.SessionLocal() as db:
        result = run_once(db, utcnow())
    if result == "sent":
        logger.info("Sent the daily reminder")


async def loop() -> None:
    """Background task: check every 15 minutes whether the daily digest is due."""
    while True:
        try:
            await asyncio.to_thread(_tick)
        except Exception:
            logger.exception("Reminder check failed")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
```

- [ ] **Step 4: Start the loop from `backend/app/main.py`**

Replace `backend/app/main.py` with:
```python
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import applications_api, config, database, inbox_api, models, reminders, users_api
from .seed import seed_admin
from .settings_store import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

models.Base.metadata.create_all(bind=database.engine)

# A fresh database gets the settings row and a first admin to log in with
with database.SessionLocal() as _db:
    get_settings(_db)
    _initial_pin = seed_admin(_db)
if _initial_pin:
    logger.warning("Created user 'Admin' with INITIAL PIN %s. Log in and change it in Einstellungen.", _initial_pin)

# Both integrations are optional; say which ones are on, but never refuse to start
logger.info(
    "Inbound e-mail: %s", "configured" if config.env("INBOUND_SECRET") else "not configured (INBOUND_SECRET empty)"
)
logger.info(
    "Reminder e-mails: %s",
    "configured" if reminders.is_configured() else "not configured (RESEND_API_KEY or MAIL_FROM empty)",
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(reminders.loop()) if reminders.is_configured() else None
    yield
    if task is not None:
        task.cancel()


app = FastAPI(title="Family Job Tracking API", version="0.1.0", lifespan=lifespan)
app.include_router(users_api.router, prefix="/api")
app.include_router(applications_api.router, prefix="/api")
app.include_router(inbox_api.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `venv/bin/pytest`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend tests
git commit -m "feat(backend): daily reminder digest via Resend

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Settings, integration status and export

**Files:**
- Create: `backend/app/integrations.py`, `backend/app/export.py`, `backend/app/settings_api.py`, `tests/test_settings.py`
- Modify: `backend/app/schemas.py` (append), `backend/app/main.py` (include router)

**Interfaces:**
- Consumes: `reminders.is_configured`, `reminders.recipients`, `reminders.next_run`, `reminders.send_test`, `get_settings`, `timeutil.iso`.
- Produces:
  - `integrations.status(db, now) -> {"inbound": Integration, "reminders": Integration}`. An Integration is `{"state": "not_configured" | "waiting" | "ok" | "error", "details": {...}, "warnings": [str]}`.
    - Inbound details: `address`, `last_received_at`, `last_error`.
    - Reminder details: `mail_from`, `recipients`, `next_run`, `last_attempt_at`, `last_sent_at`, `last_error`.
  - `export.build_zip(db) -> Path` (a temporary file).
  - Endpoints: `GET /api/settings` → `{followup_days, reminder_time, inbound_address}`, `PATCH /api/settings` (admin), `GET /api/integrations`, `POST /api/integrations/reminders/test` (204, 400 for setup problems, 502 when sending fails), `GET /api/export` (zip).

- [ ] **Step 1: Write the failing tests**

`tests/test_settings.py`:
```python
import io
import zipfile

from fastapi.testclient import TestClient

from app import reminders
from app.main import app as fastapi_app
from helpers import add_event, create_application, create_user, login
from mails import BROKEN_MAIL, INBOUND_SECRET, build_mail, post_mail


def integrations(client, headers):
    response = client.get("/api/integrations", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def configure_resend(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("MAIL_FROM", "bewerbungen@example.ch")


def test_app_starts_without_optional_integrations():
    with TestClient(fastapi_app) as client:
        assert client.get("/health").status_code == 200


def test_settings_defaults_and_admin_update(client, admin_headers):
    defaults = client.get("/api/settings", headers=admin_headers).json()
    assert defaults == {"followup_days": 10, "reminder_time": "07:00", "inbound_address": ""}
    response = client.patch(
        "/api/settings",
        json={"followup_days": 7, "reminder_time": "18:30", "inbound_address": " Bewerbungen@Example.ch "},
        headers=admin_headers,
    )
    assert response.json() == {"followup_days": 7, "reminder_time": "18:30", "inbound_address": "bewerbungen@example.ch"}


def test_settings_validation_and_permissions(client, admin_headers):
    for body in ({"followup_days": 0}, {"reminder_time": "25:00"}, {"inbound_address": "keine-adresse"}):
        assert client.patch("/api/settings", json=body, headers=admin_headers).status_code == 422
    create_user(client, admin_headers, "Sohn")
    son = login(client, "Sohn", "5678")
    assert client.get("/api/settings", headers=son).status_code == 200
    assert client.patch("/api/settings", json={"followup_days": 5}, headers=son).status_code == 403


def test_integrations_not_configured(client, admin_headers):
    data = integrations(client, admin_headers)
    assert data["inbound"]["state"] == "not_configured"
    assert data["reminders"]["state"] == "not_configured"
    assert data["reminders"]["details"]["next_run"] is None


def test_inbound_integration_states(client, admin_headers, monkeypatch):
    monkeypatch.setenv("INBOUND_SECRET", INBOUND_SECRET)
    assert integrations(client, admin_headers)["inbound"]["state"] == "waiting"
    post_mail(client, BROKEN_MAIL)
    broken = integrations(client, admin_headers)["inbound"]
    assert broken["state"] == "error"
    assert broken["details"]["last_error"]
    post_mail(client, build_mail())
    ok = integrations(client, admin_headers)["inbound"]
    assert ok["state"] == "ok"
    assert ok["details"]["last_received_at"] is not None


def test_reminder_integration_states(client, admin_headers, monkeypatch):
    configure_resend(monkeypatch)
    data = integrations(client, admin_headers)["reminders"]
    assert data["state"] == "ok"
    assert data["details"]["mail_from"] == "bewerbungen@example.ch"
    assert data["details"]["next_run"] is not None
    assert any("APP_URL" in w for w in data["warnings"])
    assert any("Niemand" in w for w in data["warnings"])

    client.patch("/api/me", json={"email": "papa@example.ch", "wants_reminders": True}, headers=admin_headers)

    def failing(*args):
        raise RuntimeError("Resend 401: bad key")

    monkeypatch.setattr(reminders, "resend_send", failing)
    response = client.post("/api/integrations/reminders/test", headers=admin_headers)
    assert response.status_code == 502
    assert "Resend 401" in response.json()["detail"]
    data = integrations(client, admin_headers)["reminders"]
    assert data["state"] == "error"
    assert "Resend 401" in data["details"]["last_error"]
    assert data["details"]["recipients"] == ["papa@example.ch"]


def test_test_reminder(client, admin_headers, monkeypatch):
    assert client.post("/api/integrations/reminders/test", headers=admin_headers).status_code == 400
    configure_resend(monkeypatch)
    assert client.post("/api/integrations/reminders/test", headers=admin_headers).status_code == 400
    client.patch("/api/me", json={"email": "papa@example.ch"}, headers=admin_headers)
    sent = []
    monkeypatch.setattr(reminders, "resend_send", lambda *args: sent.append(args))
    assert client.post("/api/integrations/reminders/test", headers=admin_headers).status_code == 204
    assert sent[0][1] == ["papa@example.ch"]


def test_export_zip(client, admin_headers):
    application = create_application(client, admin_headers, "Migros")
    add_event(client, admin_headers, application["id"], files=[("files", ("cv.pdf", b"x", "application/pdf"))])
    response = client.get("/api/export", headers=admin_headers)
    assert response.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = set(archive.namelist())
    assert {"users.csv", "applications.csv", "events.csv", "emails.csv", "attachments.csv"} <= names
    assert any(name.startswith("files/migros/") for name in names)
    users_csv = archive.read("users.csv").decode()
    assert "Admin" in users_csv
    assert "pin_hash" not in users_csv
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_settings.py`
Expected: FAIL. The settings and integrations requests return 404 and the `assert ... == 200` checks fail.

- [ ] **Step 3: Append `SettingsPatch` to `backend/app/schemas.py`**

```python


class SettingsPatch(BaseModel):
    followup_days: int | None = Field(None, ge=1, le=365)
    reminder_time: str | None = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    inbound_address: str | None = None

    @field_validator("inbound_address")
    @classmethod
    def check_inbound_address(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return clean_email(value) or ""
```

- [ ] **Step 4: Implement `backend/app/integrations.py`**

```python
from datetime import datetime

from sqlalchemy.orm import Session

from . import config, models, reminders
from .settings_store import get_settings
from .timeutil import iso


def _inbound(settings: models.Settings) -> dict:
    if not config.env("INBOUND_SECRET"):
        state = "not_configured"
    elif settings.last_inbound_error:
        state = "error"
    elif settings.last_inbound_at:
        state = "ok"
    else:
        state = "waiting"
    warnings = []
    if not settings.inbound_address:
        warnings.append("Die Eingangsadresse ist in den Einstellungen nicht gesetzt.")
    return {
        "state": state,
        "details": {
            "address": settings.inbound_address or None,
            "last_received_at": iso(settings.last_inbound_at),
            "last_error": settings.last_inbound_error,
        },
        "warnings": warnings,
    }


def _reminders(db: Session, settings: models.Settings, now: datetime) -> dict:
    configured = reminders.is_configured()
    if not configured:
        state = "not_configured"
    elif settings.last_reminder_error:
        state = "error"
    else:
        state = "ok"
    to = reminders.recipients(db)
    warnings = []
    if configured and not config.env("APP_URL"):
        warnings.append("APP_URL fehlt: die Erinnerungen enthalten keine Links.")
    if configured and not to:
        warnings.append("Niemand hat Erinnerungen eingeschaltet.")
    return {
        "state": state,
        "details": {
            "mail_from": config.env("MAIL_FROM") or None,
            "recipients": to,
            "next_run": iso(reminders.next_run(settings, now)) if configured else None,
            "last_attempt_at": iso(settings.last_reminder_attempt_at),
            "last_sent_at": iso(settings.last_reminder_sent_at),
            "last_error": settings.last_reminder_error,
        },
        "warnings": warnings,
    }


def status(db: Session, now: datetime) -> dict:
    settings = get_settings(db)
    return {"inbound": _inbound(settings), "reminders": _reminders(db, settings, now)}
```

- [ ] **Step 5: Implement `backend/app/export.py`**

```python
import csv
import io
import os
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from . import config, models
from .timeutil import iso

TABLES = [
    ("users", models.User),
    ("applications", models.Application),
    ("events", models.Event),
    ("emails", models.Email),
    ("attachments", models.Attachment),
]
# Login secrets stay out of the export
EXCLUDED_COLUMNS = {"pin_hash", "failed_logins", "locked_until"}


def _cell(value):
    if isinstance(value, datetime):
        return iso(value)
    return "" if value is None else value


def build_zip(db: Session) -> Path:
    """All tables as CSV plus the files folder, in a temporary ZIP the caller deletes."""
    fd, name = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    with zipfile.ZipFile(name, "w", zipfile.ZIP_DEFLATED) as archive:
        for table, model in TABLES:
            columns = [c.name for c in model.__table__.columns if c.name not in EXCLUDED_COLUMNS]
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(columns)
            for row in db.query(model).order_by(model.id):
                writer.writerow([_cell(getattr(row, column)) for column in columns])
            archive.writestr(f"{table}.csv", buffer.getvalue())
        root = config.files_dir()
        if root.exists():
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    archive.write(path, f"files/{path.relative_to(root).as_posix()}")
    return Path(name)
```

- [ ] **Step 6: Implement `backend/app/settings_api.py` and wire it up**

```python
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from . import auth, export, integrations, models, reminders, schemas
from .database import get_db
from .settings_store import get_settings
from .timeutil import local_date, utcnow

router = APIRouter(tags=["settings"], dependencies=[Depends(auth.get_current_user)])


def _settings_out(settings: models.Settings) -> dict:
    return {
        "followup_days": settings.followup_days,
        "reminder_time": settings.reminder_time,
        "inbound_address": settings.inbound_address,
    }


@router.get("/settings")
def read_settings(db: Session = Depends(get_db)):
    return _settings_out(get_settings(db))


@router.patch("/settings")
def update_settings(
    body: schemas.SettingsPatch, _admin: models.User = Depends(auth.require_admin), db: Session = Depends(get_db)
):
    settings = get_settings(db)
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(settings, key, value)
    db.commit()
    return _settings_out(settings)


@router.get("/integrations")
def read_integrations(db: Session = Depends(get_db)):
    return integrations.status(db, utcnow())


@router.post("/integrations/reminders/test", status_code=204)
def send_test_reminder(user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    try:
        reminders.send_test(db, user, utcnow())
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"Versand fehlgeschlagen: {exc}")


@router.get("/export")
def export_data(db: Session = Depends(get_db)):
    path = export.build_zip(db)
    filename = f"bewerbungen-export-{local_date(utcnow()).isoformat()}.zip"
    return FileResponse(
        path, media_type="application/zip", filename=filename, background=BackgroundTask(os.unlink, path)
    )
```

In `backend/app/main.py` add `settings_api` to the `from . import ...` line and add after the inbox router:
```python
app.include_router(settings_api.router, prefix="/api")
```

- [ ] **Step 7: Run the whole backend suite**

Run: `venv/bin/pytest`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add backend tests
git commit -m "feat(backend): settings, integration status and data export

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Frontend scaffold, login, layout and overview

**Files:**
- Create: `frontend/package.json`, `frontend/index.html`, `frontend/vite.config.ts`, `frontend/src/main.tsx`, `frontend/src/index.css`, `frontend/src/api.ts`, `frontend/src/types.ts`, `frontend/src/labels.ts`, `frontend/src/ui.ts`, `frontend/src/ToastContext.tsx`, `frontend/src/AuthContext.tsx`, `frontend/src/App.tsx`, `frontend/src/components/PinInput.tsx`, `frontend/src/components/Layout.tsx`, `frontend/src/components/StatusBadge.tsx`, `frontend/src/components/ApplicationForm.tsx`, `frontend/src/pages/Login.tsx`, `frontend/src/pages/Overview.tsx`
- Copy from `$PEER/frontend`: `eslint.config.js`, `postcss.config.js`, `tailwind.config.js`, `tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json`

**Interfaces:**
- Consumes: the backend JSON shapes from Tasks 2, 4, 7 and 9.
- Produces (used by Tasks 11–13):
  - `api` (axios instance with the bearer token) and `errorMessage(error, fallback?) -> string`, `downloadFile(url, filename) -> Promise<void>` from `src/api.ts`.
  - Types in `src/types.ts`: `Status`, `EventType`, `Channel`, `User`, `Attachment`, `EmailItem`, `TimelineEvent`, `ApplicationSummary`, `ApplicationDetail`, `ApplicationFormValues`, `Dashboard`, `InboxItem`, `AppSettings`, `IntegrationState`, `Integration`, `Integrations`.
  - From `src/labels.ts`: `STATUS_LABELS`, `STATUS_COLORS`, `EVENT_LABELS`, `EVENT_TYPES`, `CHANNEL_LABELS`, `formatDate()`, `formatDateTime()`, `formatSize()`.
  - From `src/ui.ts`: `FIELD`, `INPUT`, `BUTTON`, `BUTTON_SECONDARY`, `BUTTON_DANGER`, `CARD`, `EMPTY_APPLICATION`.
  - `useToast() -> (text, kind?: 'error' | 'success') => void`; `useAuth() -> {user, isLoading, login, logout, refreshUser}`.
  - Components: `PinInput`, `StatusBadge`, `ApplicationForm`, `Layout`.
  - In `App.tsx`, later tasks add their `<Route>` inside the authenticated layout route, right after `<Route index element={<Overview />} />`.

There are no frontend unit tests (spec: type-check, lint and build in CI). Each frontend task is verified with `npm run lint && npm run build` and a manual check against the running backend.

- [ ] **Step 1: Create the project files**

```bash
PEER=/home/andreas/work/family-budget-dashboard
mkdir -p frontend/src/components/settings frontend/src/pages
cp $PEER/frontend/{eslint.config.js,postcss.config.js,tailwind.config.js,tsconfig.json,tsconfig.app.json,tsconfig.node.json} frontend/
```

`frontend/package.json`:
```json
{
  "name": "jobs-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "lint": "eslint . --report-unused-disable-directives --max-warnings 0",
    "preview": "vite preview",
    "type-check": "tsc -b"
  },
  "dependencies": {
    "axios": "^1.20.0",
    "react": "^19.3.0",
    "react-dom": "^19.3.0",
    "react-router-dom": "^7.18.4"
  },
  "devDependencies": {
    "@eslint/js": "^10.0.1",
    "@tailwindcss/postcss": "^4.3.3",
    "@types/node": "^26.6.5",
    "@types/react": "^19.3.0",
    "@types/react-dom": "^19.3.0",
    "@vitejs/plugin-react": "^6.1.2",
    "autoprefixer": "^10.6.1",
    "eslint": "^10.12.0",
    "eslint-plugin-react-hooks": "^7.1.1",
    "eslint-plugin-react-refresh": "^0.5.7",
    "globals": "^17.13.0",
    "postcss": "^8.5.30",
    "tailwindcss": "^4.1.18",
    "typescript": "~5.9.3",
    "typescript-eslint": "^8.71.2",
    "vite": "^8.3.4"
  }
}
```

`frontend/index.html`:
```html
<!doctype html>
<html lang="de">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="theme-color" content="#0f172a" />
    <title>Bewerbungen</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`frontend/vite.config.ts`:
```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development, forward API calls to the backend on port 8000 (in Docker, nginx does this)
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:8000' } },
})
```

`frontend/src/index.css`:
```css
@import "tailwindcss";

body {
  margin: 0;
  min-height: 100vh;
  background: #0f172a;
  color: #f1f5f9;
  font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  -webkit-font-smoothing: antialiased;
}
```

`frontend/src/main.tsx`:
```tsx
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App.tsx';

createRoot(document.getElementById('root')!).render(
    <StrictMode>
        <App />
    </StrictMode>,
);
```

```bash
cd frontend && npm install && cd ..
```
Expected: `package-lock.json` is created and there are no errors.

- [ ] **Step 2: Write the shared modules**

`frontend/src/types.ts`:
```ts
export type Status = 'draft' | 'open' | 'in_contact' | 'closed_offer' | 'closed_rejection' | 'closed_withdrawn';
export type EventType =
    | 'sent' | 'followed_up' | 'reply_received' | 'mail_sent' | 'mail_received' | 'call'
    | 'interview' | 'trial' | 'offer' | 'rejection' | 'withdrawn' | 'note';
export type Channel = 'email' | 'portal' | 'post' | 'in_person' | 'other';

export interface User {
    id: number;
    name: string;
    is_admin: boolean;
    email: string | null;
    wants_reminders: boolean;
}

export interface Attachment {
    id: number;
    filename: string;
    content_type: string;
    size: number;
    path: string;
}

export interface EmailItem {
    id: number;
    message_id: string;
    from_addr: string;
    to_addrs: string;
    subject: string;
    body_text: string;
    received_at: string;
    application_id: number | null;
    parse_error: string | null;
    attachments: Attachment[];
}

export interface TimelineEvent {
    id: number;
    occurred_at: string;
    type: EventType;
    note: string;
    created_by_name: string | null;
    email: EmailItem | null;
    attachments: Attachment[];
}

export interface ApplicationSummary {
    id: number;
    company: string;
    position: string;
    location: string;
    status: Status;
    archived: boolean;
    due: boolean;
    last_event_type: EventType | null;
    last_event_at: string | null;
    days_since_last: number | null;
    mail_tag: string;
}

export interface ApplicationFormValues {
    company: string;
    position: string;
    location: string;
    contact_name: string;
    contact_email: string;
    contact_phone: string;
    posting_url: string;
    channel: Channel;
    notes: string;
}

export interface ApplicationDetail extends ApplicationSummary, ApplicationFormValues {
    created_at: string;
    created_by_name: string | null;
    mail_address: string | null;
    events: TimelineEvent[];
}

export interface Dashboard {
    counts: Record<Status, number>;
    due: ApplicationSummary[];
    inbox_count: number;
}

export interface InboxItem extends EmailItem {
    suggestion: { id: number; company: string; position: string } | null;
}

export interface AppSettings {
    followup_days: number;
    reminder_time: string;
    inbound_address: string;
}

export type IntegrationState = 'not_configured' | 'waiting' | 'ok' | 'error';

export interface Integration {
    state: IntegrationState;
    details: Record<string, string | number | string[] | null>;
    warnings: string[];
}

export interface Integrations {
    inbound: Integration;
    reminders: Integration;
}
```

`frontend/src/labels.ts`:
```ts
import type { Channel, EventType, Status } from './types';

export const STATUS_LABELS: Record<Status, string> = {
    draft: 'Entwurf',
    open: 'Offen',
    in_contact: 'In Kontakt',
    closed_offer: 'Zusage',
    closed_rejection: 'Absage',
    closed_withdrawn: 'Zurückgezogen',
};

export const STATUS_COLORS: Record<Status, string> = {
    draft: 'bg-slate-600',
    open: 'bg-blue-600',
    in_contact: 'bg-amber-600',
    closed_offer: 'bg-emerald-600',
    closed_rejection: 'bg-red-700',
    closed_withdrawn: 'bg-slate-500',
};

export const EVENT_LABELS: Record<EventType, string> = {
    sent: 'Bewerbung gesendet',
    followed_up: 'Nachgefragt',
    reply_received: 'Antwort erhalten',
    mail_sent: 'Mail gesendet',
    mail_received: 'Mail erhalten',
    call: 'Telefonat',
    interview: 'Vorstellungsgespräch',
    trial: 'Schnupperlehre/Probetag',
    offer: 'Zusage',
    rejection: 'Absage',
    withdrawn: 'Zurückgezogen',
    note: 'Notiz',
};

export const EVENT_TYPES = Object.keys(EVENT_LABELS) as EventType[];

export const CHANNEL_LABELS: Record<Channel, string> = {
    email: 'E-Mail',
    portal: 'Portal',
    post: 'Post',
    in_person: 'Persönlich',
    other: 'Andere',
};

export function formatDate(iso: string | null): string {
    return iso ? new Date(iso).toLocaleDateString('de-CH') : '–';
}

export function formatDateTime(iso: string | null): string {
    return iso ? new Date(iso).toLocaleString('de-CH', { dateStyle: 'medium', timeStyle: 'short' }) : '–';
}

export function formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
```

`frontend/src/ui.ts`:
```ts
import type { ApplicationFormValues } from './types';

// Shared Tailwind classes, so forms and cards look the same everywhere
export const FIELD =
    'rounded-lg border border-slate-600 bg-slate-800/60 p-2 text-slate-100 focus:border-blue-400 focus:outline-none';
export const INPUT = `${FIELD} w-full`;
export const BUTTON =
    'rounded-lg bg-blue-600 px-4 py-2 font-semibold text-white hover:bg-blue-500 disabled:opacity-50';
export const BUTTON_SECONDARY =
    'rounded-lg border border-slate-600 px-4 py-2 text-slate-200 hover:bg-slate-800 disabled:opacity-50';
export const BUTTON_DANGER =
    'rounded-lg border border-red-700 px-4 py-2 text-red-300 hover:bg-red-900/40 disabled:opacity-50';
export const CARD = 'rounded-xl border border-slate-800 bg-slate-900/60 p-4';

export const EMPTY_APPLICATION: ApplicationFormValues = {
    company: '',
    position: '',
    location: '',
    contact_name: '',
    contact_email: '',
    contact_phone: '',
    posting_url: '',
    channel: 'email',
    notes: '',
};
```

`frontend/src/api.ts`:
```ts
import axios from 'axios';

// Same origin: Vite (dev) or nginx (Docker) forwards /api to the backend
const api = axios.create();

api.interceptors.request.use((config) => {
    const token = localStorage.getItem('token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// Expired or invalid token: drop it and go back to the login page
api.interceptors.response.use(
    (response) => response,
    (error) => {
        const isLogin = error.config?.url === '/api/token';
        if (error.response?.status === 401 && !isLogin && localStorage.getItem('token')) {
            localStorage.removeItem('token');
            window.location.href = '/login';
        }
        return Promise.reject(error);
    },
);

// Turn an API error into a message for the user (FastAPI sends `detail` as text or a list of validation errors)
export function errorMessage(error: unknown, fallback = 'Etwas ist schiefgelaufen'): string {
    if (!axios.isAxiosError(error)) return fallback;
    const detail = error.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail.length > 0) return detail.map((d: { msg: string }) => d.msg).join('; ');
    return fallback;
}

// Files need the login token, so fetch them with axios and hand the browser a temporary link
export async function downloadFile(url: string, filename: string): Promise<void> {
    const response = await api.get<Blob>(url, { responseType: 'blob' });
    const href = URL.createObjectURL(response.data);
    const link = document.createElement('a');
    link.href = href;
    link.download = filename;
    link.click();
    setTimeout(() => URL.revokeObjectURL(href), 1000);
}

export default api;
```

`frontend/src/ToastContext.tsx`:
```tsx
import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';

type ToastKind = 'error' | 'success';
type ShowToast = (text: string, kind?: ToastKind) => void;

interface Toast {
    id: number;
    text: string;
    kind: ToastKind;
}

const ToastContext = createContext<ShowToast>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
    const [toasts, setToasts] = useState<Toast[]>([]);

    const show = useCallback<ShowToast>((text, kind = 'error') => {
        const id = Date.now() + Math.random();
        setToasts((current) => [...current, { id, text, kind }]);
        setTimeout(() => setToasts((current) => current.filter((t) => t.id !== id)), 5000);
    }, []);

    return (
        <ToastContext.Provider value={show}>
            {children}
            <div className="fixed inset-x-4 bottom-4 z-50 flex flex-col items-center gap-2">
                {toasts.map((t) => (
                    <div
                        key={t.id}
                        role="status"
                        className={`rounded-lg px-4 py-2 text-sm text-white shadow-lg ${
                            t.kind === 'error' ? 'bg-red-700' : 'bg-emerald-700'
                        }`}
                    >
                        {t.text}
                    </div>
                ))}
            </div>
        </ToastContext.Provider>
    );
}

// eslint-disable-next-line react-refresh/only-export-components -- the hook belongs with its provider
export const useToast = () => useContext(ToastContext);
```

`frontend/src/AuthContext.tsx`:
```tsx
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import api from './api';
import type { User } from './types';

interface AuthContextType {
    user: User | null;
    isLoading: boolean;
    login: (name: string, pin: string) => Promise<void>;
    logout: () => void;
    refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
    const [user, setUser] = useState<User | null>(null);
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        const checkAuth = async () => {
            if (localStorage.getItem('token')) {
                try {
                    setUser((await api.get<User>('/api/me')).data);
                } catch {
                    localStorage.removeItem('token');
                }
            }
            setIsLoading(false);
        };
        checkAuth();
    }, []);

    // Reload the current user after their settings change on the server
    const refreshUser = async () => {
        setUser((await api.get<User>('/api/me')).data);
    };

    const login = async (name: string, pin: string) => {
        const response = await api.post<{ access_token: string }>('/api/token', { name, pin });
        localStorage.setItem('token', response.data.access_token);
        await refreshUser();
    };

    const logout = () => {
        localStorage.removeItem('token');
        setUser(null);
    };

    return (
        <AuthContext.Provider value={{ user, isLoading, login, logout, refreshUser }}>{children}</AuthContext.Provider>
    );
};

// eslint-disable-next-line react-refresh/only-export-components -- the hook belongs with its provider
export const useAuth = () => {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
};
```

- [ ] **Step 3: Write the components**

`frontend/src/components/PinInput.tsx`:
```tsx
import { useState } from 'react';
import { INPUT } from '../ui';

interface PinInputProps {
    id: string;
    value: string;
    onChange: (pin: string) => void;
    placeholder?: string;
    autoComplete?: 'current-password' | 'new-password';
    autoFocus?: boolean;
}

// Masked PIN field with a show/hide toggle; only accepts digits (4–8)
export default function PinInput({
    id,
    value,
    onChange,
    placeholder = 'PIN',
    autoComplete = 'current-password',
    autoFocus = false,
}: PinInputProps) {
    const [show, setShow] = useState(false);
    return (
        <div className="relative">
            <input
                id={id}
                type={show ? 'text' : 'password'}
                inputMode="numeric"
                autoComplete={autoComplete}
                autoFocus={autoFocus}
                maxLength={8}
                value={value}
                onChange={(e) => {
                    if (/^\d*$/.test(e.target.value)) onChange(e.target.value);
                }}
                placeholder={placeholder}
                className={`${INPUT} pr-12 tracking-widest placeholder:tracking-normal`}
            />
            <button
                type="button"
                onClick={() => setShow(!show)}
                aria-label={show ? 'PIN verbergen' : 'PIN anzeigen'}
                className="absolute inset-y-0 right-0 px-3 text-slate-400 hover:text-white"
            >
                {show ? '🙈' : '👁️'}
            </button>
        </div>
    );
}
```

`frontend/src/components/StatusBadge.tsx`:
```tsx
import { STATUS_COLORS, STATUS_LABELS } from '../labels';
import type { Status } from '../types';

export default function StatusBadge({ status }: { status: Status }) {
    return (
        <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-semibold text-white ${STATUS_COLORS[status]}`}>
            {STATUS_LABELS[status]}
        </span>
    );
}
```

`frontend/src/components/ApplicationForm.tsx`:
```tsx
import { useState, type FormEvent } from 'react';
import { errorMessage } from '../api';
import { CHANNEL_LABELS } from '../labels';
import { useToast } from '../ToastContext';
import type { ApplicationFormValues, Channel } from '../types';
import { BUTTON, BUTTON_SECONDARY, INPUT } from '../ui';

type TextField = Exclude<keyof ApplicationFormValues, 'channel' | 'notes'>;

const FIELDS: [TextField, string, string][] = [
    ['company', 'Firma *', 'text'],
    ['position', 'Stelle', 'text'],
    ['location', 'Ort', 'text'],
    ['contact_name', 'Ansprechperson', 'text'],
    ['contact_email', 'E-Mail der Ansprechperson', 'email'],
    ['contact_phone', 'Telefon', 'tel'],
    ['posting_url', 'Link zum Inserat', 'url'],
];

interface Props {
    initial: ApplicationFormValues;
    submitLabel: string;
    onSubmit: (values: ApplicationFormValues) => Promise<void>;
    onCancel: () => void;
}

export default function ApplicationForm({ initial, submitLabel, onSubmit, onCancel }: Props) {
    const toast = useToast();
    const [values, setValues] = useState(initial);
    const [busy, setBusy] = useState(false);

    const set = (key: keyof ApplicationFormValues, value: string) => setValues({ ...values, [key]: value });

    const submit = async (e: FormEvent) => {
        e.preventDefault();
        setBusy(true);
        try {
            await onSubmit(values);
        } catch (err) {
            toast(errorMessage(err, 'Speichern fehlgeschlagen'));
        } finally {
            setBusy(false);
        }
    };

    return (
        <form onSubmit={submit} className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
                {FIELDS.map(([key, label, type]) => (
                    <label key={key} className="block text-sm">
                        <span className="mb-1 block text-slate-400">{label}</span>
                        <input
                            type={type}
                            required={key === 'company'}
                            value={values[key]}
                            onChange={(e) => set(key, e.target.value)}
                            className={INPUT}
                        />
                    </label>
                ))}
                <label className="block text-sm">
                    <span className="mb-1 block text-slate-400">Kanal</span>
                    <select
                        value={values.channel}
                        onChange={(e) => set('channel', e.target.value as Channel)}
                        className={INPUT}
                    >
                        {Object.entries(CHANNEL_LABELS).map(([value, label]) => (
                            <option key={value} value={value}>
                                {label}
                            </option>
                        ))}
                    </select>
                </label>
            </div>
            <label className="block text-sm">
                <span className="mb-1 block text-slate-400">Notizen</span>
                <textarea rows={3} value={values.notes} onChange={(e) => set('notes', e.target.value)} className={INPUT} />
            </label>
            <div className="flex gap-2">
                <button type="submit" disabled={busy} className={BUTTON}>
                    {submitLabel}
                </button>
                <button type="button" onClick={onCancel} className={BUTTON_SECONDARY}>
                    Abbrechen
                </button>
            </div>
        </form>
    );
}
```

`frontend/src/components/Layout.tsx`:
```tsx
import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import api from '../api';
import { useAuth } from '../AuthContext';
import type { Dashboard, Integrations } from '../types';

const linkClass = ({ isActive }: { isActive: boolean }) =>
    `rounded-lg px-3 py-2 text-sm ${isActive ? 'bg-slate-700 text-white' : 'text-slate-300 hover:text-white'}`;

export default function Layout() {
    const { user, logout } = useAuth();
    const location = useLocation();
    const [inboxCount, setInboxCount] = useState(0);
    const [integrationError, setIntegrationError] = useState(false);

    // Refresh the badges whenever the page changes
    useEffect(() => {
        let cancelled = false;
        Promise.all([api.get<Dashboard>('/api/dashboard'), api.get<Integrations>('/api/integrations')])
            .then(([dashboard, integrations]) => {
                if (cancelled) return;
                setInboxCount(dashboard.data.inbox_count);
                setIntegrationError(
                    integrations.data.inbound.state === 'error' || integrations.data.reminders.state === 'error',
                );
            })
            .catch(() => {});
        return () => {
            cancelled = true;
        };
    }, [location.pathname]);

    return (
        <div className="min-h-screen">
            <header className="sticky top-0 z-10 border-b border-slate-800 bg-slate-900/90 backdrop-blur">
                <div className="mx-auto flex max-w-4xl flex-wrap items-center gap-2 px-4 py-3">
                    <span className="mr-auto font-bold">Bewerbungen</span>
                    <nav className="flex gap-1">
                        <NavLink to="/" end className={linkClass}>
                            Übersicht
                        </NavLink>
                        <NavLink to="/posteingang" className={linkClass}>
                            Posteingang
                            {inboxCount > 0 && (
                                <span className="ml-1 rounded-full bg-blue-600 px-2 text-xs text-white">{inboxCount}</span>
                            )}
                        </NavLink>
                        <NavLink to="/einstellungen" className={linkClass}>
                            Einstellungen
                            {integrationError && (
                                <span
                                    className="ml-1 inline-block h-2 w-2 rounded-full bg-red-500"
                                    title="Eine Integration meldet einen Fehler"
                                />
                            )}
                        </NavLink>
                    </nav>
                    <button type="button" onClick={logout} className="text-sm text-slate-400 hover:text-white">
                        {user?.name} abmelden
                    </button>
                </div>
            </header>
            <main className="mx-auto max-w-4xl px-4 py-6">
                <Outlet />
            </main>
        </div>
    );
}
```

- [ ] **Step 4: Write the pages and the app**

`frontend/src/pages/Login.tsx`:
```tsx
import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import api, { errorMessage } from '../api';
import { useAuth } from '../AuthContext';
import PinInput from '../components/PinInput';
import { useToast } from '../ToastContext';
import { BUTTON, CARD } from '../ui';

interface PublicUser {
    id: number;
    name: string;
}

export default function Login() {
    const { login } = useAuth();
    const navigate = useNavigate();
    const toast = useToast();
    const [users, setUsers] = useState<PublicUser[]>([]);
    const [name, setName] = useState('');
    const [pin, setPin] = useState('');
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        api.get<PublicUser[]>('/api/users/public')
            .then((response) => setUsers(response.data))
            .catch(() => toast('Benutzer konnten nicht geladen werden'));
    }, [toast]);

    const submit = async (e: FormEvent) => {
        e.preventDefault();
        setBusy(true);
        try {
            await login(name, pin);
            navigate('/');
        } catch (err) {
            toast(errorMessage(err, 'Anmeldung fehlgeschlagen'));
            setPin('');
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="flex min-h-screen items-center justify-center p-4">
            <form onSubmit={submit} className={`${CARD} w-full max-w-sm space-y-4`}>
                <h1 className="text-center text-2xl font-bold">Bewerbungen</h1>
                <div className="grid grid-cols-2 gap-2">
                    {users.map((u) => (
                        <button
                            key={u.id}
                            type="button"
                            onClick={() => {
                                setName(u.name);
                                setPin('');
                            }}
                            className={`rounded-lg border p-3 font-semibold ${
                                name === u.name ? 'border-blue-400 bg-blue-600/30' : 'border-slate-700 hover:bg-slate-800'
                            }`}
                        >
                            {u.name}
                        </button>
                    ))}
                </div>
                {name && (
                    <>
                        <label htmlFor="pin" className="block text-sm text-slate-400">
                            PIN für {name}
                        </label>
                        <PinInput id="pin" value={pin} onChange={setPin} autoFocus />
                        <button type="submit" disabled={busy || pin.length < 4} className={`${BUTTON} w-full`}>
                            Anmelden
                        </button>
                    </>
                )}
            </form>
        </div>
    );
}
```

`frontend/src/pages/Overview.tsx`:
```tsx
import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import api, { errorMessage } from '../api';
import ApplicationForm from '../components/ApplicationForm';
import StatusBadge from '../components/StatusBadge';
import { EVENT_LABELS, STATUS_LABELS, formatDate } from '../labels';
import { useToast } from '../ToastContext';
import type { ApplicationDetail, ApplicationFormValues, ApplicationSummary, Dashboard, Status } from '../types';
import { BUTTON, CARD, EMPTY_APPLICATION, FIELD } from '../ui';

const TILES: { status: Status; label: string }[] = [
    { status: 'open', label: 'Offen' },
    { status: 'in_contact', label: 'In Kontakt' },
    { status: 'closed_offer', label: 'Zusagen' },
    { status: 'closed_rejection', label: 'Absagen' },
];

function ApplicationRow({ item }: { item: ApplicationSummary }) {
    return (
        <Link
            to={`/bewerbungen/${item.id}`}
            className="flex items-center gap-3 rounded-lg border border-slate-800 bg-slate-900/60 p-3 hover:border-slate-600"
        >
            <div className="min-w-0 flex-1">
                <div className="truncate font-semibold">
                    {item.company}
                    {item.archived && <span className="ml-2 text-xs font-normal text-slate-500">archiviert</span>}
                </div>
                <div className="truncate text-sm text-slate-400">
                    {item.position || '–'}
                    {item.location && ` · ${item.location}`}
                </div>
            </div>
            <div className="text-right text-xs text-slate-400">
                <StatusBadge status={item.status} />
                <div className="mt-1">
                    {item.last_event_type
                        ? `${EVENT_LABELS[item.last_event_type]}, ${formatDate(item.last_event_at)}`
                        : 'noch nichts erfasst'}
                </div>
            </div>
        </Link>
    );
}

export default function Overview() {
    const navigate = useNavigate();
    const toast = useToast();
    const [dashboard, setDashboard] = useState<Dashboard | null>(null);
    const [items, setItems] = useState<ApplicationSummary[]>([]);
    const [status, setStatus] = useState<Status | ''>('');
    const [query, setQuery] = useState('');
    const [includeArchived, setIncludeArchived] = useState(false);
    const [creating, setCreating] = useState(false);

    useEffect(() => {
        api.get<Dashboard>('/api/dashboard')
            .then((response) => setDashboard(response.data))
            .catch((e) => toast(errorMessage(e)));
    }, [toast]);

    useEffect(() => {
        // Wait until typing in the search field pauses
        const timer = setTimeout(() => {
            api.get<ApplicationSummary[]>('/api/applications', {
                params: { status: status || undefined, q: query || undefined, include_archived: includeArchived },
            })
                .then((response) => setItems(response.data))
                .catch((e) => toast(errorMessage(e)));
        }, 250);
        return () => clearTimeout(timer);
    }, [status, query, includeArchived, toast]);

    const create = async (values: ApplicationFormValues) => {
        const response = await api.post<ApplicationDetail>('/api/applications', values);
        navigate(`/bewerbungen/${response.data.id}`);
    };

    return (
        <div className="space-y-6">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {TILES.map((tile) => (
                    <button
                        key={tile.status}
                        type="button"
                        onClick={() => setStatus(status === tile.status ? '' : tile.status)}
                        className={`${CARD} text-left ${status === tile.status ? 'border-blue-400' : ''}`}
                    >
                        <div className="text-3xl font-bold">{dashboard?.counts[tile.status] ?? '–'}</div>
                        <div className="text-sm text-slate-400">{tile.label}</div>
                    </button>
                ))}
            </div>

            {dashboard && dashboard.due.length > 0 && (
                <section className={`${CARD} border-amber-600/60`}>
                    <h2 className="mb-2 font-bold text-amber-300">Nachfragen fällig</h2>
                    <ul className="space-y-1 text-sm">
                        {dashboard.due.map((d) => (
                            <li key={d.id}>
                                <Link to={`/bewerbungen/${d.id}`} className="hover:underline">
                                    {d.company}
                                    {d.position && ` – ${d.position}`}
                                </Link>
                                <span className="text-slate-400"> · seit {d.days_since_last} Tagen nichts mehr</span>
                            </li>
                        ))}
                    </ul>
                </section>
            )}

            <section className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                    <h2 className="mr-auto text-xl font-bold">Bewerbungen</h2>
                    <button type="button" onClick={() => setCreating(true)} className={BUTTON}>
                        Neue Bewerbung
                    </button>
                </div>
                {creating && (
                    <div className={CARD}>
                        <ApplicationForm
                            initial={EMPTY_APPLICATION}
                            submitLabel="Erstellen"
                            onSubmit={create}
                            onCancel={() => setCreating(false)}
                        />
                    </div>
                )}
                <div className="flex flex-wrap items-center gap-2">
                    <input
                        type="search"
                        placeholder="Suchen…"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        className={`${FIELD} min-w-40 flex-1`}
                    />
                    <select
                        value={status}
                        onChange={(e) => setStatus(e.target.value as Status | '')}
                        className={FIELD}
                    >
                        <option value="">Alle Status</option>
                        {Object.entries(STATUS_LABELS).map(([value, label]) => (
                            <option key={value} value={value}>
                                {label}
                            </option>
                        ))}
                    </select>
                    <label className="flex items-center gap-2 text-sm text-slate-300">
                        <input
                            type="checkbox"
                            checked={includeArchived}
                            onChange={(e) => setIncludeArchived(e.target.checked)}
                        />
                        Archivierte zeigen
                    </label>
                </div>
                <div className="space-y-2">
                    {items.map((item) => (
                        <ApplicationRow key={item.id} item={item} />
                    ))}
                    {items.length === 0 && <p className="text-slate-400">Keine Bewerbungen gefunden.</p>}
                </div>
            </section>
        </div>
    );
}
```

`frontend/src/App.tsx`:
```tsx
import type { ReactElement } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './AuthContext';
import Layout from './components/Layout';
import Login from './pages/Login';
import Overview from './pages/Overview';
import { ToastProvider } from './ToastContext';

function RequireAuth({ children }: { children: ReactElement }) {
    const { user, isLoading } = useAuth();
    if (isLoading) return <p className="p-6 text-slate-400">Laden…</p>;
    return user ? children : <Navigate to="/login" replace />;
}

export default function App() {
    return (
        <ToastProvider>
            <AuthProvider>
                <BrowserRouter>
                    <Routes>
                        <Route path="/login" element={<Login />} />
                        <Route
                            element={
                                <RequireAuth>
                                    <Layout />
                                </RequireAuth>
                            }
                        >
                            <Route index element={<Overview />} />
                        </Route>
                        <Route path="*" element={<Navigate to="/" replace />} />
                    </Routes>
                </BrowserRouter>
            </AuthProvider>
        </ToastProvider>
    );
}
```

- [ ] **Step 5: Lint and build**

Run: `cd frontend && npm run lint && npm run build; cd ..`
Expected: no lint errors or warnings; `vite build` writes `frontend/dist`. If ESLint's `react-hooks/set-state-in-effect` rule fires, the cause is a `setState` call made synchronously in an effect body. Move it into the `.then()` callback or after an `await`, as the code above already does.

- [ ] **Step 6: Manual check against the backend**

```bash
mkdir -p data/dev && DATA_DIR=data/dev DATABASE_URL=sqlite:///data/dev/dev.db INITIAL_ADMIN_PIN=1234 \
  SECRET_KEY=dev venv/bin/uvicorn app.main:app --app-dir backend --port 8000 &
cd frontend && npm run dev
```
Open `http://localhost:5173`. Log in as Admin/1234 and create a "Migros" application. You land on `/bewerbungen/<id>`, which still redirects to `/` until Task 11. Back on the overview, the application is listed as "Entwurf". Stop both servers afterwards.

- [ ] **Step 7: Commit**

```bash
git add frontend
git commit -m "feat(frontend): login, layout and overview of applications

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Application detail page with timeline

**Files:**
- Create: `frontend/src/components/EventForm.tsx`, `frontend/src/components/Timeline.tsx`, `frontend/src/pages/ApplicationPage.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `api`, `errorMessage`, `downloadFile`, `ApplicationForm`, `StatusBadge`, labels, `ui` classes, `useToast`.
- Produces: the route `/bewerbungen/:id`.

- [ ] **Step 1: Write `frontend/src/components/EventForm.tsx`**

```tsx
import { useRef, useState, type FormEvent } from 'react';
import api, { errorMessage } from '../api';
import { EVENT_LABELS, EVENT_TYPES } from '../labels';
import { useToast } from '../ToastContext';
import type { EventType } from '../types';
import { BUTTON, BUTTON_SECONDARY, INPUT } from '../ui';

// The current local time in the format of <input type="datetime-local">
function nowForInput(): string {
    const d = new Date();
    d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
    return d.toISOString().slice(0, 16);
}

interface Props {
    applicationId: number;
    defaultType: EventType;
    onSaved: () => void;
}

export default function EventForm({ applicationId, defaultType, onSaved }: Props) {
    const toast = useToast();
    const fileInput = useRef<HTMLInputElement>(null);
    const [open, setOpen] = useState(false);
    const [type, setType] = useState<EventType>(defaultType);
    const [when, setWhen] = useState(nowForInput);
    const [note, setNote] = useState('');
    const [files, setFiles] = useState<File[]>([]);
    const [busy, setBusy] = useState(false);

    const start = () => {
        setType(defaultType);
        setWhen(nowForInput());
        setNote('');
        setFiles([]);
        setOpen(true);
    };

    const submit = async (e: FormEvent) => {
        e.preventDefault();
        setBusy(true);
        const form = new FormData();
        form.append('type', type);
        form.append('occurred_at', new Date(when).toISOString());
        form.append('note', note);
        files.forEach((file) => form.append('files', file));
        try {
            await api.post(`/api/applications/${applicationId}/events`, form);
            setOpen(false);
            onSaved();
        } catch (err) {
            toast(errorMessage(err, 'Speichern fehlgeschlagen'));
        } finally {
            setBusy(false);
        }
    };

    if (!open) {
        return (
            <button type="button" onClick={start} className={BUTTON}>
                + Ereignis
            </button>
        );
    }

    return (
        <form onSubmit={submit} className="space-y-3 rounded-xl border border-slate-700 p-4">
            <div className="grid gap-3 sm:grid-cols-2">
                <label className="block text-sm">
                    <span className="mb-1 block text-slate-400">Was ist passiert?</span>
                    <select value={type} onChange={(e) => setType(e.target.value as EventType)} className={INPUT}>
                        {EVENT_TYPES.map((t) => (
                            <option key={t} value={t}>
                                {EVENT_LABELS[t]}
                            </option>
                        ))}
                    </select>
                </label>
                <label className="block text-sm">
                    <span className="mb-1 block text-slate-400">Wann?</span>
                    <input
                        type="datetime-local"
                        required
                        value={when}
                        onChange={(e) => setWhen(e.target.value)}
                        className={INPUT}
                    />
                </label>
            </div>
            <label className="block text-sm">
                <span className="mb-1 block text-slate-400">Notiz</span>
                <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} className={INPUT} />
            </label>
            <div className="text-sm">
                <input
                    ref={fileInput}
                    type="file"
                    multiple
                    className="hidden"
                    onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
                />
                <button type="button" onClick={() => fileInput.current?.click()} className={BUTTON_SECONDARY}>
                    Dateien wählen
                </button>
                {files.length > 0 && <span className="ml-2 text-slate-400">{files.map((f) => f.name).join(', ')}</span>}
            </div>
            <div className="flex gap-2">
                <button type="submit" disabled={busy} className={BUTTON}>
                    Speichern
                </button>
                <button type="button" onClick={() => setOpen(false)} className={BUTTON_SECONDARY}>
                    Abbrechen
                </button>
            </div>
        </form>
    );
}
```

- [ ] **Step 2: Write `frontend/src/components/Timeline.tsx`**

```tsx
import { useState } from 'react';
import api, { downloadFile, errorMessage } from '../api';
import { EVENT_LABELS, formatDateTime, formatSize } from '../labels';
import { useToast } from '../ToastContext';
import type { Attachment, TimelineEvent } from '../types';

function AttachmentList({ attachments, onDelete }: { attachments: Attachment[]; onDelete: (a: Attachment) => void }) {
    const toast = useToast();
    if (attachments.length === 0) return null;
    return (
        <ul className="mt-2 space-y-1 text-sm">
            {attachments.map((a) => (
                <li key={a.id} className="flex items-center gap-2">
                    <button
                        type="button"
                        className="truncate text-blue-300 hover:underline"
                        onClick={() =>
                            downloadFile(`/api/attachments/${a.id}`, a.filename).catch((e) =>
                                toast(errorMessage(e, 'Download fehlgeschlagen')),
                            )
                        }
                    >
                        📎 {a.filename}
                    </button>
                    <span className="text-xs text-slate-500">{formatSize(a.size)}</span>
                    <button
                        type="button"
                        onClick={() => onDelete(a)}
                        aria-label={`${a.filename} löschen`}
                        className="text-xs text-slate-500 hover:text-red-400"
                    >
                        ✕
                    </button>
                </li>
            ))}
        </ul>
    );
}

function TimelineItem({ event, onChanged }: { event: TimelineEvent; onChanged: () => void }) {
    const toast = useToast();
    const [busy, setBusy] = useState(false);
    const email = event.email;

    const run = async (action: () => Promise<unknown>) => {
        setBusy(true);
        try {
            await action();
            onChanged();
        } catch (e) {
            toast(errorMessage(e, 'Löschen fehlgeschlagen'));
        } finally {
            setBusy(false);
        }
    };
    const deleteEvent = () => {
        if (window.confirm('Dieses Ereignis löschen?')) run(() => api.delete(`/api/events/${event.id}`));
    };
    const deleteAttachment = (a: Attachment) => {
        if (window.confirm(`${a.filename} löschen?`)) run(() => api.delete(`/api/attachments/${a.id}`));
    };

    return (
        <li className="relative border-l-2 border-slate-700 pb-5 pl-4">
            <span className="absolute -left-[7px] top-1.5 h-3 w-3 rounded-full bg-blue-500" />
            <div className="flex flex-wrap items-baseline gap-x-2">
                <span className="font-semibold">{EVENT_LABELS[event.type]}</span>
                <span className="text-sm text-slate-400">{formatDateTime(event.occurred_at)}</span>
                <span className="text-xs text-slate-500">
                    {event.created_by_name ? `von ${event.created_by_name}` : email ? 'per E-Mail' : ''}
                </span>
                <button
                    type="button"
                    disabled={busy}
                    onClick={deleteEvent}
                    className="ml-auto text-xs text-slate-500 hover:text-red-400"
                >
                    löschen
                </button>
            </div>
            {event.note && <p className="mt-1 whitespace-pre-wrap text-sm">{event.note}</p>}
            <AttachmentList attachments={event.attachments} onDelete={deleteAttachment} />
            {email && (
                <details className="mt-2 rounded-lg bg-slate-800/50 p-2 text-sm">
                    <summary className="cursor-pointer text-slate-300">Mail anzeigen</summary>
                    <div className="mt-2 space-y-1 text-xs text-slate-400">
                        <div>Von: {email.from_addr || '–'}</div>
                        <div>An: {email.to_addrs || '–'}</div>
                    </div>
                    <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap font-sans text-sm">{email.body_text}</pre>
                    <AttachmentList attachments={email.attachments} onDelete={deleteAttachment} />
                    <button
                        type="button"
                        className="mt-2 text-xs text-blue-300 hover:underline"
                        onClick={() =>
                            downloadFile(`/api/emails/${email.id}/raw`, `mail-${email.id}.eml`).catch((e) =>
                                toast(errorMessage(e, 'Download fehlgeschlagen')),
                            )
                        }
                    >
                        Originalmail (.eml) herunterladen
                    </button>
                </details>
            )}
        </li>
    );
}

export default function Timeline({ events, onChanged }: { events: TimelineEvent[]; onChanged: () => void }) {
    if (events.length === 0) return <p className="text-slate-400">Noch keine Ereignisse.</p>;
    return (
        <ol className="ml-2">
            {events.map((event) => (
                <TimelineItem key={event.id} event={event} onChanged={onChanged} />
            ))}
        </ol>
    );
}
```

- [ ] **Step 3: Write `frontend/src/pages/ApplicationPage.tsx`**

```tsx
import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import api, { errorMessage } from '../api';
import ApplicationForm from '../components/ApplicationForm';
import EventForm from '../components/EventForm';
import StatusBadge from '../components/StatusBadge';
import Timeline from '../components/Timeline';
import { CHANNEL_LABELS } from '../labels';
import { useToast } from '../ToastContext';
import type { ApplicationDetail, ApplicationFormValues } from '../types';
import { BUTTON_DANGER, BUTTON_SECONDARY, CARD } from '../ui';

function toFormValues(a: ApplicationDetail): ApplicationFormValues {
    return {
        company: a.company,
        position: a.position,
        location: a.location,
        contact_name: a.contact_name,
        contact_email: a.contact_email,
        contact_phone: a.contact_phone,
        posting_url: a.posting_url,
        channel: a.channel,
        notes: a.notes,
    };
}

export default function ApplicationPage() {
    const { id } = useParams();
    const navigate = useNavigate();
    const toast = useToast();
    const [application, setApplication] = useState<ApplicationDetail | null>(null);
    const [editing, setEditing] = useState(false);

    const load = useCallback(async () => {
        try {
            setApplication((await api.get<ApplicationDetail>(`/api/applications/${id}`)).data);
        } catch (e) {
            toast(errorMessage(e, 'Bewerbung nicht gefunden'));
        }
    }, [id, toast]);

    useEffect(() => {
        load();
    }, [load]);

    if (!application) return <p className="text-slate-400">Laden…</p>;

    const save = async (values: ApplicationFormValues) => {
        await api.patch(`/api/applications/${application.id}`, values);
        setEditing(false);
        await load();
    };

    const toggleArchived = async () => {
        try {
            await api.patch(`/api/applications/${application.id}`, { archived: !application.archived });
            await load();
        } catch (e) {
            toast(errorMessage(e));
        }
    };

    const remove = async () => {
        if (!window.confirm(`„${application.company}“ mit allen Ereignissen, Mails und Dateien löschen?`)) return;
        try {
            await api.delete(`/api/applications/${application.id}`);
            navigate('/');
        } catch (e) {
            toast(errorMessage(e));
        }
    };

    const copyAddress = () => {
        const address = application.mail_address;
        // The clipboard API only exists on https (or localhost)
        if (!address || !navigator.clipboard) {
            toast('Kopieren nicht möglich – bitte von Hand markieren');
            return;
        }
        navigator.clipboard.writeText(address).then(
            () => toast('Adresse kopiert', 'success'),
            () => toast('Kopieren nicht möglich – bitte von Hand markieren'),
        );
    };

    const details: [string, string][] = [
        ['Ort', application.location],
        ['Ansprechperson', application.contact_name],
        ['E-Mail', application.contact_email],
        ['Telefon', application.contact_phone],
        ['Kanal', CHANNEL_LABELS[application.channel]],
    ];
    const postingIsLink = /^https?:\/\//i.test(application.posting_url);

    return (
        <div className="space-y-6">
            <div className="flex flex-wrap items-start gap-3">
                <div className="mr-auto">
                    <h1 className="text-2xl font-bold">{application.company}</h1>
                    <p className="text-slate-400">{application.position || 'Stelle nicht angegeben'}</p>
                </div>
                <StatusBadge status={application.status} />
            </div>

            {application.mail_address ? (
                <div className={`${CARD} flex flex-wrap items-center gap-2 text-sm`}>
                    <span className="text-slate-400">Mails an / BCC:</span>
                    <code className="break-all">{application.mail_address}</code>
                    <button type="button" onClick={copyAddress} className="ml-auto text-blue-300 hover:underline">
                        Kopieren
                    </button>
                </div>
            ) : (
                <p className="text-sm text-slate-500">
                    Für eine eigene Mail-Adresse pro Bewerbung die Eingangsadresse in den Einstellungen setzen.
                </p>
            )}

            <section className={CARD}>
                {editing ? (
                    <ApplicationForm
                        initial={toFormValues(application)}
                        submitLabel="Speichern"
                        onSubmit={save}
                        onCancel={() => setEditing(false)}
                    />
                ) : (
                    <>
                        <dl className="grid gap-2 text-sm sm:grid-cols-2">
                            {details
                                .filter(([, value]) => value)
                                .map(([label, value]) => (
                                    <div key={label}>
                                        <dt className="text-slate-500">{label}</dt>
                                        <dd className="break-words">{value}</dd>
                                    </div>
                                ))}
                            {application.posting_url && (
                                <div>
                                    <dt className="text-slate-500">Inserat</dt>
                                    <dd className="break-all">
                                        {postingIsLink ? (
                                            <a
                                                href={application.posting_url}
                                                target="_blank"
                                                rel="noreferrer"
                                                className="text-blue-300 hover:underline"
                                            >
                                                {application.posting_url}
                                            </a>
                                        ) : (
                                            application.posting_url
                                        )}
                                    </dd>
                                </div>
                            )}
                        </dl>
                        {application.notes && <p className="mt-3 whitespace-pre-wrap text-sm">{application.notes}</p>}
                        <div className="mt-4 flex flex-wrap gap-2">
                            <button type="button" onClick={() => setEditing(true)} className={BUTTON_SECONDARY}>
                                Bearbeiten
                            </button>
                            <button type="button" onClick={toggleArchived} className={BUTTON_SECONDARY}>
                                {application.archived ? 'Wiederherstellen' : 'Archivieren'}
                            </button>
                            <button type="button" onClick={remove} className={BUTTON_DANGER}>
                                Löschen
                            </button>
                        </div>
                    </>
                )}
            </section>

            <section className="space-y-4">
                <h2 className="text-xl font-bold">Verlauf</h2>
                <EventForm
                    applicationId={application.id}
                    defaultType={application.events.length ? 'followed_up' : 'sent'}
                    onSaved={load}
                />
                <Timeline events={application.events} onChanged={load} />
            </section>
        </div>
    );
}
```

- [ ] **Step 4: Add the route**

In `frontend/src/App.tsx` add `import ApplicationPage from './pages/ApplicationPage';` and, after `<Route index element={<Overview />} />`:
```tsx
                            <Route path="bewerbungen/:id" element={<ApplicationPage />} />
```

- [ ] **Step 5: Lint, build and check by hand**

Run: `cd frontend && npm run lint && npm run build; cd ..`
Expected: clean.

Start backend and dev server as in Task 10 Step 6. Open an application and do the following:
- Add "Bewerbung gesendet" with a PDF. The status becomes "Offen", the file downloads with its original name, and it lies under `data/dev/files/<firma>/`.
- Edit the master data and archive the application.
- Delete the event.

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "feat(frontend): application page with timeline, events and files

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Inbox page

**Files:**
- Create: `frontend/src/pages/Inbox.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `GET /api/inbox`, `GET /api/applications`, `POST /api/inbox/{id}/assign|create-application|dismiss`.
- Produces: the route `/posteingang`.

- [ ] **Step 1: Write `frontend/src/pages/Inbox.tsx`**

```tsx
import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import api, { downloadFile, errorMessage } from '../api';
import { EVENT_LABELS, formatDateTime, formatSize } from '../labels';
import { useToast } from '../ToastContext';
import type { ApplicationSummary, EventType, InboxItem } from '../types';
import { BUTTON, BUTTON_SECONDARY, CARD, FIELD } from '../ui';

const MAIL_EVENT_TYPES: EventType[] = [
    'mail_received',
    'mail_sent',
    'reply_received',
    'sent',
    'followed_up',
    'interview',
    'offer',
    'rejection',
];

// "hr.migros.ch" -> "Migros", as a starting point for a new application
function guessCompany(fromAddr: string): string {
    const parts = (fromAddr.split('@')[1] ?? '').split('.');
    const name = parts.length >= 2 ? parts[parts.length - 2] : '';
    return name ? name.charAt(0).toUpperCase() + name.slice(1) : '';
}

interface CardProps {
    item: InboxItem;
    applications: ApplicationSummary[];
    onDone: () => void;
}

function InboxCard({ item, applications, onDone }: CardProps) {
    const toast = useToast();
    const navigate = useNavigate();
    const [applicationId, setApplicationId] = useState(item.suggestion ? String(item.suggestion.id) : '');
    const [eventType, setEventType] = useState<EventType | ''>('');
    const [creating, setCreating] = useState(false);
    const [company, setCompany] = useState(() => guessCompany(item.from_addr));
    const [position, setPosition] = useState('');
    const [busy, setBusy] = useState(false);

    const run = async (action: () => Promise<void>) => {
        setBusy(true);
        try {
            await action();
        } catch (e) {
            toast(errorMessage(e));
        } finally {
            setBusy(false);
        }
    };

    const assign = () =>
        run(async () => {
            await api.post(`/api/inbox/${item.id}/assign`, {
                application_id: Number(applicationId),
                event_type: eventType || null,
            });
            toast('Mail zugeordnet', 'success');
            onDone();
        });

    const create = () =>
        run(async () => {
            const response = await api.post<{ application_id: number }>(
                `/api/inbox/${item.id}/create-application`,
                { company, position },
            );
            navigate(`/bewerbungen/${response.data.application_id}`);
        });

    const dismiss = () => {
        if (!window.confirm('Diese Mail verwerfen?')) return;
        run(async () => {
            await api.post(`/api/inbox/${item.id}/dismiss`);
            onDone();
        });
    };

    return (
        <article className={`${CARD} space-y-3`}>
            <header>
                <div className="font-semibold">{item.subject || '(kein Betreff)'}</div>
                <div className="text-sm text-slate-400">
                    {item.from_addr || 'unbekannter Absender'} · {formatDateTime(item.received_at)}
                </div>
                {item.parse_error && (
                    <div className="mt-1 text-sm text-red-300">Konnte nicht gelesen werden: {item.parse_error}</div>
                )}
            </header>
            {item.body_text && (
                <details className="text-sm">
                    <summary className="cursor-pointer text-slate-300">Inhalt anzeigen</summary>
                    <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap font-sans">{item.body_text}</pre>
                </details>
            )}
            {item.attachments.length > 0 && (
                <ul className="text-sm">
                    {item.attachments.map((a) => (
                        <li key={a.id}>
                            <button
                                type="button"
                                className="text-blue-300 hover:underline"
                                onClick={() =>
                                    downloadFile(`/api/attachments/${a.id}`, a.filename).catch((e) =>
                                        toast(errorMessage(e)),
                                    )
                                }
                            >
                                📎 {a.filename}
                            </button>{' '}
                            <span className="text-xs text-slate-500">{formatSize(a.size)}</span>
                        </li>
                    ))}
                </ul>
            )}
            {item.suggestion && (
                <p className="text-sm text-amber-300">
                    Gehört vermutlich zu{' '}
                    <Link to={`/bewerbungen/${item.suggestion.id}`} className="underline">
                        {item.suggestion.company}
                    </Link>
                </p>
            )}
            <div className="flex flex-wrap gap-2">
                <select
                    value={applicationId}
                    onChange={(e) => setApplicationId(e.target.value)}
                    className={`${FIELD} min-w-40 flex-1`}
                >
                    <option value="">Bewerbung wählen…</option>
                    {applications.map((a) => (
                        <option key={a.id} value={a.id}>
                            {a.company}
                            {a.position ? ` – ${a.position}` : ''}
                        </option>
                    ))}
                </select>
                <select
                    value={eventType}
                    onChange={(e) => setEventType(e.target.value as EventType | '')}
                    className={FIELD}
                >
                    <option value="">Typ automatisch</option>
                    {MAIL_EVENT_TYPES.map((t) => (
                        <option key={t} value={t}>
                            {EVENT_LABELS[t]}
                        </option>
                    ))}
                </select>
                <button type="button" disabled={busy || !applicationId} onClick={assign} className={BUTTON}>
                    Zuordnen
                </button>
            </div>
            {creating ? (
                <div className="flex flex-wrap gap-2">
                    <input
                        placeholder="Firma"
                        value={company}
                        onChange={(e) => setCompany(e.target.value)}
                        className={`${FIELD} min-w-32 flex-1`}
                    />
                    <input
                        placeholder="Stelle"
                        value={position}
                        onChange={(e) => setPosition(e.target.value)}
                        className={`${FIELD} min-w-32 flex-1`}
                    />
                    <button type="button" disabled={busy || !company.trim()} onClick={create} className={BUTTON}>
                        Erstellen
                    </button>
                    <button type="button" onClick={() => setCreating(false)} className={BUTTON_SECONDARY}>
                        Abbrechen
                    </button>
                </div>
            ) : (
                <div className="flex flex-wrap gap-2">
                    <button type="button" onClick={() => setCreating(true)} className={BUTTON_SECONDARY}>
                        Neue Bewerbung daraus erstellen
                    </button>
                    <button type="button" disabled={busy} onClick={dismiss} className={BUTTON_SECONDARY}>
                        Verwerfen
                    </button>
                </div>
            )}
        </article>
    );
}

export default function Inbox() {
    const toast = useToast();
    const [items, setItems] = useState<InboxItem[] | null>(null);
    const [applications, setApplications] = useState<ApplicationSummary[]>([]);

    const load = useCallback(async () => {
        try {
            const [inbox, apps] = await Promise.all([
                api.get<InboxItem[]>('/api/inbox'),
                api.get<ApplicationSummary[]>('/api/applications'),
            ]);
            setItems(inbox.data);
            setApplications([...apps.data].sort((a, b) => a.company.localeCompare(b.company, 'de')));
        } catch (e) {
            toast(errorMessage(e));
        }
    }, [toast]);

    useEffect(() => {
        load();
    }, [load]);

    if (items === null) return <p className="text-slate-400">Laden…</p>;

    return (
        <div className="space-y-4">
            <h1 className="text-2xl font-bold">Posteingang</h1>
            <p className="text-sm text-slate-400">
                Mails ohne Bewerbungs-Kennung landen hier. Ordne sie einer Bewerbung zu oder verwirf sie.
            </p>
            {items.length === 0 && <p className="text-slate-400">Keine offenen Mails.</p>}
            {items.map((item) => (
                <InboxCard key={item.id} item={item} applications={applications} onDone={load} />
            ))}
        </div>
    );
}
```

- [ ] **Step 2: Add the route**

In `frontend/src/App.tsx` add `import Inbox from './pages/Inbox';` and, after the `bewerbungen/:id` route:
```tsx
                            <Route path="posteingang" element={<Inbox />} />
```

- [ ] **Step 3: Lint, build and check by hand**

Run: `cd frontend && npm run lint && npm run build; cd ..`
Expected: clean.

With the dev backend from Task 10 Step 6 started with `INBOUND_SECRET=dev` in addition, post a test mail:
```bash
venv/bin/python -c "import sys; sys.path.insert(0,'tests'); from mails import build_mail; sys.stdout.buffer.write(build_mail(to='bewerbungen@example.ch', attachments=[('Zeugnis.pdf', b'x', 'application/pdf')]))" \
  | curl -s -X POST -H 'X-Inbound-Secret: dev' --data-binary @- http://localhost:8000/api/inbound
```
Expected: `{"status":"stored",...}`, and the badge on "Posteingang" shows 1. Assign the mail to an application. It disappears from the inbox and shows up in the application's timeline with `Zeugnis.pdf`.

- [ ] **Step 4: Commit**

```bash
git add frontend
git commit -m "feat(frontend): inbox to assign incoming e-mails

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Settings page with integrations

**Files:**
- Create: `frontend/src/components/settings/MyAccount.tsx`, `frontend/src/components/settings/AppSettingsForm.tsx`, `frontend/src/components/settings/UserManager.tsx`, `frontend/src/components/settings/IntegrationCards.tsx`, `frontend/src/pages/SettingsPage.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `/api/me`, `/api/me/pin`, `/api/settings`, `/api/users`, `/api/integrations`, `/api/integrations/reminders/test`, `/api/export`.
- Produces: the route `/einstellungen`.

- [ ] **Step 1: Write `frontend/src/components/settings/MyAccount.tsx`**

```tsx
import { useState, type FormEvent } from 'react';
import api, { errorMessage } from '../../api';
import { useAuth } from '../../AuthContext';
import { useToast } from '../../ToastContext';
import { BUTTON, CARD, INPUT } from '../../ui';
import PinInput from '../PinInput';

export default function MyAccount() {
    const { user, refreshUser } = useAuth();
    const toast = useToast();
    const [email, setEmail] = useState(user?.email ?? '');
    const [wantsReminders, setWantsReminders] = useState(user?.wants_reminders ?? false);
    const [currentPin, setCurrentPin] = useState('');
    const [newPin, setNewPin] = useState('');

    const saveProfile = async (e: FormEvent) => {
        e.preventDefault();
        try {
            await api.patch('/api/me', { email, wants_reminders: wantsReminders });
            await refreshUser();
            toast('Gespeichert', 'success');
        } catch (err) {
            toast(errorMessage(err));
        }
    };

    const changePin = async (e: FormEvent) => {
        e.preventDefault();
        try {
            await api.post('/api/me/pin', { current_pin: currentPin, new_pin: newPin });
            setCurrentPin('');
            setNewPin('');
            toast('PIN geändert', 'success');
        } catch (err) {
            toast(errorMessage(err, 'PIN konnte nicht geändert werden'));
        }
    };

    return (
        <section className={`${CARD} space-y-4`}>
            <h2 className="text-lg font-bold">Mein Konto ({user?.name})</h2>
            <form onSubmit={saveProfile} className="space-y-3">
                <label className="block text-sm">
                    <span className="mb-1 block text-slate-400">
                        E-Mail-Adresse (für Erinnerungen; Mails von dieser Adresse gelten als „gesendet“)
                    </span>
                    <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className={INPUT} />
                </label>
                <label className="flex items-center gap-2 text-sm">
                    <input
                        type="checkbox"
                        checked={wantsReminders}
                        onChange={(e) => setWantsReminders(e.target.checked)}
                    />
                    Tägliche Erinnerung per E-Mail erhalten
                </label>
                <button type="submit" className={BUTTON}>
                    Speichern
                </button>
            </form>
            <form onSubmit={changePin} className="space-y-3">
                <h3 className="font-semibold">PIN ändern</h3>
                <div className="grid gap-3 sm:grid-cols-2">
                    <PinInput id="current-pin" value={currentPin} onChange={setCurrentPin} placeholder="Aktueller PIN" />
                    <PinInput
                        id="new-pin"
                        value={newPin}
                        onChange={setNewPin}
                        placeholder="Neuer PIN (4–8 Ziffern)"
                        autoComplete="new-password"
                    />
                </div>
                <button type="submit" disabled={currentPin.length < 4 || newPin.length < 4} className={BUTTON}>
                    PIN ändern
                </button>
            </form>
        </section>
    );
}
```

- [ ] **Step 2: Write `frontend/src/components/settings/AppSettingsForm.tsx`**

```tsx
import { useEffect, useState, type FormEvent } from 'react';
import api, { errorMessage } from '../../api';
import { useToast } from '../../ToastContext';
import type { AppSettings } from '../../types';
import { BUTTON, CARD, INPUT } from '../../ui';

export default function AppSettingsForm({ onSaved }: { onSaved: () => void }) {
    const toast = useToast();
    const [settings, setSettings] = useState<AppSettings | null>(null);

    useEffect(() => {
        api.get<AppSettings>('/api/settings')
            .then((response) => setSettings(response.data))
            .catch((e) => toast(errorMessage(e)));
    }, [toast]);

    if (!settings) return null;

    const save = async (e: FormEvent) => {
        e.preventDefault();
        try {
            setSettings((await api.patch<AppSettings>('/api/settings', settings)).data);
            toast('Gespeichert', 'success');
            onSaved();
        } catch (err) {
            toast(errorMessage(err));
        }
    };

    return (
        <section className={`${CARD} space-y-3`}>
            <h2 className="text-lg font-bold">App-Einstellungen</h2>
            <form onSubmit={save} className="grid gap-3 sm:grid-cols-3">
                <label className="block text-sm">
                    <span className="mb-1 block text-slate-400">Nachfragen nach (Tagen)</span>
                    <input
                        type="number"
                        min={1}
                        max={365}
                        required
                        value={settings.followup_days}
                        onChange={(e) => setSettings({ ...settings, followup_days: Number(e.target.value) })}
                        className={INPUT}
                    />
                </label>
                <label className="block text-sm">
                    <span className="mb-1 block text-slate-400">Erinnerung um</span>
                    <input
                        type="time"
                        required
                        value={settings.reminder_time}
                        onChange={(e) => setSettings({ ...settings, reminder_time: e.target.value })}
                        className={INPUT}
                    />
                </label>
                <label className="block text-sm">
                    <span className="mb-1 block text-slate-400">Eingangsadresse</span>
                    <input
                        type="email"
                        placeholder="bewerbungen@deine-domain.ch"
                        value={settings.inbound_address}
                        onChange={(e) => setSettings({ ...settings, inbound_address: e.target.value })}
                        className={INPUT}
                    />
                </label>
                <div className="sm:col-span-3">
                    <button type="submit" className={BUTTON}>
                        Speichern
                    </button>
                </div>
            </form>
        </section>
    );
}
```

- [ ] **Step 3: Write `frontend/src/components/settings/UserManager.tsx`**

```tsx
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import api, { errorMessage } from '../../api';
import { useAuth } from '../../AuthContext';
import { useToast } from '../../ToastContext';
import type { User } from '../../types';
import { BUTTON, CARD, FIELD } from '../../ui';
import PinInput from '../PinInput';

export default function UserManager() {
    const { user: me } = useAuth();
    const toast = useToast();
    const [users, setUsers] = useState<User[]>([]);
    const [name, setName] = useState('');
    const [pin, setPin] = useState('');
    const [isAdmin, setIsAdmin] = useState(false);

    const load = useCallback(async () => {
        try {
            setUsers((await api.get<User[]>('/api/users')).data);
        } catch (e) {
            toast(errorMessage(e));
        }
    }, [toast]);

    useEffect(() => {
        load();
    }, [load]);

    const run = async (action: () => Promise<unknown>, success?: string) => {
        try {
            await action();
            if (success) toast(success, 'success');
            await load();
        } catch (e) {
            toast(errorMessage(e));
        }
    };

    const add = (e: FormEvent) => {
        e.preventDefault();
        run(async () => {
            await api.post('/api/users', { name, pin, is_admin: isAdmin });
            setName('');
            setPin('');
            setIsAdmin(false);
        }, 'Benutzer angelegt');
    };
    const rename = (u: User) => {
        const newName = window.prompt('Neuer Name:', u.name);
        if (newName && newName !== u.name) run(() => api.patch(`/api/users/${u.id}`, { name: newName }));
    };
    const resetPin = (u: User) => {
        const newPin = window.prompt(`Neuer PIN für ${u.name} (4–8 Ziffern):`);
        if (newPin) run(() => api.post(`/api/users/${u.id}/pin`, { pin: newPin }), 'PIN gesetzt');
    };
    const toggleAdmin = (u: User) => run(() => api.patch(`/api/users/${u.id}`, { is_admin: !u.is_admin }));
    const remove = (u: User) => {
        if (window.confirm(`${u.name} löschen? Bewerbungen und Ereignisse bleiben erhalten.`)) {
            run(() => api.delete(`/api/users/${u.id}`), 'Benutzer gelöscht');
        }
    };

    return (
        <section className={`${CARD} space-y-3`}>
            <h2 className="text-lg font-bold">Benutzer</h2>
            <ul className="divide-y divide-slate-800">
                {users.map((u) => (
                    <li key={u.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-sm">
                        <span className="mr-auto font-semibold">
                            {u.name}
                            {u.is_admin && <span className="ml-2 text-xs text-amber-300">Admin</span>}
                            <span className="ml-2 text-xs font-normal text-slate-500">{u.email ?? 'keine E-Mail'}</span>
                        </span>
                        <button type="button" onClick={() => rename(u)} className="text-slate-300 hover:underline">
                            Umbenennen
                        </button>
                        <button type="button" onClick={() => resetPin(u)} className="text-slate-300 hover:underline">
                            PIN setzen
                        </button>
                        <button type="button" onClick={() => toggleAdmin(u)} className="text-slate-300 hover:underline">
                            {u.is_admin ? 'Admin entziehen' : 'Zum Admin machen'}
                        </button>
                        {u.id !== me?.id && (
                            <button type="button" onClick={() => remove(u)} className="text-red-300 hover:underline">
                                Löschen
                            </button>
                        )}
                    </li>
                ))}
            </ul>
            <form onSubmit={add} className="flex flex-wrap items-center gap-2">
                <input
                    placeholder="Name"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className={`${FIELD} min-w-32 flex-1`}
                />
                <div className="w-44">
                    <PinInput id="new-user-pin" value={pin} onChange={setPin} placeholder="PIN" autoComplete="new-password" />
                </div>
                <label className="flex items-center gap-1 text-sm">
                    <input type="checkbox" checked={isAdmin} onChange={(e) => setIsAdmin(e.target.checked)} />
                    Admin
                </label>
                <button type="submit" disabled={!name.trim() || pin.length < 4} className={BUTTON}>
                    Hinzufügen
                </button>
            </form>
        </section>
    );
}
```

- [ ] **Step 4: Write `frontend/src/components/settings/IntegrationCards.tsx`**

```tsx
import { Fragment, useCallback, useEffect, useState, type ReactNode } from 'react';
import api, { errorMessage } from '../../api';
import { formatDateTime } from '../../labels';
import { useToast } from '../../ToastContext';
import type { Integration, IntegrationState, Integrations } from '../../types';
import { BUTTON_SECONDARY, CARD } from '../../ui';

const STATE_STYLES: Record<IntegrationState, { label: string; className: string }> = {
    ok: { label: 'OK', className: 'bg-emerald-600' },
    waiting: { label: 'Wartet', className: 'bg-amber-600' },
    error: { label: 'Fehler', className: 'bg-red-600' },
    not_configured: { label: 'Nicht konfiguriert', className: 'bg-slate-600' },
};

const DETAIL_LABELS: Record<string, string> = {
    address: 'Eingangsadresse',
    last_received_at: 'Letzte Mail',
    last_error: 'Letzter Fehler',
    mail_from: 'Absender',
    recipients: 'Empfänger',
    next_run: 'Nächster Versand',
    last_attempt_at: 'Letzter Versuch',
    last_sent_at: 'Zuletzt versendet',
};

function formatValue(value: string | number | string[] | null): string {
    if (value === null || value === '') return '–';
    if (Array.isArray(value)) return value.length ? value.join(', ') : '–';
    if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T.*Z$/.test(value)) return formatDateTime(value);
    return String(value);
}

interface CardProps {
    title: string;
    integration: Integration;
    help: string;
    children?: ReactNode;
}

function IntegrationCard({ title, integration, help, children }: CardProps) {
    const style = STATE_STYLES[integration.state];
    return (
        <div className={`${CARD} space-y-2`}>
            <div className="flex items-center gap-2">
                <h3 className="mr-auto font-semibold">{title}</h3>
                <span className={`rounded-full px-2 py-0.5 text-xs font-semibold text-white ${style.className}`}>
                    {style.label}
                </span>
            </div>
            {integration.state === 'not_configured' ? (
                <p className="text-sm text-slate-400">{help}</p>
            ) : (
                <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                    {Object.entries(integration.details).map(([key, value]) => (
                        <Fragment key={key}>
                            <dt className="text-slate-500">{DETAIL_LABELS[key] ?? key}</dt>
                            <dd className={`break-words ${key === 'last_error' && value ? 'text-red-300' : ''}`}>
                                {formatValue(value)}
                            </dd>
                        </Fragment>
                    ))}
                </dl>
            )}
            {integration.warnings.map((warning) => (
                <p key={warning} className="text-sm text-amber-300">
                    ⚠ {warning}
                </p>
            ))}
            {children}
        </div>
    );
}

export default function IntegrationCards() {
    const toast = useToast();
    const [data, setData] = useState<Integrations | null>(null);
    const [sending, setSending] = useState(false);

    const load = useCallback(async () => {
        try {
            setData((await api.get<Integrations>('/api/integrations')).data);
        } catch (e) {
            toast(errorMessage(e));
        }
    }, [toast]);

    useEffect(() => {
        load();
    }, [load]);

    const sendTest = async () => {
        setSending(true);
        try {
            await api.post('/api/integrations/reminders/test');
            toast('Test-Erinnerung gesendet', 'success');
        } catch (e) {
            toast(errorMessage(e, 'Versand fehlgeschlagen'));
        } finally {
            setSending(false);
            await load();
        }
    };

    if (!data) return null;

    return (
        <section className="space-y-3">
            <h2 className="text-lg font-bold">Integrationen</h2>
            <div className="grid gap-3 sm:grid-cols-2">
                <IntegrationCard
                    title="Eingehende Mails (Cloudflare)"
                    integration={data.inbound}
                    help="INBOUND_SECRET in .env und als Worker-Secret setzen (siehe README_DOCKER.md)."
                />
                <IntegrationCard
                    title="Erinnerungen (Resend)"
                    integration={data.reminders}
                    help="RESEND_API_KEY und MAIL_FROM in .env setzen (siehe README_DOCKER.md)."
                >
                    {data.reminders.state !== 'not_configured' && (
                        <button type="button" disabled={sending} onClick={sendTest} className={BUTTON_SECONDARY}>
                            Test-Erinnerung senden
                        </button>
                    )}
                </IntegrationCard>
            </div>
        </section>
    );
}
```

- [ ] **Step 5: Write `frontend/src/pages/SettingsPage.tsx` and add the route**

```tsx
import { useState } from 'react';
import { downloadFile, errorMessage } from '../api';
import { useAuth } from '../AuthContext';
import AppSettingsForm from '../components/settings/AppSettingsForm';
import IntegrationCards from '../components/settings/IntegrationCards';
import MyAccount from '../components/settings/MyAccount';
import UserManager from '../components/settings/UserManager';
import { useToast } from '../ToastContext';
import { BUTTON_SECONDARY, CARD } from '../ui';

export default function SettingsPage() {
    const { user } = useAuth();
    const toast = useToast();
    // Bumped after saving the app settings, so the integration cards reload (e.g. the inbound address warning)
    const [integrationsVersion, setIntegrationsVersion] = useState(0);
    const [exporting, setExporting] = useState(false);

    const exportData = async () => {
        setExporting(true);
        try {
            await downloadFile('/api/export', 'bewerbungen-export.zip');
        } catch (e) {
            toast(errorMessage(e, 'Export fehlgeschlagen'));
        } finally {
            setExporting(false);
        }
    };

    return (
        <div className="space-y-6">
            <h1 className="text-2xl font-bold">Einstellungen</h1>
            <MyAccount />
            <IntegrationCards key={integrationsVersion} />
            {user?.is_admin && (
                <>
                    <AppSettingsForm onSaved={() => setIntegrationsVersion((v) => v + 1)} />
                    <UserManager />
                </>
            )}
            <section className={`${CARD} space-y-2`}>
                <h2 className="text-lg font-bold">Daten exportieren</h2>
                <p className="text-sm text-slate-400">
                    Alle Bewerbungen, Ereignisse und Mails als CSV, dazu alle Dateien, in einem ZIP.
                </p>
                <button type="button" disabled={exporting} onClick={exportData} className={BUTTON_SECONDARY}>
                    {exporting ? 'Export läuft…' : 'ZIP herunterladen'}
                </button>
            </section>
        </div>
    );
}
```

In `frontend/src/App.tsx` add `import SettingsPage from './pages/SettingsPage';` and, after the `posteingang` route:
```tsx
                            <Route path="einstellungen" element={<SettingsPage />} />
```

- [ ] **Step 6: Lint, build and check by hand**

Run: `cd frontend && npm run lint && npm run build; cd ..`
Expected: clean.

With the dev backend (no Resend variables), open Einstellungen and check the following:
- The "Erinnerungen (Resend)" card shows "Nicht konfiguriert".
- Set the Eingangsadresse to `bewerbungen@example.ch`. An application page now shows `bewerbungen+<tag>@example.ch`.
- Add the user "Sohn" and log in as Sohn. The admin sections are hidden.
- The export downloads a ZIP.

- [ ] **Step 7: Commit**

```bash
git add frontend
git commit -m "feat(frontend): settings with account, users, integrations and export

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: Cloudflare Email Worker

**Files:**
- Create: `cloudflare/email-worker/package.json`, `cloudflare/email-worker/tsconfig.json`, `cloudflare/email-worker/wrangler.toml`, `cloudflare/email-worker/src/index.ts`, `cloudflare/email-worker/test/index.test.ts`

**Interfaces:**
- Consumes: `POST /api/inbound` from Task 6. It needs the headers `X-Inbound-Secret` and `X-Envelope-To`, and it answers 2xx when the mail was stored.
- Produces:
  - `deliver(message: InboundMessage, env: Env, fetchImpl?: typeof fetch): Promise<void>`.
  - The default export `{ email(message, env) }`.
  - `Env` holds `APP_URL` (a var) plus `INBOUND_SECRET`, `CF_ACCESS_CLIENT_ID` and `CF_ACCESS_CLIENT_SECRET` (secrets).

- [ ] **Step 1: Create the project**

```bash
mkdir -p cloudflare/email-worker/src cloudflare/email-worker/test
```

`cloudflare/email-worker/package.json`:
```json
{
  "name": "family-jobs-inbound",
  "private": true,
  "type": "module",
  "scripts": {
    "deploy": "wrangler deploy",
    "test": "vitest run",
    "type-check": "tsc --noEmit"
  }
}
```

```bash
cd cloudflare/email-worker
npm install --save-dev wrangler@4 vitest@3 typescript@~5.9.3 @cloudflare/workers-types@4
cd ../..
```
Expected: `package-lock.json` is created and `devDependencies` is filled in.

`cloudflare/email-worker/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ES2022",
    "moduleResolution": "bundler",
    "lib": ["ES2022"],
    "types": ["@cloudflare/workers-types"],
    "strict": true,
    "noEmit": true,
    "skipLibCheck": true
  },
  "include": ["src", "test"]
}
```

`cloudflare/email-worker/wrangler.toml`:
```toml
# Cloudflare Email Worker: forwards every mail for bewerbungen@<domain> to the app.
# Setup: README_DOCKER.md, "Incoming e-mails".
name = "family-jobs-inbound"
main = "src/index.ts"
compatibility_date = "2026-01-01"

[vars]
# Public URL of the app through the Cloudflare Tunnel
APP_URL = "https://bewerbungen.example.ch"

# Secrets, set with `npx wrangler secret put <NAME>`:
#   INBOUND_SECRET            same value as INBOUND_SECRET in the app's .env
#   CF_ACCESS_CLIENT_ID       Cloudflare Access service token for /api/inbound
#   CF_ACCESS_CLIENT_SECRET
```

- [ ] **Step 2: Write the failing test**

`cloudflare/email-worker/test/index.test.ts`:
```ts
import { describe, expect, it, vi } from 'vitest';
import { deliver, type Env, type InboundMessage } from '../src/index';

const env: Env = {
    APP_URL: 'https://bewerbungen.example.ch/',
    INBOUND_SECRET: 's3cret',
    CF_ACCESS_CLIENT_ID: 'id.access',
    CF_ACCESS_CLIENT_SECRET: 'access-secret',
};

const RAW = 'Subject: Hallo\r\n\r\nText';

function message() {
    const setReject = vi.fn();
    const msg: InboundMessage = {
        from: 'hr@migros.ch',
        to: 'bewerbungen+abcd@example.ch',
        raw: new Response(RAW).body!,
        rawSize: RAW.length,
        setReject,
    };
    return { msg, setReject };
}

describe('deliver', () => {
    it('posts the raw mail with the secrets and the envelope recipient', async () => {
        const fetchMock = vi.fn(async () => new Response('{"status":"stored"}', { status: 200 }));
        const { msg, setReject } = message();
        await deliver(msg, env, fetchMock as unknown as typeof fetch);

        expect(fetchMock).toHaveBeenCalledOnce();
        const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
        expect(url).toBe('https://bewerbungen.example.ch/api/inbound');
        const headers = init.headers as Record<string, string>;
        expect(headers['X-Inbound-Secret']).toBe('s3cret');
        expect(headers['X-Envelope-To']).toBe('bewerbungen+abcd@example.ch');
        expect(headers['CF-Access-Client-Id']).toBe('id.access');
        expect(headers['CF-Access-Client-Secret']).toBe('access-secret');
        expect(init.redirect).toBe('manual');
        expect(new TextDecoder().decode(init.body as ArrayBuffer)).toBe(RAW);
        expect(setReject).not.toHaveBeenCalled();
    });

    // 302: Cloudflare Access redirects to its login page when the service token is wrong
    it.each([500, 401, 302])('rejects the mail when the app answers %i', async (status) => {
        const { msg, setReject } = message();
        await deliver(msg, env, (async () => new Response(null, { status })) as unknown as typeof fetch);
        expect(setReject).toHaveBeenCalledOnce();
    });

    it('rejects the mail when the app is unreachable', async () => {
        const { msg, setReject } = message();
        const failing = async () => {
            throw new Error('connection refused');
        };
        await deliver(msg, env, failing as unknown as typeof fetch);
        expect(setReject).toHaveBeenCalledWith(expect.stringContaining('nicht erreichbar'));
    });
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd cloudflare/email-worker && npm test; cd ../..`
Expected: FAIL, `Failed to resolve import "../src/index"`.

- [ ] **Step 4: Implement `cloudflare/email-worker/src/index.ts`**

```ts
export interface Env {
    APP_URL: string;
    INBOUND_SECRET: string;
    CF_ACCESS_CLIENT_ID: string;
    CF_ACCESS_CLIENT_SECRET: string;
}

// The parts of Cloudflare's ForwardableEmailMessage the worker uses
export interface InboundMessage {
    readonly from: string;
    readonly to: string;
    readonly raw: ReadableStream<Uint8Array>;
    readonly rawSize: number;
    setReject(reason: string): void;
}

/**
 * Post the raw mail to the app. If the app doesn't accept it, reject the mail,
 * so the sender gets a bounce instead of the mail being lost silently.
 */
export async function deliver(message: InboundMessage, env: Env, fetchImpl: typeof fetch = fetch): Promise<void> {
    const body = await new Response(message.raw).arrayBuffer();
    let response: Response;
    try {
        response = await fetchImpl(`${env.APP_URL.replace(/\/+$/, '')}/api/inbound`, {
            method: 'POST',
            headers: {
                'Content-Type': 'message/rfc822',
                'X-Inbound-Secret': env.INBOUND_SECRET,
                // A BCC'd +tag address appears in no header, only in the envelope
                'X-Envelope-To': message.to,
                'CF-Access-Client-Id': env.CF_ACCESS_CLIENT_ID,
                'CF-Access-Client-Secret': env.CF_ACCESS_CLIENT_SECRET,
            },
            body,
            // Cloudflare Access answers a bad service token with a redirect to its login page
            redirect: 'manual',
        });
    } catch (error) {
        message.setReject(`Family Job Tracking nicht erreichbar: ${String(error)}`);
        return;
    }
    if (!response.ok) {
        message.setReject(`Family Job Tracking hat die Mail nicht angenommen (HTTP ${response.status})`);
    }
}

export default {
    async email(message: InboundMessage, env: Env): Promise<void> {
        await deliver(message, env);
    },
};
```

- [ ] **Step 5: Run the tests and the type check**

Run: `cd cloudflare/email-worker && npm test && npm run type-check; cd ../..`
Expected: 5 tests pass (1 + 3 parameterised + 1), and `tsc` prints nothing.

- [ ] **Step 6: Commit**

```bash
git add cloudflare
git commit -m "feat(worker): Cloudflare Email Worker that forwards mails to the app

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: Docker, NAS scripts, CI and documentation

**Files:**
- Create: `backend/Dockerfile`, `frontend/Dockerfile` (copied), `frontend/nginx.conf`, `docker-compose.yml`, `.env.example`, `.deploy.env.example`, `scripts/deploy-nas.sh`, `scripts/nas-update.sh` (copied and adapted), `.github/workflows/pr-checks.yml`, `.github/workflows/ci-cd.yml`, `README.md`, `README_DOCKER.md`

**Interfaces:**
- Consumes: everything above.
- Produces: images `ghcr.io/frankandreas/family-job-tracking/{backend,frontend}:latest` on every push to `main`, and a NAS install that follows `README_DOCKER.md`.

- [ ] **Step 1: Copy the Dockerfiles and NAS scripts from the peer and adapt them**

```bash
PEER=/home/andreas/work/family-budget-dashboard
mkdir -p scripts .github/workflows
cp $PEER/backend/Dockerfile backend/Dockerfile
cp $PEER/frontend/Dockerfile frontend/Dockerfile
cp $PEER/scripts/deploy-nas.sh $PEER/scripts/nas-update.sh scripts/
cp $PEER/.deploy.env.example .deploy.env.example
sed -i \
  -e 's/Family Budget/Family Job Tracking/g' \
  -e 's/budget-backend/jobs-backend/g' \
  -e 's/budget-\$stamp/jobs-$stamp/g' \
  -e 's#budget-\*\.gz#jobs-*.gz#g' \
  -e 's#/volume1/docker/family-budget#/volume1/docker/family-jobs#g' \
  scripts/deploy-nas.sh scripts/nas-update.sh .deploy.env.example
chmod +x scripts/*.sh
grep -n -i budget scripts/*.sh .deploy.env.example backend/Dockerfile frontend/Dockerfile
```
Expected: the final `grep` prints nothing. The backend Dockerfile already creates `/app/data` owned by 999:999, and attachments live below it. No change is needed.

- [ ] **Step 2: Write `frontend/nginx.conf`**

```nginx
server {
    listen 8080;
    server_name localhost;

    # Uploads and incoming e-mails may be up to 25 MB (the backend enforces that limit)
    client_max_body_size 30m;

    # Serve the React app (SPA)
    location / {
        root /usr/share/nginx/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    # Forward API requests to the backend ('backend' is the compose service name)
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

- [ ] **Step 3: Write `docker-compose.yml` and `.env.example`**

`docker-compose.yml`:
```yaml
# Family Job Tracking on a NAS (or any Docker host), with the published images.
# Copy it to the app folder on the NAS as compose.yaml; see README_DOCKER.md.
#
# The backend runs as PUID:PGID from .env (default 999:999, the image's own
# user). On a Synology, use a DSM user's IDs (see README_DOCKER.md). The ./data
# folder must exist and belong to that user before the first start; it holds the
# database and all attachments.
#
# To try your local changes instead: docker compose up -d --build

services:
  backend:
    image: ghcr.io/frankandreas/family-job-tracking/backend:latest
    build: ./backend
    container_name: jobs-backend
    user: "${PUID:-999}:${PGID:-999}"
    volumes:
      - ./data:/app/data          # jobs.db and files/ (attachments, raw e-mails)
    environment:
      - DATABASE_URL=sqlite:///./data/jobs.db
      - DATA_DIR=/app/data
      - TZ=${TZ:-Europe/Zurich}
      # Signs login tokens. If empty, a random key is used and everyone is
      # logged out whenever the container restarts (e.g. on every update).
      - SECRET_KEY=${SECRET_KEY:-}
      # PIN for the first user "Admin" on an empty database; empty means a
      # random PIN, printed once in the backend log
      - INITIAL_ADMIN_PIN=${INITIAL_ADMIN_PIN:-}
      - APP_URL=${APP_URL:-}
      # Optional integrations; the app runs without them
      - INBOUND_SECRET=${INBOUND_SECRET:-}
      - RESEND_API_KEY=${RESEND_API_KEY:-}
      - MAIL_FROM=${MAIL_FROM:-}
    restart: unless-stopped
    healthcheck:
      test: [ "CMD-SHELL", "python3 -c 'import urllib.request; urllib.request.urlopen(\"http://localhost:8000/health\")' || exit 1" ]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

  frontend:
    image: ghcr.io/frankandreas/family-job-tracking/frontend:latest
    build: ./frontend
    container_name: jobs-frontend
    ports:
      - "${PORT:-8082}:8080"
    depends_on:
      - backend
    restart: unless-stopped
```

`.env.example`:
```bash
# Copy to .env next to the compose file (git ignores it). docker compose reads it automatically.
# See README_DOCKER.md for the NAS setup.

# User and group the backend runs as, and that owns ./data.
# On a Synology, the IDs of a DSM user (`id <user>`); default: the image's own user 999:999.
PUID=999
PGID=999

# Port of the app on the NAS: http://<NAS_IP>:8082
PORT=8082

# Time zone for reminder times and the dates in file names
TZ=Europe/Zurich

# Signs login tokens; set it so logins survive updates. Generate one with:
#   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
SECRET_KEY=

# Optional: PIN (4-8 digits) for the first user "Admin", created when the database is empty.
# If unset, a random 4-digit PIN is generated and printed once in the backend log.
INITIAL_ADMIN_PIN=

# Public URL of the app (through the Cloudflare Tunnel), for links in reminder e-mails
APP_URL=

# Optional: incoming e-mails from the Cloudflare Email Worker; the same value as the worker's INBOUND_SECRET.
#   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
INBOUND_SECRET=

# Optional: daily reminder e-mails via Resend. Both must be set; MAIL_FROM must use a domain
# verified in Resend, e.g. "Bewerbungen <bewerbungen@example.ch>".
RESEND_API_KEY=
MAIL_FROM=
```

- [ ] **Step 4: Smoke-test the containers locally**

```bash
mkdir -p data && printf 'SECRET_KEY=dev\nINITIAL_ADMIN_PIN=1234\nINBOUND_SECRET=dev\nPUID=%s\nPGID=%s\n' "$(id -u)" "$(id -g)" > .env
docker compose up -d --build
sleep 15
curl -sf http://localhost:8082/api/users/public
TOKEN=$(curl -sf -X POST -H 'Content-Type: application/json' -d '{"name":"Admin","pin":"1234"}' http://localhost:8082/api/token | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -sf -H "Authorization: Bearer $TOKEN" http://localhost:8082/api/integrations
# A ~20 MB mail (15 MB attachment, base64) must pass nginx (client_max_body_size) and be stored
venv/bin/python -c "import sys; sys.path.insert(0,'tests'); from mails import build_mail; sys.stdout.buffer.write(build_mail(to='bewerbungen@example.ch', attachments=[('gross.pdf', b'x'*15_000_000, 'application/pdf')]))" \
  | curl -s -X POST -H 'X-Inbound-Secret: dev' --data-binary @- http://localhost:8082/api/inbound
ls data/files/_posteingang
docker compose down
rm -rf data/jobs.db data/files .env
```
Expected:
- `users/public` prints `[{"id":1,"name":"Admin"}]`.
- `integrations` shows the inbound state `waiting` and the reminders state `not_configured`.
- The inbound POST prints `{"status":"stored",...}`, and `ls` lists the `.eml` file and `..._gross.pdf`.
- The SPA loads at `http://localhost:8082`.

- [ ] **Step 5: Write the GitHub workflows**

`.github/workflows/pr-checks.yml`:
```yaml
name: Checks

on:
  pull_request:
  # Also run by ci-cd.yml before images are built
  workflow_call:

jobs:
  backend:
    name: Backend tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: '3.14'
          cache: 'pip'
      - run: pip install -r backend/requirements.txt -r tests/requirements.txt
      # The tests run the API in-process against a temporary SQLite database (see tests/conftest.py)
      - run: pytest

  frontend:
    name: Frontend lint, type-check and build
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-node@v7
        with:
          node-version: '26'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npm run lint
      - run: npm run build

  worker:
    name: Email worker tests
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: cloudflare/email-worker
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-node@v7
        with:
          node-version: '26'
          cache: 'npm'
          cache-dependency-path: cloudflare/email-worker/package-lock.json
      - run: npm ci
      - run: npm run type-check
      - run: npm test

  compose:
    name: Validate docker-compose.yml
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - run: docker compose config --quiet
```

`.github/workflows/ci-cd.yml`:
```yaml
name: CI/CD

on:
  push:
    branches: [main]

jobs:
  checks:
    uses: ./.github/workflows/pr-checks.yml

  images:
    name: Build and push ${{ matrix.component }} image
    needs: checks
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    strategy:
      matrix:
        include:
          # Registry paths must be lowercase; change these if the repository moves
          - component: backend
            image: ghcr.io/frankandreas/family-job-tracking/backend
          - component: frontend
            image: ghcr.io/frankandreas/family-job-tracking/frontend
    steps:
      - uses: actions/checkout@v7
      - uses: docker/setup-buildx-action@v4
      - uses: docker/login-action@v4
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - id: meta
        uses: docker/metadata-action@v6
        with:
          images: ${{ matrix.image }}
          tags: |
            type=raw,value=latest
            type=sha
      - uses: docker/build-push-action@v7
        with:
          context: ${{ matrix.component }}
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha,scope=${{ matrix.component }}
          cache-to: type=gha,mode=max,scope=${{ matrix.component }}
```

Run: `docker compose config --quiet && echo ok`
Expected: `ok`.

- [ ] **Step 6: Write `README.md`**

```markdown
# Family Job Tracking

A small self-hosted app to keep track of job and apprenticeship applications: every company, and a
timeline of everything that happened (sent, followed up, reply, interview, offer, …), including the
e-mails and their attachments. Built for a family: the applicant and a parent both log in with a PIN
and see everything.

- **Overview**: counts per status, the applications that need a follow-up, search and filters.
- **Timeline per application**: events with notes and files; files are stored on the NAS with
  readable names (`files/migros/2026-10-15_migros_Lebenslauf.pdf`).
- **E-mails into the timeline**: each application has its own address
  (`bewerbungen+a7k2@your-domain`); put it in BCC or forward mails there and they appear in the
  timeline. Mails without such an address land in the inbox for one-click assignment.
- **Daily reminder** by e-mail (via Resend) when a follow-up is due.

The UI is German. Stack: FastAPI + SQLite, React + Vite + Tailwind, nginx, a Cloudflare Email
Worker; runs as two Docker containers next to family-budget-dashboard and family-chore.

## Install
See [README_DOCKER.md](README_DOCKER.md) for the NAS setup, Cloudflare and Resend.

## Development

```bash
python3 -m venv venv
venv/bin/pip install -r backend/requirements.txt -r tests/requirements.txt
venv/bin/pytest                                   # backend tests

mkdir -p data/dev
DATA_DIR=data/dev DATABASE_URL=sqlite:///data/dev/dev.db INITIAL_ADMIN_PIN=1234 SECRET_KEY=dev \
  venv/bin/uvicorn app.main:app --app-dir backend --reload --port 8000

cd frontend && npm install && npm run dev         # http://localhost:5173, proxies /api to :8000
cd cloudflare/email-worker && npm install && npm test
```

The design is in `docs/superpowers/specs/2026-10-15-family-job-tracking-design.md`.
```

- [ ] **Step 7: Write `README_DOCKER.md`**

````markdown
# Running Family Job Tracking on a Synology NAS

The app runs as two containers from images on GitHub Container Registry (GHCR):

- **backend** (`ghcr.io/frankandreas/family-job-tracking/backend`): the API; the database and all
  attachments live in `./data`
- **frontend** (`ghcr.io/frankandreas/family-job-tracking/frontend`): nginx serving the app on port
  8080 inside the container, forwarding `/api` to the backend

It is set up like family-budget-dashboard and family-chore, so all three run side by side
(family-chore on 8080, family-budget on 8081, this app on **8082**).

Two integrations are optional and can be added later; the app runs fine without them:

- **Incoming e-mails** through Cloudflare Email Routing and a small Email Worker
- **Daily reminders** through Resend

## Installation

1. **Choose the user the app runs as.** Reuse the DSM user of the other family apps (e.g.
   `familyapps`), or create one in **Control Panel → User & Group** with no application permissions.
   Look up its IDs over SSH:
   ```bash
   id familyapps    # e.g. uid=1031(familyapps) gid=100(users)
   ```
2. **Prepare the folder.** Create `/volume1/docker/family-jobs` and upload `docker-compose.yml` into
   it **renamed to `compose.yaml`**. Then create the data folder, owned by the app's user:
   ```bash
   cd /volume1/docker/family-jobs
   sudo mkdir -p data
   sudo chown -R 1031:100 data    # the IDs from step 1
   ```
3. **Create `.env`** (all settings are explained in `.env.example`):
   ```bash
   printf 'PUID=1031\nPGID=100\nPORT=8082\nTZ=Europe/Zurich\nSECRET_KEY=%s\nAPP_URL=https://bewerbungen.example.ch\n' \
     "$(openssl rand -hex 32)" | sudo tee .env
   sudo chmod 600 .env
   ```
4. **Start** it:
   ```bash
   sudo docker-compose pull
   sudo docker-compose up -d
   ```
5. **Open** `http://<NAS_IP>:8082`.

### First login
On an empty database the backend creates the user **Admin** with a random 4-digit PIN, printed once in
its log:
```bash
sudo docker logs jobs-backend 2>&1 | grep "INITIAL PIN"
```
Log in, then in **Einstellungen**:
- change the PIN
- rename Admin
- add the other user (e.g. your son) under **Benutzer**

Everyone sees and edits all applications. To choose the first PIN yourself, set
`INITIAL_ADMIN_PIN=1234` in `.env` before the first start.

### Where the data is
Everything worth keeping is in `data/`:
- `jobs.db`: the database
- `files/<firma>/`: attachments and the original e-mails (`.eml`), named
  `<date>_<firma>_<original name>`
- `files/_posteingang/`: files of e-mails that are not assigned yet

Include `data/` in your Hyper Backup task. **Einstellungen → Daten exportieren** downloads everything
as a ZIP (CSV files plus the attachments).

## Reaching the app from outside (Cloudflare Tunnel and Access)

The NAS is already connected to Cloudflare Zero Trust with a tunnel.

1. **Public hostname.** In **Zero Trust → Networks → Tunnels → your tunnel → Public Hostname → Add**:
   - subdomain `bewerbungen`, your domain
   - service `HTTP`, URL `<NAS_IP>:8082`
2. **Access application for people.** In **Zero Trust → Access → Applications → Add → Self-hosted**:
   - domain `bewerbungen.<domain>`
   - a policy that allows your family's e-mail addresses

   The PIN login of the app comes on top of that.
3. Set `APP_URL=https://bewerbungen.<domain>` in `.env` and restart (`sudo docker-compose up -d`).

## Incoming e-mails (Cloudflare Email Worker)

Each application has its own address `bewerbungen+<tag>@<domain>`. A mail sent, CC'd, BCC'd or
forwarded to it lands in that application's timeline, including attachments. Mails to plain
`bewerbungen@<domain>` land in the **Posteingang**.

1. **Secret for the app.** Add it to `.env`, then restart:
   ```bash
   echo "INBOUND_SECRET=$(openssl rand -hex 32)" | sudo tee -a .env
   ```
2. **Service token for the worker.** In **Zero Trust → Access → Service Auth → Service Tokens →
   Create**, name it `family-jobs-inbound` and note the Client ID and Client Secret.
3. **Access application for the worker.** In **Access → Applications → Add → Self-hosted**:
   - domain `bewerbungen.<domain>`, path `api/inbound`
   - one policy with action **Service Auth** that includes the service token

   The more specific path takes precedence over the application from above. Only the worker can call
   `/api/inbound`, and the app checks `INBOUND_SECRET` on top of that.
4. **Deploy the worker** from a checkout of this repository:
   ```bash
   cd cloudflare/email-worker
   npm ci
   # set APP_URL in wrangler.toml to https://bewerbungen.<domain>
   npx wrangler login
   npx wrangler secret put INBOUND_SECRET            # the value from step 1
   npx wrangler secret put CF_ACCESS_CLIENT_ID       # from step 2
   npx wrangler secret put CF_ACCESS_CLIENT_SECRET   # from step 2
   npx wrangler deploy
   ```
5. **Route the address to the worker.** In the Cloudflare dashboard, open your domain and go to
   **Email → Email Routing**:
   - enable it if it isn't, and let Cloudflare add the MX/SPF records
   - in **Settings**, enable **Subaddressing**, so `bewerbungen+tag@` reaches the same rule
   - under **Routing rules → Custom addresses → Create address**, enter `bewerbungen`, set the action
     to **Send to a Worker** and choose `family-jobs-inbound`
6. **In the app**, open **Einstellungen**:
   - set the **Eingangsadresse** to `bewerbungen@<domain>`
   - check that the card **Eingehende Mails** says "Wartet"
   - send a test mail to `bewerbungen@<domain>`

   The card turns "OK" and the mail appears in the Posteingang.

If the app is unreachable or refuses the mail, the worker rejects it, so the sender gets a bounce and
nothing is lost silently. Mails the app cannot read are kept as `.eml` in the Posteingang. Delivering
the same mail twice is detected by its Message-ID.

**Mails from you count as "Mail gesendet":** save your own address under **Einstellungen → Mein Konto**.

## Daily reminders (Resend)

1. In Resend, verify the domain (or a subdomain) you want to send from. If Papra already sends through
   Resend with this domain, it is verified already.
2. Create an API key with **Sending access** for that domain.
3. Add it to `.env` and restart:
   ```bash
   printf 'RESEND_API_KEY=re_...\nMAIL_FROM=Bewerbungen <bewerbungen@example.ch>\n' | sudo tee -a .env
   sudo docker-compose up -d
   ```
4. In **Einstellungen**, do the following:
   - every user who wants reminders saves their e-mail address and ticks **Tägliche Erinnerung**
   - an admin sets **Nachfragen nach (Tagen)** (default 10) and **Erinnerung um** (default 07:00)
   - press **Test-Erinnerung senden** on the **Erinnerungen** card

Once a day, after the set time, one e-mail goes to everyone who opted in. It lists the applications
with no news for longer than the follow-up period, and the number of unassigned inbox mails. Nothing
is sent on days without anything due. If sending fails, the card turns red with the error and the
app retries every 15 minutes.

## Automatic updates

`scripts/nas-update.sh` checks for new images and installs them, the same way as in the other family
apps:
- it pulls the images
- if there is a new one, it backs up the database to `db-backups/`, keeps the old images as
  `:previous` and restarts the app
- it waits until the backend is healthy, logging to `logs/update.log`

1. Copy `scripts/nas-update.sh` into `/volume1/docker/family-jobs` and make it executable (or let
   `scripts/deploy-nas.sh` upload it):
   ```bash
   sudo chmod +x /volume1/docker/family-jobs/nas-update.sh
   sudo /volume1/docker/family-jobs/nas-update.sh     # should end with "Up to date" or "Update complete"
   ```
2. In **Control Panel → Task Scheduler → Create → Scheduled Task → User-defined script**:
   - user **root**
   - daily, a few minutes apart from the other apps' updates (e.g. 04:00)
   - command `bash /volume1/docker/family-jobs/nas-update.sh`

If the images are private, log in to the registry once as root:
`sudo docker login ghcr.io -u <github-user>` with a token that has `read:packages`.

To deploy right away from your computer:
```bash
cp .deploy.env.example .deploy.env   # once; then set NAS_HOST and NAS_DIR
scripts/deploy-nas.sh
```

## Troubleshooting

| Symptom | Check |
|---|---|
| Card "Eingehende Mails" is red | the error shown on the card; the mail is still in the Posteingang as `.eml` |
| Mails bounce with "nicht angenommen (HTTP 302)" | the Access service token or the `api/inbound` Access application |
| Mails bounce with "HTTP 401" | `INBOUND_SECRET` differs between `.env` and the worker secret |
| Card "Erinnerungen" is red | the Resend error shown on the card (unverified domain, wrong key) |
| Reminder e-mails have no links | `APP_URL` in `.env` |
| Everyone is logged out after an update | `SECRET_KEY` is empty in `.env` |
````

- [ ] **Step 8: Commit**

```bash
git add backend/Dockerfile frontend/Dockerfile frontend/nginx.conf docker-compose.yml .env.example .deploy.env.example \
  scripts .github README.md README_DOCKER.md
git commit -m "build: Docker images, NAS scripts, CI/CD and installation guide

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Spec coverage

| Spec section | Task |
|---|---|
| Architecture, configuration | 1, 15 |
| Data model, derived status, follow-up due | 1, 3, 4 |
| File storage (readable names, counter, inbox folder, move on assign) | 3, 4, 6, 7 |
| Authentication (PIN, lockout, admin, first PIN) | 2 |
| Backend API | 2, 4, 6, 7, 9 |
| Inbound e-mail (worker, secret, envelope, dedupe, unreadable mails) | 5, 6, 14 |
| Inbox suggestion | 7 |
| Reminder e-mails | 8 |
| Integration status | 9, 13 |
| Frontend screens | 10–13 |
| Export | 9, 13 |
| Testing, CI/CD, deployment docs | every task, 15 |
