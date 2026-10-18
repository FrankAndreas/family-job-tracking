# Suggestions (Vorschläge) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Family members post links to open apprenticeships as suggestions (in the app or by e-mail); the son applies (one click to an application) or declines; reminders and export include them.

**Architecture:** A new `suggestions` table and router next to the existing applications API. URL handling (normalising, duplicates, link extraction) lives in `backend/app/suggestions.py`; fetching a page title with an SSRF guard in `backend/app/pagetitle.py`. The inbound mail flow branches on the `+vorschlag` tag before the application tag lookup. The frontend gets a `/vorschlaege` page with a nav badge kept in step like the Posteingang badge.

**Tech Stack:** FastAPI, SQLAlchemy 2, SQLite, pytest; React 19, TypeScript, Tailwind, axios; Python standard library only for HTTP (`http.client`, `socket`, `ssl`, `ipaddress`, `html.parser`).

**Spec:** `docs/superpowers/specs/2026-10-18-suggestions-design.md`

## Global Constraints

- No new Python or npm dependency.
- UI text in German; code, comments, docs and commit messages in English.
- Everyone sees all suggestions; every endpoint except `/api/inbound` needs a login.
- `url` at most 500 characters, `http` or `https` only.
- Title fetch: ports 80 and 443 only, every resolved address must be public, at most 3 redirects, 5 s timeout, at most 1 MB, `text/html` only; any failure gives `title: null`.
- Mail address `bewerbungen+vorschlag@<domain>`; only senders that are users' addresses; at most 10 links per mail; nothing fetched for e-mailed links.
- Reminder: "new" = created after `settings.last_reminder_sent_at`; "deadline soon" = deadline from today to 7 days ahead (local date).
- Run backend tests with `venv/bin/pytest` from the repository root; frontend checks with `npm run lint && npm run build` in `frontend/`.
- Commit messages end with:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01YA8keQBSJPgVNmbSLJoGmM
  ```

## Review Focus

- A link pasted with spaces around it, or without `https://` (e.g. `www.yousty.ch/…`): the backend trims and rejects schemeless input with a clear 422; the form adds `https://` before sending. (Task 2 test, Task 7 form.)
- A suggestion whose application was deleted later: the list still loads, status stays `applied`, `application` is `null`. (Task 2 test.)
- A shared link that arrives as an HTML-only mail whose link text is not the URL (`<a href="https://…">Lehrstelle</a>`): it still becomes a suggestion. (Task 4 test.)
- A page in ISO-8859-1 with umlauts in the title: the title is decoded with the charset from the `Content-Type` header. (Task 3 test.)
- A double click on "Bewerben": the second request gets 409 and creates no second application. (Task 2 test.)

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/models.py` (modify) | `SuggestionStatus` enum and `Suggestion` model |
| `backend/app/suggestions.py` (create) | `normalize_url`, `label`, `find_duplicates`, `extract_links`, `clean_subject`, `create_from_mail`, constants |
| `backend/app/pagetitle.py` (create) | `fetch_title(url)` with the SSRF guard; `extract_title(html)` |
| `backend/app/schemas.py` (modify) | `SuggestionIn`, `SuggestionPatch`, `SuggestionApplyIn`, `SuggestionDeclineIn`, `SuggestionCheckIn` |
| `backend/app/views.py` (modify) | `suggestion_out(s, today)` |
| `backend/app/suggestions_api.py` (create) | the `/api/suggestions…` endpoints |
| `backend/app/applications_api.py` (modify) | `suggestion_count` in `/api/dashboard` |
| `backend/app/main.py` (modify) | register the router |
| `backend/app/mailparse.py` (modify) | `ParsedMail.html_links` |
| `backend/app/inbound.py` (modify) | `+vorschlag` branch in `process` |
| `backend/app/inbox_api.py` (modify) | response for suggestion mails |
| `backend/app/reminders.py` (modify) | suggestion lists in the digest and mail |
| `backend/app/export.py` (modify) | `vorschlaege.csv`, `suggestions.csv` |
| `tests/test_suggestions.py` (create) | Tasks 1, 2, 4 |
| `tests/test_pagetitle.py` (create) | Task 3 |
| `tests/test_reminders.py`, `tests/test_settings.py` (modify) | Tasks 5, 6 |
| `frontend/src/types.ts`, `components/Layout.tsx`, `App.tsx` (modify) | types, nav tab and badge, route |
| `frontend/src/pages/Suggestions.tsx` (create) | page: form, open list, done list |
| `frontend/src/components/SuggestionCard.tsx` (create) | one suggestion with its actions |
| `README.md`, `README_DOCKER.md` (modify) | feature and mail address |

---

### Task 1: Model and URL helpers

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/app/suggestions.py`
- Test: `tests/test_suggestions.py`

**Interfaces:**
- Produces:
  - `models.SuggestionStatus` (`OPEN = "open"`, `APPLIED = "applied"`, `DECLINED = "declined"`)
  - `models.Suggestion` with the columns of the spec and relationships `application`, `creator`, `decider`
  - `suggestions.SUGGESTION_TAG = "vorschlag"`, `suggestions.MAX_MAIL_LINKS = 10`
  - `suggestions.normalize_url(url: str) -> str`
  - `suggestions.label(s: models.Suggestion) -> str`
  - `suggestions.find_duplicates(db, url: str, exclude_id: int | None = None) -> list[dict]` (dict keys: `kind` `"suggestion"|"application"`, `id`, `label`, `date` ISO string, `status` only for suggestions)
  - `suggestions.extract_links(*texts: str) -> list[str]`
  - `suggestions.clean_subject(subject: str) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_suggestions.py` (later tasks append tests; their imports are already here):

```python
import pytest

from app import models, suggestions
from helpers import create_user, login
from mails import INBOUND_SECRET, build_mail, post_mail


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.Yousty.ch/de-CH/lehrstellen/123/", "https://yousty.ch/de-CH/lehrstellen/123"),
        ("HTTPS://jobs.ch/a?b=2&a=1#top", "https://jobs.ch/a?a=1&b=2"),
        ("https://jobs.ch/a?utm_source=x&id=7&fbclid=y&gclid=z", "https://jobs.ch/a?id=7"),
        ("  https://jobs.ch/a  ", "https://jobs.ch/a"),
        ("Inserat auf Papier", "inserat auf papier"),
    ],
)
def test_normalize_url(url, expected):
    assert suggestions.normalize_url(url) == expected


def add_suggestion(db, url, **fields):
    s = models.Suggestion(url=url, url_key=suggestions.normalize_url(url), **fields)
    db.add(s)
    db.commit()
    return s


def test_label_falls_back_to_host(db):
    assert suggestions.label(add_suggestion(db, "https://www.yousty.ch/x")) == "yousty.ch"
    s = add_suggestion(db, "https://jobs.ch/y", company="Migros", position="Informatiker")
    assert suggestions.label(s) == "Migros – Informatiker"


def test_find_duplicates_in_suggestions_and_applications(db):
    first = add_suggestion(db, "https://www.yousty.ch/x?utm_source=mail", company="Migros")
    db.add(models.Application(company="Coop", posting_url="https://yousty.ch/x/", mail_tag="abcd"))
    db.add(models.Application(company="Lidl", posting_url="Inserat auf Papier", mail_tag="efgh"))
    db.commit()
    found = suggestions.find_duplicates(db, "https://yousty.ch/x")
    assert [(d["kind"], d["label"]) for d in found] == [("suggestion", "Migros"), ("application", "Coop")]
    assert found[0]["status"] == "open"
    assert suggestions.find_duplicates(db, "https://yousty.ch/x", exclude_id=first.id)[0]["kind"] == "application"


def test_extract_links():
    text = "Schau mal: https://yousty.ch/a. Und (https://jobs.ch/b?x=1), nochmals https://yousty.ch/a"
    html_links = ["https://jobs.ch/b?x=1", "mailto:hr@migros.ch", "https://migros.ch/c"]
    assert suggestions.extract_links(text, *html_links) == [
        "https://yousty.ch/a",
        "https://jobs.ch/b?x=1",
        "https://migros.ch/c",
    ]


@pytest.mark.parametrize(
    "subject, expected",
    [("Fwd: Lehrstelle Informatiker", "Lehrstelle Informatiker"), ("WG: Fw: FWD:  Koch", "Koch"), ("Koch", "Koch")],
)
def test_clean_subject(subject, expected):
    assert suggestions.clean_subject(subject) == expected
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_suggestions.py -q`
Expected: FAIL with `ImportError: cannot import name 'suggestions'`

- [ ] **Step 3: Add the model**

In `backend/app/models.py`, change the first SQLAlchemy import line to include `Date`:

```python
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text
```

Append at the end of the file:

```python
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
```

- [ ] **Step 4: Add the helpers**

Create `backend/app/suggestions.py`:

```python
"""Suggestions: links to open apprenticeships, their duplicates and the links in e-mails."""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.orm import Session

from . import models
from .timeutil import iso

# bewerbungen+vorschlag@<domain>; application tags never contain an "o", so this can't clash
SUGGESTION_TAG = "vorschlag"
MAX_MAIL_LINKS = 10

_TRACKING_PARAMS = {"fbclid", "gclid"}
_LINK = re.compile(r"https?://[^\s<>\"'()\[\]]+", re.IGNORECASE)
_FORWARD_PREFIX = re.compile(r"^\s*((fwd?|wg)\s*:\s*)+", re.IGNORECASE)


def normalize_url(url: str) -> str:
    """The form of a link used to find duplicates: no www., fragment, tracking parameters or trailing slash."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    try:
        port = parts.port
    except ValueError:
        port = None
    netloc = f"{host}:{port}" if port else host
    query = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_PARAMS
    )
    if not netloc:
        # Not a link (an application's posting_url may be free text): compare it as text
        return " ".join(url.split()).lower()
    return urlunsplit((parts.scheme.lower(), netloc, parts.path.rstrip("/"), urlencode(query), ""))


def label(s: models.Suggestion) -> str:
    """"Company – position", either one alone, or the link's host if both are empty."""
    text = " – ".join(part for part in (s.company, s.position) if part)
    if text:
        return text
    host = (urlsplit(s.url).hostname or s.url).lower()
    return host[4:] if host.startswith("www.") else host


def find_duplicates(db: Session, url: str, exclude_id: int | None = None) -> list[dict]:
    """Earlier suggestions and applications with the same normalised link."""
    key = normalize_url(url)
    found = [
        {"kind": "suggestion", "id": s.id, "label": label(s), "date": iso(s.created_at), "status": s.status}
        for s in db.query(models.Suggestion)
        .filter(models.Suggestion.url_key == key)
        .order_by(models.Suggestion.created_at, models.Suggestion.id)
        if s.id != exclude_id
    ]
    applications = db.query(models.Application).filter(models.Application.posting_url != "").order_by(
        models.Application.created_at, models.Application.id
    )
    for a in applications:
        if normalize_url(a.posting_url) == key:
            title = a.company + (f" – {a.position}" if a.position else "")
            found.append({"kind": "application", "id": a.id, "label": title, "date": iso(a.created_at)})
    return found


def extract_links(*texts: str) -> list[str]:
    """The http(s) links in the texts, in order, without repeats; trailing punctuation is not part of a link."""
    links: list[str] = []
    for text in texts:
        for match in _LINK.findall(text or ""):
            link = match.rstrip(".,;:!?")
            if link not in links:
                links.append(link)
    return links


def clean_subject(subject: str) -> str:
    """A forwarded mail's subject without "Fwd:", "Fw:" or "WG:"."""
    return _FORWARD_PREFIX.sub("", subject).strip()
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_suggestions.py -q`
Expected: PASS (all tests in the file)

- [ ] **Step 6: Run the whole suite**

Run: `venv/bin/pytest -q`
Expected: all pass (the new table is created by `create_all` in the test fixture)

- [ ] **Step 7: Commit**

```bash
git add backend/app/models.py backend/app/suggestions.py tests/test_suggestions.py
git commit -m "feat(suggestions): model, URL normalisation, duplicates and link extraction"
```

---

### Task 2: Suggestions API (CRUD, apply, decline, reopen, dashboard count)

**Files:**
- Modify: `backend/app/schemas.py`, `backend/app/views.py`, `backend/app/applications_api.py`, `backend/app/main.py`
- Create: `backend/app/suggestions_api.py`
- Test: `tests/test_suggestions.py`

**Interfaces:**
- Consumes: Task 1 (`models.Suggestion`, `suggestions.normalize_url`, `suggestions.find_duplicates`)
- Produces:
  - `views.suggestion_out(s: models.Suggestion, today: date) -> dict` with keys `id, url, company, position, location, deadline (YYYY-MM-DD|None), note, status, decline_reason, source, created_at, created_by_name, decided_at, decided_by_name, application ({id, company, position}|None), deadline_passed`
  - Endpoints of the spec except `check` (Task 3)
  - `/api/dashboard` key `suggestion_count`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_suggestions.py` (imports are at the top since Task 1):

```python
def post_suggestion(client, headers, url="https://yousty.ch/lehrstellen/1", **fields):
    response = client.post("/api/suggestions", json={"url": url, **fields}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_suggestions_need_login(client):
    assert client.get("/api/suggestions").status_code == 401


def test_create_and_list(client, admin_headers):
    created = post_suggestion(
        client, admin_headers, " https://yousty.ch/lehrstellen/1 ", company="Migros", deadline="2026-11-01", note="nah"
    )
    assert created["url"] == "https://yousty.ch/lehrstellen/1"
    assert created["status"] == "open"
    assert created["source"] == "app"
    assert created["created_by_name"] == "Admin"
    assert created["deadline"] == "2026-11-01"
    assert client.get("/api/suggestions", headers=admin_headers).json()[0]["id"] == created["id"]


@pytest.mark.parametrize("url", ["www.yousty.ch/x", "ftp://yousty.ch/x", "javascript:alert(1)", "", "https://" + "a" * 500])
def test_create_refuses_other_links(client, admin_headers, url):
    assert client.post("/api/suggestions", json={"url": url}, headers=admin_headers).status_code == 422


def test_patch_and_clear_deadline(client, admin_headers):
    s = post_suggestion(client, admin_headers, deadline="2026-11-01")
    response = client.patch(
        f"/api/suggestions/{s['id']}", json={"company": "Coop", "deadline": None}, headers=admin_headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["company"] == "Coop"
    assert response.json()["deadline"] is None


def test_patch_url_updates_duplicate_key(client, admin_headers, db):
    s = post_suggestion(client, admin_headers)
    client.patch(f"/api/suggestions/{s['id']}", json={"url": "https://www.jobs.ch/z/"}, headers=admin_headers)
    assert db.get(models.Suggestion, s["id"]).url_key == "https://jobs.ch/z"


def test_delete(client, admin_headers):
    s = post_suggestion(client, admin_headers)
    assert client.delete(f"/api/suggestions/{s['id']}", headers=admin_headers).status_code == 204
    assert client.get("/api/suggestions", headers=admin_headers).json() == []


def test_apply_creates_application(client, admin_headers):
    sohn = create_user(client, admin_headers, "Sohn")
    s = post_suggestion(client, admin_headers, company="Migros", position="Informatiker", location="Bern", note="toll")
    sohn_headers = login(client, "Sohn", "5678")
    response = client.post(f"/api/suggestions/{s['id']}/apply", json={}, headers=sohn_headers)
    assert response.status_code == 201, response.text
    application = client.get(f"/api/applications/{response.json()['application_id']}", headers=admin_headers).json()
    assert (application["company"], application["position"], application["location"]) == ("Migros", "Informatiker", "Bern")
    assert application["posting_url"] == s["url"]
    assert application["notes"] == "toll"
    after = client.get("/api/suggestions", headers=admin_headers).json()[0]
    assert after["status"] == "applied"
    assert after["decided_by_name"] == sohn["name"]
    assert after["application"]["id"] == application["id"]


def test_apply_needs_a_company(client, admin_headers):
    s = post_suggestion(client, admin_headers)
    assert client.post(f"/api/suggestions/{s['id']}/apply", json={}, headers=admin_headers).status_code == 422
    response = client.post(f"/api/suggestions/{s['id']}/apply", json={"company": " Coop "}, headers=admin_headers)
    assert response.status_code == 201
    assert client.get("/api/suggestions", headers=admin_headers).json()[0]["company"] == "Coop"


def test_apply_twice_is_409_and_creates_one_application(client, admin_headers):
    s = post_suggestion(client, admin_headers, company="Migros")
    assert client.post(f"/api/suggestions/{s['id']}/apply", json={}, headers=admin_headers).status_code == 201
    assert client.post(f"/api/suggestions/{s['id']}/apply", json={}, headers=admin_headers).status_code == 409
    assert len(client.get("/api/applications", headers=admin_headers).json()) == 1


def test_decline_and_reopen(client, admin_headers):
    s = post_suggestion(client, admin_headers)
    response = client.post(f"/api/suggestions/{s['id']}/decline", json={"reason": "zu weit"}, headers=admin_headers)
    assert response.json()["status"] == "declined"
    assert response.json()["decline_reason"] == "zu weit"
    assert client.post(f"/api/suggestions/{s['id']}/decline", json={}, headers=admin_headers).status_code == 409
    reopened = client.post(f"/api/suggestions/{s['id']}/reopen", headers=admin_headers).json()
    assert (reopened["status"], reopened["decline_reason"], reopened["decided_by_name"]) == ("open", "", None)
    assert client.post(f"/api/suggestions/{s['id']}/reopen", headers=admin_headers).status_code == 409


def test_reopen_keeps_the_application(client, admin_headers):
    s = post_suggestion(client, admin_headers, company="Migros")
    client.post(f"/api/suggestions/{s['id']}/apply", json={}, headers=admin_headers)
    reopened = client.post(f"/api/suggestions/{s['id']}/reopen", headers=admin_headers).json()
    assert reopened["application"] is None
    assert len(client.get("/api/applications", headers=admin_headers).json()) == 1


def test_deleted_application_leaves_the_suggestion_applied(client, admin_headers):
    s = post_suggestion(client, admin_headers, company="Migros")
    app_id = client.post(f"/api/suggestions/{s['id']}/apply", json={}, headers=admin_headers).json()["application_id"]
    assert client.delete(f"/api/applications/{app_id}", headers=admin_headers).status_code == 204
    after = client.get("/api/suggestions", headers=admin_headers).json()[0]
    assert (after["status"], after["application"]) == ("applied", None)


def test_deadline_passed(client, admin_headers):
    s = post_suggestion(client, admin_headers, deadline="2020-01-01")
    assert s["deadline_passed"] is True
    assert post_suggestion(client, admin_headers, "https://jobs.ch/2", deadline="2099-01-01")["deadline_passed"] is False


def test_unknown_suggestion_is_404(client, admin_headers):
    assert client.post("/api/suggestions/99/decline", json={}, headers=admin_headers).status_code == 404


def test_dashboard_counts_open_suggestions(client, admin_headers):
    post_suggestion(client, admin_headers, "https://jobs.ch/1")
    declined = post_suggestion(client, admin_headers, "https://jobs.ch/2")
    client.post(f"/api/suggestions/{declined['id']}/decline", json={}, headers=admin_headers)
    assert client.get("/api/dashboard", headers=admin_headers).json()["suggestion_count"] == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_suggestions.py -q`
Expected: the new tests FAIL with 404 (no route)

- [ ] **Step 3: Add the schemas**

In `backend/app/schemas.py`, change the first import line to:

```python
from datetime import date, datetime
```

Append at the end:

```python
def clean_link(value: str | None) -> str | None:
    """A trimmed http(s) link; anything else is refused."""
    if value is None:
        return None
    value = value.strip()
    if not value.lower().startswith(("http://", "https://")) or len(value) <= len("https://"):
        raise ValueError("Der Link muss mit http:// oder https:// beginnen")
    return value


class SuggestionIn(BaseModel):
    url: str = Field(max_length=500)
    company: str = Field("", max_length=200)
    position: str = Field("", max_length=200)
    location: str = Field("", max_length=200)
    deadline: date | None = None
    note: str = ""

    check_url = field_validator("url")(clean_link)


class SuggestionPatch(BaseModel):
    """Fields left out stay unchanged; null clears only the deadline."""

    url: str | None = Field(None, max_length=500)
    company: str | None = Field(None, max_length=200)
    position: str | None = Field(None, max_length=200)
    location: str | None = Field(None, max_length=200)
    deadline: date | None = None
    note: str | None = None

    check_url = field_validator("url")(clean_link)


class SuggestionApplyIn(BaseModel):
    """Overrides for the new application; left out means the suggestion's value."""

    company: str | None = Field(None, max_length=200)
    position: str | None = Field(None, max_length=200)
    location: str | None = Field(None, max_length=200)


class SuggestionDeclineIn(BaseModel):
    reason: str = ""


class SuggestionCheckIn(BaseModel):
    url: str = Field(max_length=500)

    check_url = field_validator("url")(clean_link)
```

Note: `"https://" + "a" * 500` is longer than 500, so `max_length` refuses it with 422 before the validator.

- [ ] **Step 4: Add the view**

In `backend/app/views.py`, change the first import to `from datetime import date, datetime` and append:

```python
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
```

- [ ] **Step 5: Add the router**

Create `backend/app/suggestions_api.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from . import auth, models, schemas, suggestions, views
from .applications_api import new_mail_tag
from .database import get_db
from .timeutil import local_date, utcnow

router = APIRouter(tags=["suggestions"], dependencies=[Depends(auth.get_current_user)])

OPEN = models.SuggestionStatus.OPEN.value


def _get(db: Session, suggestion_id: int) -> models.Suggestion:
    s = db.get(models.Suggestion, suggestion_id)
    if s is None:
        raise HTTPException(404, "Vorschlag nicht gefunden")
    return s


def _get_open(db: Session, suggestion_id: int) -> models.Suggestion:
    s = _get(db, suggestion_id)
    if s.status != OPEN:
        raise HTTPException(409, "Über diesen Vorschlag ist schon entschieden")
    return s


def _out(s: models.Suggestion) -> dict:
    return views.suggestion_out(s, local_date(utcnow()))


@router.get("/suggestions")
def list_suggestions(db: Session = Depends(get_db)):
    items = db.query(models.Suggestion).order_by(models.Suggestion.created_at.desc(), models.Suggestion.id.desc())
    return [_out(s) for s in items]


@router.post("/suggestions", status_code=201)
def create_suggestion(
    body: schemas.SuggestionIn, user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)
):
    s = models.Suggestion(**body.model_dump(), url_key=suggestions.normalize_url(body.url), created_by=user.id)
    db.add(s)
    db.commit()
    db.refresh(s)
    return _out(s)


@router.patch("/suggestions/{suggestion_id}")
def update_suggestion(suggestion_id: int, body: schemas.SuggestionPatch, db: Session = Depends(get_db)):
    s = _get(db, suggestion_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is None and key != "deadline":
            continue
        setattr(s, key, value)
    s.url_key = suggestions.normalize_url(s.url)
    db.commit()
    db.refresh(s)
    return _out(s)


@router.delete("/suggestions/{suggestion_id}", status_code=204)
def delete_suggestion(suggestion_id: int, db: Session = Depends(get_db)):
    db.delete(_get(db, suggestion_id))
    db.commit()


@router.post("/suggestions/{suggestion_id}/apply", status_code=201)
def apply_suggestion(
    suggestion_id: int,
    body: schemas.SuggestionApplyIn,
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    s = _get_open(db, suggestion_id)
    company = (body.company if body.company is not None else s.company).strip()
    position = (body.position if body.position is not None else s.position).strip()
    location = (body.location if body.location is not None else s.location).strip()
    if not company:
        raise HTTPException(422, "Firma fehlt")
    application = models.Application(
        company=company,
        position=position,
        location=location,
        posting_url=s.url,
        notes=s.note,
        mail_tag=new_mail_tag(db),
        created_by=user.id,
    )
    db.add(application)
    db.flush()
    s.company, s.position, s.location = company, position, location
    s.status = models.SuggestionStatus.APPLIED.value
    s.application_id = application.id
    s.decided_by = user.id
    s.decided_at = utcnow()
    db.commit()
    return {"application_id": application.id}


@router.post("/suggestions/{suggestion_id}/decline")
def decline_suggestion(
    suggestion_id: int,
    body: schemas.SuggestionDeclineIn,
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    s = _get_open(db, suggestion_id)
    s.status = models.SuggestionStatus.DECLINED.value
    s.decline_reason = body.reason.strip()
    s.decided_by = user.id
    s.decided_at = utcnow()
    db.commit()
    db.refresh(s)
    return _out(s)


@router.post("/suggestions/{suggestion_id}/reopen")
def reopen_suggestion(suggestion_id: int, db: Session = Depends(get_db)):
    s = _get(db, suggestion_id)
    if s.status == OPEN:
        raise HTTPException(409, "Der Vorschlag ist schon offen")
    s.status = OPEN
    s.decline_reason = ""
    s.decided_by = None
    s.decided_at = None
    s.application_id = None
    db.commit()
    db.refresh(s)
    return _out(s)
```

- [ ] **Step 6: Register the router and add the dashboard count**

In `backend/app/main.py`, add `suggestions_api` to the import from `.` (keep the names sorted) and below the last `include_router` line add:

```python
app.include_router(suggestions_api.router, prefix="/api")
```

In `backend/app/applications_api.py`, replace the last line of `dashboard`:

```python
    return {"counts": counts, "due": due, "inbox_count": inbox_count}
```

with:

```python
    suggestion_count = (
        db.query(models.Suggestion).filter(models.Suggestion.status == models.SuggestionStatus.OPEN.value).count()
    )
    return {"counts": counts, "due": due, "inbox_count": inbox_count, "suggestion_count": suggestion_count}
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_suggestions.py -q`
Expected: PASS

- [ ] **Step 8: Run the whole suite**

Run: `venv/bin/pytest -q`
Expected: all pass

- [ ] **Step 9: Commit**

```bash
git add backend/app/schemas.py backend/app/views.py backend/app/suggestions_api.py backend/app/applications_api.py backend/app/main.py tests/test_suggestions.py
git commit -m "feat(suggestions): API to post, edit, apply, decline and reopen suggestions"
```

---

### Task 3: Page title with SSRF guard, and the `check` endpoint

**Files:**
- Create: `backend/app/pagetitle.py`
- Modify: `backend/app/suggestions_api.py`
- Test: `tests/test_pagetitle.py`

**Interfaces:**
- Consumes: Task 1 `suggestions.find_duplicates`; Task 2 router and `schemas.SuggestionCheckIn`
- Produces:
  - `pagetitle.fetch_title(url: str) -> str | None`
  - `pagetitle.extract_title(html: str) -> str | None`
  - internal seams the tests replace: `pagetitle._resolve(host: str, port: int) -> list[str]` (all addresses) and `pagetitle._request(scheme: str, host: str, ip: str, port: int, target: str) -> tuple[int, str | None, str, bytes]` (status, Location, Content-Type, body)
  - `POST /api/suggestions/check` → `{"duplicates": [...], "title": str | None}`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pagetitle.py`:

```python
import pytest

from app import pagetitle
from helpers import create_application


@pytest.fixture
def web(monkeypatch):
    """A fake internet: hostname -> addresses, (host, target) -> response."""
    dns: dict[str, list[str]] = {"yousty.ch": ["8.8.8.8"]}
    pages: dict[tuple[str, str], tuple[int, str | None, str, bytes]] = {}
    requests: list[tuple[str, str, str, int, str]] = []

    def resolve(host, port):
        if host not in dns:
            raise pagetitle.Refused(f"Unbekannter Host: {host}")
        return dns[host]

    def request(scheme, host, ip, port, target):
        requests.append((scheme, host, ip, port, target))
        return pages.get((host, target), (404, None, "text/html", b""))

    monkeypatch.setattr(pagetitle, "_resolve", resolve)
    monkeypatch.setattr(pagetitle, "_request", request)
    return dns, pages, requests


def html(title_tags: str, charset="utf-8"):
    return (200, None, f"text/html; charset={charset}", f"<html><head>{title_tags}</head></html>".encode(charset))


def test_title_from_og_title_then_title(web):
    _dns, pages, requests = web
    pages[("yousty.ch", "/a")] = html('<title>Fallback</title><meta property="og:title" content="Lehrstelle &amp; Mehr">')
    pages[("yousty.ch", "/b?x=1")] = html("<title>\n  Informatiker   EFZ\n</title>")
    assert pagetitle.fetch_title("https://yousty.ch/a") == "Lehrstelle & Mehr"
    assert pagetitle.fetch_title("https://yousty.ch/b?x=1#frag") == "Informatiker EFZ"
    # Connects to the address it checked, with the hostname for TLS and the Host header
    assert requests[0] == ("https", "yousty.ch", "8.8.8.8", 443, "/a")


def test_title_in_latin1(web):
    _dns, pages, _requests = web
    pages[("yousty.ch", "/")] = html("<title>Bäcker/in EFZ, Zürich</title>", charset="iso-8859-1")
    assert pagetitle.fetch_title("http://yousty.ch") == "Bäcker/in EFZ, Zürich"


def test_title_is_cut_to_200_characters(web):
    _dns, pages, _requests = web
    pages[("yousty.ch", "/")] = html(f"<title>{'x' * 300}</title>")
    assert len(pagetitle.fetch_title("https://yousty.ch/")) == 200


@pytest.mark.parametrize(
    "url",
    ["ftp://yousty.ch/a", "https://yousty.ch:8443/a", "file:///etc/passwd", "https:///nohost"],
)
def test_refuses_other_schemes_and_ports(web, url):
    assert pagetitle.fetch_title(url) is None
    assert web[2] == []


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.0.0.5", "192.168.1.10", "172.16.0.1", "169.254.169.254", "100.64.0.1", "0.0.0.0",
     "::1", "fe80::1", "fd00::1", "::ffff:192.168.1.10", "224.0.0.1"],
)
def test_refuses_non_public_addresses(web, address):
    dns, pages, requests = web
    dns["nas.example.ch"] = ["8.8.8.8", address]  # one bad address is enough
    pages[("nas.example.ch", "/")] = html("<title>NAS</title>")
    assert pagetitle.fetch_title("https://nas.example.ch/") is None
    assert requests == []


def test_follows_redirects_to_public_hosts_only(web):
    dns, pages, requests = web
    dns["jobs.ch"] = ["8.8.4.4"]
    dns["intern.example.ch"] = ["192.168.1.10"]
    pages[("yousty.ch", "/short")] = (301, "https://jobs.ch/long", "text/html", b"")
    pages[("jobs.ch", "/long")] = html("<title>Koch EFZ</title>")
    assert pagetitle.fetch_title("https://yousty.ch/short") == "Koch EFZ"
    pages[("yousty.ch", "/evil")] = (302, "http://intern.example.ch/admin", "text/html", b"")
    assert pagetitle.fetch_title("https://yousty.ch/evil") is None
    assert ("http", "intern.example.ch", "192.168.1.10", 80, "/admin") not in requests


def test_gives_up_after_three_redirects(web):
    _dns, pages, requests = web
    for i in range(5):
        pages[("yousty.ch", f"/{i}")] = (302, f"/{i + 1}", "text/html", b"")
    pages[("yousty.ch", "/5")] = html("<title>Ende</title>")
    assert pagetitle.fetch_title("https://yousty.ch/0") is None
    assert len(requests) == 4


@pytest.mark.parametrize(
    "response",
    [(500, None, "text/html", b"<title>x</title>"), (200, None, "application/pdf", b"%PDF"), (200, None, "text/html", b"")],
)
def test_no_title_for_errors_and_other_content(web, response):
    web[1][("yousty.ch", "/")] = response
    assert pagetitle.fetch_title("https://yousty.ch/") is None


def test_network_errors_give_none(web, monkeypatch):
    def broken(*args):
        raise TimeoutError("timed out")

    monkeypatch.setattr(pagetitle, "_request", broken)
    assert pagetitle.fetch_title("https://yousty.ch/") is None


def test_check_endpoint(client, admin_headers, web):
    web[1][("yousty.ch", "/a")] = html("<title>Informatiker EFZ</title>")
    create_application(client, admin_headers, "Migros", posting_url="https://www.yousty.ch/a/")
    response = client.post("/api/suggestions/check", json={"url": "https://yousty.ch/a"}, headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Informatiker EFZ"
    assert [(d["kind"], d["label"]) for d in body["duplicates"]] == [("application", "Migros")]


def test_check_endpoint_refuses_non_links(client, admin_headers):
    assert client.post("/api/suggestions/check", json={"url": "yousty.ch"}, headers=admin_headers).status_code == 422
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_pagetitle.py -q`
Expected: FAIL with `ImportError: cannot import name 'pagetitle'`

- [ ] **Step 3: Implement `pagetitle.py`**

Create `backend/app/pagetitle.py`:

```python
"""The title of a web page for a suggested link, without letting a link reach into the home network."""

import http.client
import ipaddress
import logging
import socket
import ssl
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5
MAX_BYTES = 1024 * 1024
MAX_REDIRECTS = 3
MAX_TITLE = 200
PORTS = {"http": 80, "https": 443}
REDIRECTS = {301, 302, 303, 307, 308}
USER_AGENT = "Mozilla/5.0 (compatible; FamilyJobTracking/1.0)"


class Refused(Exception):
    """The link may not be fetched."""


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def _resolve(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise Refused(f"Unbekannter Host: {host}") from exc
    return [info[4][0] for info in infos]


def _public_address(host: str, port: int) -> str:
    """The address to connect to; refused if any address of the host is not on the public internet."""
    addresses = _resolve(host, port)
    if not addresses or not all(_is_public(a) for a in addresses):
        raise Refused(f"{host} ist keine öffentliche Adresse")
    return addresses[0]


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """Connects to the checked address, so a second DNS answer can't point it elsewhere."""

    def __init__(self, host: str, ip: str, port: int):
        super().__init__(host, port, timeout=TIMEOUT_SECONDS)
        self._ip = ip

    def connect(self):
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, ip: str, port: int):
        super().__init__(host, port, timeout=TIMEOUT_SECONDS, context=ssl.create_default_context())
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _request(scheme: str, host: str, ip: str, port: int, target: str) -> tuple[int, str | None, str, bytes]:
    connection_class = _PinnedHTTPSConnection if scheme == "https" else _PinnedHTTPConnection
    connection = connection_class(host, ip, port)
    try:
        connection.request("GET", target, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
        response = connection.getresponse()
        return response.status, response.getheader("Location"), response.getheader("Content-Type", ""), response.read(
            MAX_BYTES
        )
    finally:
        connection.close()


def _split(url: str) -> tuple[str, str, int, str]:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in PORTS or not parts.hostname:
        raise Refused("Nur http- und https-Links")
    port = parts.port or PORTS[scheme]
    if port != PORTS[scheme]:
        raise Refused("Nur die Standard-Ports 80 und 443")
    target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    return scheme, parts.hostname, port, target


def _charset(content_type: str) -> str:
    for param in content_type.split(";")[1:]:
        key, _, value = param.partition("=")
        if key.strip().lower() == "charset" and value.strip():
            return value.strip().strip('"')
    return "utf-8"


class _TitleParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.og_title: str | None = None
        self.title_parts: list[str] = []
        self._in_title = False
        self._title_done = False

    def handle_starttag(self, tag, attrs):
        values = {key.lower(): value or "" for key, value in attrs}
        kind = (values.get("property") or values.get("name") or "").lower()
        if tag == "meta" and kind == "og:title" and values.get("content") and self.og_title is None:
            self.og_title = values["content"]
        elif tag == "title" and not self._title_done:
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title" and self._in_title:
            self._in_title = False
            self._title_done = True

    def handle_data(self, data):
        if self._in_title:
            self.title_parts.append(data)


def extract_title(html: str) -> str | None:
    """og:title, else <title>; whitespace collapsed, at most MAX_TITLE characters."""
    parser = _TitleParser()
    parser.feed(html)
    title = parser.og_title or "".join(parser.title_parts)
    title = " ".join(title.split())[:MAX_TITLE]
    return title or None


def fetch_title(url: str) -> str | None:
    """The page's title, or None if it can't or may not be fetched."""
    try:
        for _ in range(MAX_REDIRECTS + 1):
            scheme, host, port, target = _split(url)
            ip = _public_address(host, port)
            status, location, content_type, body = _request(scheme, host, ip, port, target)
            if status in REDIRECTS and location:
                url = urljoin(url, location)
                continue
            if status != 200 or "text/html" not in content_type.lower():
                return None
            try:
                text = body.decode(_charset(content_type), errors="replace")
            except LookupError:
                text = body.decode("utf-8", errors="replace")
            return extract_title(text)
        return None
    except Exception as exc:
        logger.info("No title for %s: %s", url, exc)
        return None
```

- [ ] **Step 4: Add the endpoint**

In `backend/app/suggestions_api.py`, change the import line to include `pagetitle`:

```python
from . import auth, models, pagetitle, schemas, suggestions, views
```

Add this endpoint **above** `@router.patch("/suggestions/{suggestion_id}")` (a fixed path, so it reads clearly before the `{suggestion_id}` routes):

```python
@router.post("/suggestions/check")
def check_link(body: schemas.SuggestionCheckIn, db: Session = Depends(get_db)):
    """Earlier suggestions and applications with this link, and the page's title as a suggested position."""
    return {"duplicates": suggestions.find_duplicates(db, body.url), "title": pagetitle.fetch_title(body.url)}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_pagetitle.py -q`
Expected: PASS

- [ ] **Step 6: Run the whole suite**

Run: `venv/bin/pytest -q`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add backend/app/pagetitle.py backend/app/suggestions_api.py tests/test_pagetitle.py
git commit -m "feat(suggestions): fetch a link's page title without reaching private addresses"
```

---

### Task 4: Suggestions by e-mail (`bewerbungen+vorschlag@`)

**Files:**
- Modify: `backend/app/mailparse.py`, `backend/app/suggestions.py`, `backend/app/inbound.py`, `backend/app/inbox_api.py`
- Test: `tests/test_suggestions.py`

**Interfaces:**
- Consumes: Task 1 (`SUGGESTION_TAG`, `MAX_MAIL_LINKS`, `extract_links`, `clean_subject`, `normalize_url`)
- Produces:
  - `ParsedMail.html_links: list[str]` (the `href`s of the HTML part, in order)
  - `suggestions.create_from_mail(db, user: models.User, links: list[str], subject: str) -> list[models.Suggestion]`
  - `inbound.process` returns `models.Email | list[models.Suggestion] | None`
  - `/api/inbound` answers `{"status": "suggestions", "suggestion_ids": [...]}` for suggestion mails

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_suggestions.py`:

```python
SUGGESTION_ADDRESS = "bewerbungen+vorschlag@example.ch"


@pytest.fixture
def inbound(monkeypatch):
    monkeypatch.setenv("INBOUND_SECRET", INBOUND_SECRET)


def test_mail_from_a_user_creates_suggestions(client, admin_headers, inbound, db):
    create_user(client, admin_headers, "Papa", email="papa@example.ch")
    raw = build_mail(
        sender="Papa <papa@example.ch>",
        to=SUGGESTION_ADDRESS,
        subject="Fwd: Lehrstelle Informatiker EFZ",
        body="Schau mal https://www.yousty.ch/x?utm_source=share",
    )
    response = post_mail(client, raw)
    assert response.json()["status"] == "suggestions"
    s = db.query(models.Suggestion).one()
    assert (s.url, s.position, s.source) == ("https://www.yousty.ch/x?utm_source=share", "Lehrstelle Informatiker EFZ", "mail")
    assert s.creator.name == "Papa"
    assert db.query(models.Email).count() == 0


def test_mail_with_several_links_and_duplicates(client, admin_headers, inbound, db):
    create_user(client, admin_headers, "Papa", email="papa@example.ch")
    post_suggestion(client, admin_headers, "https://jobs.ch/1")
    links = " ".join(f"https://yousty.ch/{i}" for i in range(12))
    raw = build_mail(sender="papa@example.ch", to=SUGGESTION_ADDRESS, subject="Ideen", body=f"https://jobs.ch/1/ {links}")
    ids = post_mail(client, raw).json()["suggestion_ids"]
    assert len(ids) == 9  # 10 links read, the first is a duplicate
    new = db.query(models.Suggestion).filter(models.Suggestion.source == "mail").all()
    assert all(s.position == "" for s in new)  # several links: the subject says nothing about each


def test_html_only_mail_uses_the_links_behind_the_text(client, admin_headers, inbound, db):
    create_user(client, admin_headers, "Papa", email="papa@example.ch")
    raw = build_mail(
        sender="papa@example.ch",
        to=SUGGESTION_ADDRESS,
        body=None,
        html='<p><a href="https://www.yousty.ch/lehrstelle/42">Lehrstelle ansehen</a></p>',
    )
    assert post_mail(client, raw).json()["status"] == "suggestions"
    assert db.query(models.Suggestion).one().url == "https://www.yousty.ch/lehrstelle/42"


def test_bcc_to_the_suggestion_address_counts(client, admin_headers, inbound, db):
    create_user(client, admin_headers, "Papa", email="papa@example.ch")
    raw = build_mail(sender="papa@example.ch", to="sohn@example.ch", body="https://yousty.ch/a")
    assert post_mail(client, raw, envelope_to=SUGGESTION_ADDRESS).json()["status"] == "suggestions"


@pytest.mark.parametrize(
    "sender, body",
    [("fremd@spam.example", "https://yousty.ch/a"), ("papa@example.ch", "Keine Links hier")],
)
def test_other_suggestion_mails_land_in_the_inbox(client, admin_headers, inbound, db, sender, body):
    create_user(client, admin_headers, "Papa", email="papa@example.ch")
    response = post_mail(client, build_mail(sender=sender, to=SUGGESTION_ADDRESS, body=body))
    assert response.json()["status"] == "stored"
    assert response.json()["application_id"] is None
    assert db.query(models.Suggestion).count() == 0
    assert db.query(models.Email).count() == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_suggestions.py -q -k mail`
Expected: FAIL (status `stored` instead of `suggestions`)

- [ ] **Step 3: Collect the HTML links in `mailparse.py`**

In `backend/app/mailparse.py`, add a field to `ParsedMail` after `attachments`:

```python
    html_links: list[str] = field(default_factory=list)  # hrefs of the HTML part, for suggestion mails
```

Add below `html_to_text`:

```python
class _LinkCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href.strip())


def _html_links(msg: EmailMessage) -> list[str]:
    part = msg.get_body(preferencelist=("html",))
    if part is None:
        return []
    collector = _LinkCollector()
    collector.feed(part.get_content())
    collector.close()
    return collector.links
```

In `parse`, add the argument to the `ParsedMail(...)` call after `attachments=_attachments(msg),`:

```python
            html_links=_html_links(msg),
```

- [ ] **Step 4: Add `create_from_mail` to `suggestions.py`**

Append to `backend/app/suggestions.py`:

```python
def create_from_mail(db: Session, user: models.User, links: list[str], subject: str) -> list[models.Suggestion]:
    """A suggestion for each new link (at most MAX_MAIL_LINKS read); the subject names the position if there is one."""
    known = {key for (key,) in db.query(models.Suggestion.url_key)}
    created: list[models.Suggestion] = []
    for link in links[:MAX_MAIL_LINKS]:
        key = normalize_url(link)
        if key in known or len(link) > 500:
            continue
        known.add(key)
        created.append(
            models.Suggestion(url=link, url_key=key, source="mail", created_by=user.id)
        )
    if len(created) == 1:
        created[0].position = clean_subject(subject)[:200]
    db.add_all(created)
    return created
```

Note: the duplicate check here covers earlier suggestions only, matching the test (`https://jobs.ch/1/` is skipped because a suggestion exists). Links that match an application are kept as suggestions; the page shows the duplicate warning only in the form.

- [ ] **Step 5: Branch in `inbound.process`**

In `backend/app/inbound.py`, change the import line `from . import mailparse, models` to:

```python
from . import mailparse, models, suggestions
```

In `process`, insert directly after the duplicate Message-ID check (the `if db.query(models.Email).filter_by(message_id=...)` block) and before `known_tags = ...`:

```python
    if mailparse.find_tag(mail.recipients, {suggestions.SUGGESTION_TAG}):
        sender = db.query(models.User).filter(models.User.email == mail.from_addr).first()
        links = suggestions.extract_links(mail.body_text, *mail.html_links)
        if sender is not None and links:
            created = suggestions.create_from_mail(db, sender, links, mail.subject)
            db.commit()
            return created
        # From someone else, or without a link: keep it like any untagged mail
```

Change the signature's return annotation to `-> models.Email | list[models.Suggestion] | None` and the docstring to:

```python
    """Store an incoming e-mail in its application's timeline, otherwise in the inbox.

    The application is the one of the +tag, or for an untagged e-mail the only active one its sender's domain fits.
    A mail from a user to the +vorschlag address turns its links into suggestions instead (returned as a list).

    Returns None when the same Message-ID was stored before (the worker delivered it twice)."""
```

- [ ] **Step 6: Answer suggestion mails in `inbox_api.py`**

In `receive_mail`, replace:

```python
    email = inbound.process(db, raw, request.headers.get("x-envelope-to"))
    if email is None:
        return {"status": "duplicate"}
```

with:

```python
    email = inbound.process(db, raw, request.headers.get("x-envelope-to"))
    if email is None:
        return {"status": "duplicate"}
    if isinstance(email, list):
        return {"status": "suggestions", "suggestion_ids": [s.id for s in email]}
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_suggestions.py -q`
Expected: PASS

- [ ] **Step 8: Run the whole suite**

Run: `venv/bin/pytest -q`
Expected: all pass (existing inbound tests unchanged)

- [ ] **Step 9: Commit**

```bash
git add backend/app/mailparse.py backend/app/suggestions.py backend/app/inbound.py backend/app/inbox_api.py tests/test_suggestions.py
git commit -m "feat(suggestions): turn links mailed to +vorschlag into suggestions"
```

---

### Task 5: Suggestions in the daily reminder

**Files:**
- Modify: `backend/app/reminders.py`
- Test: `tests/test_reminders.py`

**Interfaces:**
- Consumes: Task 1 (`models.Suggestion`, `suggestions.label`)
- Produces: `reminders.SuggestionItem(id: int, label: str, deadline: date | None)`; `Digest.new_suggestions` and `Digest.deadline_soon` (lists, default empty); `render` adds a "Vorschläge" section

- [ ] **Step 1: Write the failing tests**

In `tests/test_reminders.py`, change the imports at the top to
`from datetime import date, datetime, timedelta` and `from app import models, reminders, suggestions`, then append:

```python
def add_suggestion(db, url, created_at, deadline=None, status="open", company=""):
    db.add(
        models.Suggestion(
            url=url, url_key=suggestions.normalize_url(url), created_at=created_at, deadline=deadline,
            status=status, company=company,
        )
    )
    db.commit()


def test_digest_lists_new_and_soon_due_suggestions(db):
    settings = get_settings(db)
    settings.last_reminder_sent_at = AFTER - timedelta(days=1)
    db.commit()
    add_suggestion(db, "https://jobs.ch/new", AFTER - timedelta(hours=2), company="Neu AG")
    add_suggestion(db, "https://jobs.ch/old-soon", AFTER - timedelta(days=5), deadline=date(2026, 10, 20))
    add_suggestion(db, "https://jobs.ch/old-later", AFTER - timedelta(days=5), deadline=date(2026, 10, 30))
    add_suggestion(db, "https://jobs.ch/old-passed", AFTER - timedelta(days=5), deadline=date(2026, 10, 14))
    add_suggestion(db, "https://jobs.ch/declined", AFTER - timedelta(hours=2), status="declined")
    digest = reminders.build_digest(db, AFTER)
    assert [s.label for s in digest.new_suggestions] == ["Neu AG"]
    assert [s.label for s in digest.deadline_soon] == ["jobs.ch"]
    assert digest.deadline_soon[0].deadline == date(2026, 10, 20)
    assert not digest.empty


def test_all_open_suggestions_are_new_before_the_first_reminder(db):
    add_suggestion(db, "https://jobs.ch/a", AFTER - timedelta(days=30))
    assert len(reminders.build_digest(db, AFTER).new_suggestions) == 1


def test_old_suggestions_without_near_deadline_send_nothing(db):
    settings = get_settings(db)
    settings.last_reminder_sent_at = AFTER - timedelta(days=1)
    db.commit()
    add_suggestion(db, "https://jobs.ch/a", AFTER - timedelta(days=5))
    assert reminders.build_digest(db, AFTER).empty


def test_render_suggestions_and_subject_priority():
    soon = reminders.SuggestionItem(1, "Migros – Koch", date(2026, 10, 20))
    new = reminders.SuggestionItem(2, "jobs.ch", None)
    subject, text, html_body = reminders.render(
        reminders.Digest(due=[], inbox_count=1, new_suggestions=[new], deadline_soon=[soon]), "https://app.example.ch"
    )
    assert subject == "Bewerbungen: Frist läuft ab"
    assert "Migros – Koch (Frist 20.10.2026)" in text
    assert "jobs.ch" in text
    assert "https://app.example.ch/vorschlaege" in text
    assert "Vorschläge" in html_body
    subject, _text, _html = reminders.render(
        reminders.Digest(due=[], inbox_count=1, new_suggestions=[new, new]), ""
    )
    assert subject == "Bewerbungen: 2 neue Vorschläge"
    subject, _text, _html = reminders.render(reminders.Digest(due=[], inbox_count=0, new_suggestions=[new]), "")
    assert subject == "Bewerbungen: 1 neuer Vorschlag"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_reminders.py -q`
Expected: FAIL (`SuggestionItem` missing / unexpected keyword `new_suggestions`)

- [ ] **Step 3: Extend the digest**

In `backend/app/reminders.py`:

1. Change the imports to:

```python
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
```

```python
from . import config, database, models, suggestions
```

```python
from .timeutil import local_date, to_local, to_utc, utcnow
```

2. Add after `DueItem`:

```python
@dataclass
class SuggestionItem:
    id: int
    label: str
    deadline: date | None
```

3. Replace the `Digest` class with:

```python
@dataclass
class Digest:
    due: list[DueItem]
    inbox_count: int
    new_suggestions: list[SuggestionItem] = field(default_factory=list)
    deadline_soon: list[SuggestionItem] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.due and self.inbox_count == 0 and not self.new_suggestions and not self.deadline_soon
```

4. Add above `build_digest`:

```python
SOON_DAYS = 7


def _suggestion_lists(db: Session, since: datetime | None, today: date) -> tuple[list, list]:
    """Open suggestions created after the last reminder, and older ones whose deadline is within SOON_DAYS."""
    new, soon = [], []
    open_ones = (
        db.query(models.Suggestion)
        .filter(models.Suggestion.status == models.SuggestionStatus.OPEN.value)
        .order_by(models.Suggestion.created_at, models.Suggestion.id)
    )
    for s in open_ones:
        item = SuggestionItem(s.id, suggestions.label(s), s.deadline)
        if since is None or s.created_at > since:
            new.append(item)
        elif s.deadline and today <= s.deadline <= today + timedelta(days=SOON_DAYS):
            soon.append(item)
    soon.sort(key=lambda item: item.deadline)
    return new, soon
```

5. In `build_digest`, replace `return Digest(due, inbox_count)` with:

```python
    new, soon = _suggestion_lists(db, settings.last_reminder_sent_at, local_date(now))
    return Digest(due, inbox_count, new, soon)
```

- [ ] **Step 4: Extend `render`**

In `render`, replace the subject block:

```python
    due_count = len(digest.due)
    if due_count:
        subject = f"Bewerbungen: {due_count} {_plural(due_count, 'Nachfrage', 'Nachfragen')} fällig"
    elif digest.inbox_count:
```

with:

```python
    due_count = len(digest.due)
    new_count = len(digest.new_suggestions)
    if due_count:
        subject = f"Bewerbungen: {due_count} {_plural(due_count, 'Nachfrage', 'Nachfragen')} fällig"
    elif digest.deadline_soon:
        subject = "Bewerbungen: Frist läuft ab"
    elif new_count:
        subject = f"Bewerbungen: {new_count} {_plural(new_count, 'neuer Vorschlag', 'neue Vorschläge')}"
    elif digest.inbox_count:
```

Then insert, directly before `if digest.inbox_count:` (the paragraph about the Posteingang):

```python
    if digest.new_suggestions or digest.deadline_soon:
        text_lines.append("Vorschläge:")
        html_parts.append("<h2>Vorschläge</h2>")
        for heading, items in (("Frist läuft bald ab", digest.deadline_soon), ("Neu", digest.new_suggestions)):
            if not items:
                continue
            text_lines.append(f"{heading}:")
            html_parts.append(f"<p>{heading}:</p><ul>")
            for item in items:
                deadline = f" (Frist {item.deadline.strftime('%d.%m.%Y')})" if item.deadline else ""
                text_lines.append(f"- {item.label}{deadline}")
                html_parts.append(f"<li>{html.escape(item.label)}{deadline}</li>")
            html_parts.append("</ul>")
        url = link("/vorschlaege")
        if url:
            text_lines.append(f"Zu den Vorschlägen: {url}")
            html_parts.append(f'<p><a href="{html.escape(url)}">Zu den Vorschlägen</a></p>')
        text_lines.append("")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_reminders.py -q`
Expected: PASS (old tests too: `Digest(due, inbox_count)` still works through the defaults)

- [ ] **Step 6: Run the whole suite**

Run: `venv/bin/pytest -q`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add backend/app/reminders.py tests/test_reminders.py
git commit -m "feat(reminders): list new suggestions and near deadlines in the daily mail"
```

---

### Task 6: Suggestions in the export

**Files:**
- Modify: `backend/app/export.py`
- Test: `tests/test_settings.py`

**Interfaces:**
- Consumes: Task 1 (`models.Suggestion`); the existing `_csv`, `_date`, `_datetime` helpers of `export.py`
- Produces: `vorschlaege.csv` and `suggestions.csv` in the ZIP

- [ ] **Step 1: Write the failing test**

Append to `tests/test_settings.py`:

```python
def test_export_suggestions(client, admin_headers):
    s = client.post(
        "/api/suggestions",
        json={"url": "https://yousty.ch/1", "company": "Bäckerei Zürich", "deadline": "2026-11-01"},
        headers=admin_headers,
    ).json()
    client.post(f"/api/suggestions/{s['id']}/decline", json={"reason": "zu früh"}, headers=admin_headers)
    archive = zipfile.ZipFile(io.BytesIO(client.get("/api/export", headers=admin_headers).content))
    header, *rows = read_csv(archive, "vorschlaege.csv")
    row = dict(zip(header, rows[0]))
    assert row["Status"] == "Nicht interessiert"
    assert row["Firma"] == "Bäckerei Zürich"
    assert row["Frist"] == "01.11.2026"
    assert row["Link"] == "https://yousty.ch/1"
    assert row["Vorgeschlagen von"] == "Admin"
    assert row["Grund"] == "zu früh"
    raw_header, *_ = read_csv(archive, "suggestions.csv")
    assert "url_key" in raw_header
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `venv/bin/pytest tests/test_settings.py -q -k suggestions`
Expected: FAIL with `KeyError: "There is no item named 'vorschlaege.csv' in the archive"`

- [ ] **Step 3: Implement**

In `backend/app/export.py`:

1. Add `("suggestions", models.Suggestion),` as the last entry of `TABLES`.

2. Add after `CHANNEL_LABELS`:

```python
SUGGESTION_LABELS = {"open": "Offen", "applied": "Beworben", "declined": "Nicht interessiert"}
```

3. Add after `_timeline`:

```python
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
```

4. In `build_zip`, after `archive.writestr("zeitleiste.csv", _timeline(applications))` add:

```python
        archive.writestr("vorschlaege.csv", _suggestions(db))
```

5. `_cell` writes a `date` as `str(date)` (ISO), which is right for the raw table; no change needed.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_settings.py -q`
Expected: PASS

- [ ] **Step 5: Run the whole suite**

Run: `venv/bin/pytest -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/export.py tests/test_settings.py
git commit -m "feat(export): suggestions as readable vorschlaege.csv and raw table"
```

---

### Task 7: Frontend page "Vorschläge"

**Files:**
- Modify: `frontend/src/types.ts`, `frontend/src/components/Layout.tsx`, `frontend/src/App.tsx`
- Create: `frontend/src/pages/Suggestions.tsx`, `frontend/src/components/SuggestionCard.tsx`

**Interfaces:**
- Consumes: Task 2 and 3 endpoints, `GET /api/settings` (`inbound_address`), `/api/dashboard.suggestion_count`
- Produces: route `/vorschlaege`; `LayoutContext.setSuggestionCount`

- [ ] **Step 1: Types**

In `frontend/src/types.ts`, add `suggestion_count: number;` to `Dashboard` (after `inbox_count`), add `setSuggestionCount: (count: number) => void;` to `LayoutContext`, and append:

```ts
export type SuggestionStatus = 'open' | 'applied' | 'declined';

export interface SuggestionFormValues {
    url: string;
    company: string;
    position: string;
    location: string;
    deadline: string; // YYYY-MM-DD or '' for none
    note: string;
}

export interface Suggestion extends Omit<SuggestionFormValues, 'deadline'> {
    id: number;
    deadline: string | null;
    status: SuggestionStatus;
    decline_reason: string;
    source: 'app' | 'mail';
    created_at: string;
    created_by_name: string | null;
    decided_at: string | null;
    decided_by_name: string | null;
    application: { id: number; company: string; position: string } | null;
    deadline_passed: boolean;
}

export interface SuggestionDuplicate {
    kind: 'suggestion' | 'application';
    id: number;
    label: string;
    date: string;
    status?: SuggestionStatus;
}

export interface SuggestionCheck {
    duplicates: SuggestionDuplicate[];
    title: string | null;
}
```

- [ ] **Step 2: Navigation and route**

In `frontend/src/components/Layout.tsx`:

- add `const [suggestionCount, setSuggestionCount] = useState(0);` next to `inboxCount`
- in the effect, after `setInboxCount(...)`, add `setSuggestionCount(dashboard.data.suggestion_count);`
- add this `NavLink` between Übersicht and Posteingang:

```tsx
                        <NavLink to="/vorschlaege" className={linkClass}>
                            Vorschläge
                            {suggestionCount > 0 && (
                                <span className="ml-1 rounded-full bg-blue-600 px-2 text-xs text-white">
                                    {suggestionCount}
                                </span>
                            )}
                        </NavLink>
```

- change the outlet to `<Outlet context={{ setInboxCount, setSuggestionCount } satisfies LayoutContext} />`

In `frontend/src/App.tsx`, import `Suggestions from './pages/Suggestions'` and add `<Route path="vorschlaege" element={<Suggestions />} />` after the `bewerbungen/:id` route.

- [ ] **Step 3: The card**

Create `frontend/src/components/SuggestionCard.tsx`:

```tsx
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import api, { errorMessage } from '../api';
import { formatDate, formatDateTime } from '../labels';
import { useToast } from '../ToastContext';
import type { Suggestion } from '../types';
import { BUTTON, BUTTON_DANGER, BUTTON_SECONDARY, CARD } from '../ui';

const SOON_MS = 7 * 24 * 60 * 60 * 1000;

function host(url: string): string {
    try {
        return new URL(url).hostname.replace(/^www\./, '');
    } catch {
        return url;
    }
}

function title(s: Suggestion): string {
    return [s.company, s.position].filter(Boolean).join(' – ') || host(s.url);
}

function Deadline({ s }: { s: Suggestion }) {
    if (!s.deadline) return null;
    const soon = !s.deadline_passed && new Date(s.deadline).getTime() - Date.now() < SOON_MS;
    const color = s.deadline_passed ? 'text-red-400' : soon ? 'text-amber-400' : 'text-slate-400';
    return (
        <span className={color}>
            {s.deadline_passed ? 'Frist abgelaufen' : 'Frist'} {formatDate(s.deadline)}
        </span>
    );
}

interface Props {
    suggestion: Suggestion;
    onChanged: () => void;
    onEdit: (s: Suggestion) => void;
}

export default function SuggestionCard({ suggestion: s, onChanged, onEdit }: Props) {
    const toast = useToast();
    const navigate = useNavigate();
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

    const apply = () => {
        let company = s.company;
        if (!company) {
            company = window.prompt('Bei welcher Firma ist die Lehrstelle?')?.trim() ?? '';
            if (!company) return;
        }
        run(async () => {
            const response = await api.post<{ application_id: number }>(`/api/suggestions/${s.id}/apply`, { company });
            navigate(`/bewerbungen/${response.data.application_id}`);
        });
    };

    const decline = () => {
        const reason = window.prompt('Nicht interessiert. Grund (optional):');
        if (reason === null) return;
        run(async () => {
            await api.post(`/api/suggestions/${s.id}/decline`, { reason });
            onChanged();
        });
    };

    const reopen = () =>
        run(async () => {
            await api.post(`/api/suggestions/${s.id}/reopen`);
            onChanged();
        });

    const remove = () => {
        if (!window.confirm('Diesen Vorschlag löschen?')) return;
        run(async () => {
            await api.delete(`/api/suggestions/${s.id}`);
            onChanged();
        });
    };

    return (
        <div className={`${CARD} space-y-2`}>
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <a href={s.url} target="_blank" rel="noreferrer" className="font-semibold text-blue-300 hover:underline">
                    {title(s)}
                </a>
                {s.location && <span className="text-sm text-slate-400">{s.location}</span>}
                <span className="text-sm">
                    <Deadline s={s} />
                </span>
            </div>
            {s.note && <p className="whitespace-pre-wrap text-sm text-slate-300">{s.note}</p>}
            <p className="text-xs text-slate-500">
                Vorgeschlagen von {s.created_by_name ?? 'unbekannt'} am {formatDateTime(s.created_at)}
                {s.source === 'mail' && ' (per Mail)'} · {host(s.url)}
            </p>
            {s.status === 'applied' && (
                <p className="text-sm text-emerald-400">
                    Beworben
                    {s.application ? (
                        <>
                            : <Link to={`/bewerbungen/${s.application.id}`} className="underline">zur Bewerbung</Link>
                        </>
                    ) : (
                        ' (Bewerbung gelöscht)'
                    )}
                </p>
            )}
            {s.status === 'declined' && (
                <p className="text-sm text-slate-400">
                    Nicht interessiert{s.decline_reason && `: ${s.decline_reason}`} ({s.decided_by_name ?? 'unbekannt'})
                </p>
            )}
            <div className="flex flex-wrap gap-2">
                {s.status === 'open' ? (
                    <>
                        <button type="button" className={BUTTON} disabled={busy} onClick={apply}>
                            Bewerben
                        </button>
                        <button type="button" className={BUTTON_SECONDARY} disabled={busy} onClick={decline}>
                            Nicht interessiert
                        </button>
                        <button type="button" className={BUTTON_SECONDARY} disabled={busy} onClick={() => onEdit(s)}>
                            Bearbeiten
                        </button>
                    </>
                ) : (
                    <button type="button" className={BUTTON_SECONDARY} disabled={busy} onClick={reopen}>
                        Wieder öffnen
                    </button>
                )}
                <button type="button" className={BUTTON_DANGER} disabled={busy} onClick={remove}>
                    Löschen
                </button>
            </div>
        </div>
    );
}
```

- [ ] **Step 4: The page**

Create `frontend/src/pages/Suggestions.tsx`:

```tsx
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { useOutletContext } from 'react-router-dom';
import api, { errorMessage } from '../api';
import SuggestionCard from '../components/SuggestionCard';
import { formatDate } from '../labels';
import { useToast } from '../ToastContext';
import type { AppSettings, LayoutContext, Suggestion, SuggestionCheck, SuggestionFormValues } from '../types';
import { BUTTON, BUTTON_SECONDARY, CARD, INPUT } from '../ui';

const EMPTY: SuggestionFormValues = { url: '', company: '', position: '', location: '', deadline: '', note: '' };

// "www.yousty.ch/..." -> "https://www.yousty.ch/...": people paste links without the scheme
function withScheme(url: string): string {
    const trimmed = url.trim();
    return !trimmed || /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
}

// Open ones by deadline (soonest first), those without one after them, newest first
function byDeadline(a: Suggestion, b: Suggestion): number {
    if (a.deadline && b.deadline) return a.deadline.localeCompare(b.deadline);
    if (a.deadline) return -1;
    if (b.deadline) return 1;
    return b.created_at.localeCompare(a.created_at);
}

function mailAddress(inbound: string): string | null {
    const [local, domain] = inbound.split('@');
    return local && domain ? `${local}+vorschlag@${domain}` : null;
}

export default function Suggestions() {
    const toast = useToast();
    const { setSuggestionCount } = useOutletContext<LayoutContext>();
    const [items, setItems] = useState<Suggestion[] | null>(null);
    const [address, setAddress] = useState<string | null>(null);
    const [values, setValues] = useState<SuggestionFormValues>(EMPTY);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [check, setCheck] = useState<SuggestionCheck | null>(null);
    const [checkedUrl, setCheckedUrl] = useState('');
    const [saving, setSaving] = useState(false);
    const [showDone, setShowDone] = useState(false);

    const [version, setVersion] = useState(0);
    const load = useCallback(() => setVersion((v) => v + 1), []);

    useEffect(() => {
        api.get<Suggestion[]>('/api/suggestions')
            .then((response) => {
                setItems(response.data);
                setSuggestionCount(response.data.filter((s) => s.status === 'open').length);
            })
            .catch((e) => toast(errorMessage(e)));
    }, [version, toast, setSuggestionCount]);

    useEffect(() => {
        api.get<AppSettings>('/api/settings')
            .then((response) => setAddress(mailAddress(response.data.inbound_address)))
            .catch(() => {});
    }, []);

    const set = (key: keyof SuggestionFormValues) => (value: string) => setValues((v) => ({ ...v, [key]: value }));

    const checkUrl = async () => {
        const url = withScheme(values.url);
        if (!url || url === checkedUrl || editingId !== null) return;
        setCheckedUrl(url);
        setValues((v) => ({ ...v, url }));
        try {
            const response = await api.post<SuggestionCheck>('/api/suggestions/check', { url });
            setCheck(response.data);
            const title = response.data.title;
            if (title) setValues((v) => (v.position ? v : { ...v, position: title }));
        } catch {
            setCheck(null);
        }
    };

    const reset = () => {
        setValues(EMPTY);
        setEditingId(null);
        setCheck(null);
        setCheckedUrl('');
    };

    const submit = async (event: FormEvent) => {
        event.preventDefault();
        setSaving(true);
        const body = { ...values, url: withScheme(values.url), deadline: values.deadline || null };
        try {
            if (editingId === null) {
                await api.post('/api/suggestions', body);
                toast('Vorschlag gespeichert', 'success');
            } else {
                await api.patch(`/api/suggestions/${editingId}`, body);
                toast('Vorschlag geändert', 'success');
            }
            reset();
            load();
        } catch (e) {
            toast(errorMessage(e));
        } finally {
            setSaving(false);
        }
    };

    const edit = (s: Suggestion) => {
        setEditingId(s.id);
        setCheck(null);
        setValues({
            url: s.url,
            company: s.company,
            position: s.position,
            location: s.location,
            deadline: s.deadline ?? '',
            note: s.note,
        });
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    if (items === null) return <p className="text-slate-400">Laden…</p>;
    const open = items.filter((s) => s.status === 'open').sort(byDeadline);
    const done = items.filter((s) => s.status !== 'open');

    return (
        <div className="space-y-4">
            <h1 className="text-2xl font-bold">Vorschläge</h1>
            <form onSubmit={submit} className={`${CARD} space-y-3`}>
                <h2 className="font-semibold">{editingId === null ? 'Lehrstelle vorschlagen' : 'Vorschlag bearbeiten'}</h2>
                <label className="block text-sm">
                    <span className="mb-1 block text-slate-400">Link zur Lehrstelle</span>
                    <input
                        type="text"
                        inputMode="url"
                        required
                        value={values.url}
                        onChange={(e) => set('url')(e.target.value)}
                        onBlur={checkUrl}
                        placeholder="https://www.yousty.ch/…"
                        className={INPUT}
                    />
                </label>
                {check && check.duplicates.length > 0 && (
                    <ul className="rounded-lg border border-amber-700 bg-amber-900/30 p-2 text-sm text-amber-200">
                        {check.duplicates.map((d) => (
                            <li key={`${d.kind}-${d.id}`}>
                                {d.kind === 'suggestion'
                                    ? `Schon vorgeschlagen am ${formatDate(d.date)}: ${d.label}`
                                    : `Bewerbung existiert: ${d.label}`}
                            </li>
                        ))}
                    </ul>
                )}
                <div className="grid gap-3 sm:grid-cols-2">
                    <label className="block text-sm">
                        <span className="mb-1 block text-slate-400">Stelle</span>
                        <input value={values.position} onChange={(e) => set('position')(e.target.value)} className={INPUT} />
                    </label>
                    <label className="block text-sm">
                        <span className="mb-1 block text-slate-400">Firma</span>
                        <input value={values.company} onChange={(e) => set('company')(e.target.value)} className={INPUT} />
                    </label>
                    <label className="block text-sm">
                        <span className="mb-1 block text-slate-400">Ort</span>
                        <input value={values.location} onChange={(e) => set('location')(e.target.value)} className={INPUT} />
                    </label>
                    <label className="block text-sm">
                        <span className="mb-1 block text-slate-400">Bewerbungsfrist</span>
                        <input
                            type="date"
                            value={values.deadline}
                            onChange={(e) => set('deadline')(e.target.value)}
                            className={INPUT}
                        />
                    </label>
                </div>
                <label className="block text-sm">
                    <span className="mb-1 block text-slate-400">Notiz</span>
                    <textarea value={values.note} onChange={(e) => set('note')(e.target.value)} rows={2} className={INPUT} />
                </label>
                <div className="flex flex-wrap gap-2">
                    <button type="submit" className={BUTTON} disabled={saving}>
                        {editingId === null ? 'Vorschlagen' : 'Speichern'}
                    </button>
                    {editingId !== null && (
                        <button type="button" className={BUTTON_SECONDARY} onClick={reset}>
                            Abbrechen
                        </button>
                    )}
                </div>
                {address && (
                    <p className="text-xs text-slate-500">
                        Auch per Mail: Link an <span className="text-slate-300">{address}</span> schicken (von deiner
                        gespeicherten Adresse aus).
                    </p>
                )}
            </form>

            <h2 className="text-lg font-semibold">Offen ({open.length})</h2>
            {open.length === 0 && <p className="text-slate-400">Keine offenen Vorschläge.</p>}
            {open.map((s) => (
                <SuggestionCard key={s.id} suggestion={s} onChanged={load} onEdit={edit} />
            ))}

            {done.length > 0 && (
                <div className="space-y-3">
                    <button type="button" className="text-sm text-slate-400 hover:text-white" onClick={() => setShowDone((v) => !v)}>
                        {showDone ? '▾' : '▸'} Erledigt ({done.length})
                    </button>
                    {showDone &&
                        done.map((s) => <SuggestionCard key={s.id} suggestion={s} onChanged={load} onEdit={edit} />)}
                </div>
            )}
        </div>
    );
}
```

- [ ] **Step 5: Lint and build**

Run: `cd frontend && npm run lint && npm run build`
Expected: no lint errors; `✓ built`. Fix any formatting complaints the way the linter asks.

- [ ] **Step 6: Commit**

```bash
git add frontend/src
git commit -m "feat(frontend): Vorschläge page with form, duplicate warning and decisions"
```

---

### Task 8: Documentation and final check

**Files:**
- Modify: `README.md`, `README_DOCKER.md`

- [ ] **Step 1: README.md**

In the feature list of `README.md` (find it with `grep -n "^- " README.md | head -20`), add a bullet in the same style:

```markdown
- **Vorschläge:** anyone posts a link to an open apprenticeship (in the app, or by mailing it to
  `bewerbungen+vorschlag@<domain>`); the page title fills in the position, duplicates are flagged,
  and "Bewerben" turns a suggestion into an application.
```

- [ ] **Step 2: README_DOCKER.md**

In the section "Incoming e-mails", after the paragraph that starts with "Each application has its own address", add:

```markdown
Links mailed to `bewerbungen+vorschlag@<domain>` from a user's saved address become suggestions on
the page **Vorschläge** (one per link, at most 10 per mail). This needs no extra Email Routing rule.
From any other sender, or without a link, the mail lands in the Posteingang.
```

- [ ] **Step 3: Full verification**

Run:
```bash
venv/bin/pytest -q
(cd frontend && npm run lint && npm run build)
(cd cloudflare/email-worker && npm test)
```
Expected: all backend tests pass; frontend lint clean and build succeeds; worker tests pass.

- [ ] **Step 4: Commit**

```bash
git add README.md README_DOCKER.md
git commit -m "docs: suggestions page and the +vorschlag mail address"
```
