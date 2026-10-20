# Documents (Unterlagen) and Dossier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A tab where the son keeps his application documents by category, and a button that builds one dossier PDF from them in the usual order.

**Architecture:** A new `documents` table and router like the suggestions feature. Files go through new helpers in `files.py` into `files/_unterlagen/<folder>/`. The dossier is built in memory by `backend/app/dossier.py` (pypdf for PDFs, Pillow + pillow-heif for images). The frontend gets a `/unterlagen` page.

**Tech Stack:** FastAPI, SQLAlchemy 2, SQLite, pytest; pypdf, Pillow, pillow-heif; React 19, TypeScript, Tailwind, axios.

**Spec:** `docs/superpowers/specs/2026-10-20-documents-design.md`

## Global Constraints

- New Python dependencies only `pypdf==6.21.1`, `Pillow==13.0.0`, `pillow-heif==1.8.1` (wheels exist for CPython 3.14 x86_64); no new npm dependency.
- UI text German; code, comments, docs, commits English.
- Every endpoint needs a login; everyone sees all documents.
- Categories and dossier order: `letter` (Motivationsschreiben, folder `motivationsschreiben`), `cv` (Lebenslauf, `lebenslauf`), `report` (Zeugnis, `zeugnis`), `certificate` (Zertifikat/Test, `zertifikat`), `other` (Andere, `andere`).
- Files: `files/_unterlagen/<folder>/<YYYY-MM-DD>_<folder>_<title-slug>.<ext>`; at most 25 MB per file; any type accepted.
- New upload and category change: `position = lowest position in the category - 1` (0 if empty).
- Outdated sets `in_dossier = false`; back to current leaves `in_dossier`.
- Dossier images: EXIF orientation applied, RGB, fit into 1240 × 1754 px (A4 at 150 dpi, never enlarged), centred on white A4, JPEG quality 80.
- Dossier file name `Bewerbungsdossier_<YYYY-MM-DD>.pdf` (local date).
- Backend tests: `venv/bin/pytest -q` from the repo root; frontend: `cd frontend && npm run lint && npm run build`.
- Commit messages end with:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01YA8keQBSJPgVNmbSLJoGmM
  ```

## Review Focus

- A phone photo uploaded as HEIC with content type `application/octet-stream`: it is recognised by its extension and goes into the dossier. (Task 3 test.)
- A document title with dots or slashes (`Zeugnis 2./3. Sek`): the stored file name keeps the uploaded extension and has no path separators. (Task 1 test.)
- A document whose file was removed from the NAS by hand: the list still loads, download answers 404, the dossier skips it with "Datei fehlt". (Task 2 and Task 3 tests.)
- Moving a category change into an empty category, and ↑ on the first document: no error, positions stay unique. (Task 2 test.)
- A PDF protected only against editing (owner password, empty user password): it goes into the dossier. (Task 3 test.)

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/requirements.txt` (modify) | the three new packages |
| `backend/app/models.py` (modify) | `DocumentCategory`, `CATEGORY_ORDER`, `CATEGORY_FOLDERS`, `CATEGORY_LABELS`, `Document` |
| `backend/app/files.py` (modify) | `DOCUMENTS_FOLDER`, `store_document`, `move_document` |
| `backend/app/schemas.py` (modify) | `DocumentPatch`, `DocumentMoveIn` |
| `backend/app/views.py` (modify) | `document_out` |
| `backend/app/dossier.py` (create) | `kind`, `image_page`, `build` |
| `backend/app/documents_api.py` (create) | `/api/documents…` endpoints |
| `backend/app/main.py` (modify) | register the router |
| `backend/app/export.py` (modify) | `unterlagen.csv`, `documents.csv` |
| `tests/test_documents.py` (create) | Tasks 1, 2 |
| `tests/test_dossier.py` (create) | Task 3 |
| `tests/test_settings.py` (modify) | Task 4 |
| `frontend/src/types.ts`, `api.ts`, `labels.ts`, `components/Layout.tsx`, `App.tsx` (modify) | types, `openFile`, labels, tab, route |
| `frontend/src/pages/Documents.tsx`, `components/DocumentRow.tsx` (create) | page and one row |
| `README.md`, `README_DOCKER.md` (modify) | feature and folder |

---

### Task 1: Dependencies, model and file helpers

**Files:**
- Modify: `backend/requirements.txt`, `backend/app/models.py`, `backend/app/files.py`
- Test: `tests/test_documents.py`

**Interfaces:**
- Produces:
  - `models.DocumentCategory` (str enum `LETTER="letter"`, `CV="cv"`, `REPORT="report"`, `CERTIFICATE="certificate"`, `OTHER="other"`)
  - `models.CATEGORY_ORDER: list[str]` (keys in dossier order), `models.CATEGORY_FOLDERS: dict[str, str]`, `models.CATEGORY_LABELS: dict[str, str]`
  - `models.Document` (columns of the spec, relationship `creator`)
  - `files.DOCUMENTS_FOLDER = "_unterlagen"`
  - `files.store_document(category: str, day: date, title: str, original_name: str, content: bytes) -> str`
  - `files.move_document(rel_path: str, category: str) -> str`

- [ ] **Step 1: Add the dependencies**

Append to `backend/requirements.txt`:

```
# Dossier PDF: merging PDFs, and photos (also HEIC from phones) as pages
pypdf==6.21.1
Pillow==13.0.0
pillow-heif==1.8.1
```

Run: `venv/bin/pip install -r backend/requirements.txt -q && venv/bin/python -c "import pypdf, PIL, pillow_heif; print('ok')"`
Expected: `ok`

- [ ] **Step 2: Write the failing tests**

Create `tests/test_documents.py` (later tasks append; their imports are here already):

```python
import io
from datetime import date

import pytest

from app import config, files, models
from helpers import create_user, login


def test_category_tables_agree():
    assert models.CATEGORY_ORDER == ["letter", "cv", "report", "certificate", "other"]
    assert set(models.CATEGORY_FOLDERS) == set(models.CATEGORY_ORDER) == set(models.CATEGORY_LABELS)
    assert models.CATEGORY_FOLDERS["report"] == "zeugnis"


def test_store_document_names_the_file_after_title_and_date():
    path = files.store_document("report", date(2026, 7, 1), "Zeugnis 2. Sek, 1. Semester", "scan.PDF", b"x")
    assert path == "_unterlagen/zeugnis/2026-07-01_zeugnis_Zeugnis-2-Sek-1-Semester.pdf"
    assert (config.files_dir() / path).read_bytes() == b"x"
    again = files.store_document("report", date(2026, 7, 1), "Zeugnis 2. Sek, 1. Semester", "scan.pdf", b"y")
    assert again == "_unterlagen/zeugnis/2026-07-01_zeugnis_Zeugnis-2-Sek-1-Semester_2.pdf"


def test_store_document_title_with_dots_and_slashes_keeps_the_extension():
    path = files.store_document("certificate", date(2026, 3, 5), "Multicheck 2./3. Teil", "IMG_1234.heic", b"x")
    assert path == "_unterlagen/zertifikat/2026-03-05_zertifikat_Multicheck-2-3-Teil.heic"


def test_store_document_without_extension():
    assert files.store_document("other", date(2026, 1, 2), "Notizen", "notes", b"x").endswith("_andere_Notizen")


def test_move_document_to_another_category():
    path = files.store_document("other", date(2026, 1, 2), "Stellwerk", "s.pdf", b"x")
    moved = files.move_document(path, "certificate")
    assert moved == "_unterlagen/zertifikat/2026-01-02_zertifikat_Stellwerk.pdf"
    assert (config.files_dir() / moved).exists()
    assert not (config.files_dir() / path).exists()
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_documents.py -q`
Expected: FAIL with `AttributeError: module 'app.models' has no attribute 'CATEGORY_ORDER'`

- [ ] **Step 4: Add the model**

Append to `backend/app/models.py` (`Date` is imported already since the suggestions feature):

```python
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
```

- [ ] **Step 5: Add the file helpers**

In `backend/app/files.py`, below `INBOX_FOLDER`:

```python
# The son's application documents, one subfolder per category
DOCUMENTS_FOLDER = "_unterlagen"
```

Append at the end of the file (it needs `models` only for the folder names, so import inside to keep `files` free of model imports at load time):

```python
def _document_folder(category: str) -> str:
    from .models import CATEGORY_FOLDERS

    return CATEGORY_FOLDERS[category]


def store_document(category: str, day: date, title: str, original_name: str, content: bytes) -> str:
    """Save a document as _unterlagen/<folder>/<date>_<folder>_<title>.<ext of the upload>."""
    folder = _document_folder(category)
    _stem, ext = safe_filename(original_name)
    # The title is slugified first, so dots in it can't be taken for the extension
    name = slugify(title, lower=False, max_len=80, fallback="dokument") + ext
    return _store(f"{DOCUMENTS_FOLDER}/{folder}", day, folder, name, content)


def move_document(rel_path: str, category: str) -> str:
    """Move a document's file into the folder of its new category."""
    folder = _document_folder(category)
    return _move(rel_path, f"{DOCUMENTS_FOLDER}/{folder}", folder)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_documents.py -q`
Expected: PASS

Note for `test_store_document_without_extension`: `_store` builds `<date>_andere_Notizen` with an empty extension; the assertion checks the end of the path.

- [ ] **Step 7: Run the whole suite and commit**

Run: `venv/bin/pytest -q` → all pass.

```bash
git add backend/requirements.txt backend/app/models.py backend/app/files.py tests/test_documents.py
git commit -m "feat(documents): model, categories and file storage under _unterlagen"
```

---

### Task 2: Documents API

**Files:**
- Modify: `backend/app/schemas.py`, `backend/app/views.py`, `backend/app/main.py`
- Create: `backend/app/documents_api.py`
- Test: `tests/test_documents.py`

**Interfaces:**
- Consumes: Task 1 (`models.Document`, `CATEGORY_ORDER`, `files.store_document`, `files.move_document`)
- Produces:
  - `views.document_out(d: models.Document) -> dict` with keys `id, category, title, issued_on (YYYY-MM-DD|None), note, outdated, in_dossier, position, filename, content_type, size, created_at, created_by_name, dossier_ok`
  - `views.document_out` calls `dossier.kind(content_type, filename)` (Task 3). Until Task 3 exists, `documents_api` provides it: see Step 4 note.
  - endpoints `GET/POST /api/documents`, `PATCH/DELETE /api/documents/{id}`, `POST /api/documents/{id}/move`, `GET /api/documents/{id}/file`
  - `documents_api.ordered(db) -> list[models.Document]` (category order, then position, then id)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_documents.py`:

```python
def upload(client, headers, name="zeugnis.pdf", content=b"%PDF-1.4 x", category="report", **fields):
    response = client.post(
        "/api/documents",
        data={"category": category, **fields},
        files={"file": (name, content, "application/pdf")},
        headers=headers,
    )
    return response


def uploaded(client, headers, *args, **kwargs) -> dict:
    response = upload(client, headers, *args, **kwargs)
    assert response.status_code == 201, response.text
    return response.json()


def listed(client, headers) -> list[dict]:
    response = client.get("/api/documents", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_documents_need_login(client):
    assert client.get("/api/documents").status_code == 401


def test_upload_and_list(client, admin_headers, db):
    d = uploaded(client, admin_headers, title="Zeugnis 1. Semester", issued_on="2026-02-01", note="gut")
    assert (d["category"], d["title"], d["issued_on"], d["note"]) == ("report", "Zeugnis 1. Semester", "2026-02-01", "gut")
    assert (d["filename"], d["size"], d["in_dossier"], d["outdated"]) == ("zeugnis.pdf", 10, True, False)
    assert d["created_by_name"] == "Admin"
    stored = db.get(models.Document, d["id"])
    assert stored.path == "_unterlagen/zeugnis/2026-02-01_zeugnis_Zeugnis-1-Semester.pdf"
    assert listed(client, admin_headers)[0]["id"] == d["id"]


def test_title_defaults_to_the_file_name(client, admin_headers):
    assert uploaded(client, admin_headers, name="Multicheck_Informatik.pdf")["title"] == "Multicheck_Informatik"


@pytest.mark.parametrize(
    "kwargs, status",
    [({"category": "zeugnis"}, 422), ({"content": b""}, 422), ({"issued_on": "gestern"}, 422)],
)
def test_upload_refuses_bad_input(client, admin_headers, kwargs, status):
    assert upload(client, admin_headers, **kwargs).status_code == status


def test_upload_refuses_files_over_25_mb(client, admin_headers, monkeypatch):
    from app import documents_api

    monkeypatch.setattr(documents_api, "MAX_UPLOAD_BYTES", 5)
    assert upload(client, admin_headers, content=b"123456").status_code == 413


def test_list_order_is_category_then_newest_first(client, admin_headers):
    first = uploaded(client, admin_headers, title="Zeugnis alt")
    second = uploaded(client, admin_headers, title="Zeugnis neu")
    cv = uploaded(client, admin_headers, title="CV", category="cv")
    other = uploaded(client, admin_headers, title="Foto", category="other")
    assert [d["id"] for d in listed(client, admin_headers)] == [cv["id"], second["id"], first["id"], other["id"]]


def test_patch_fields_and_clear_date(client, admin_headers):
    d = uploaded(client, admin_headers, issued_on="2026-02-01")
    response = client.patch(
        f"/api/documents/{d['id']}", json={"title": "Neu", "note": "x", "issued_on": None}, headers=admin_headers
    )
    assert response.status_code == 200, response.text
    assert (response.json()["title"], response.json()["note"], response.json()["issued_on"]) == ("Neu", "x", None)


def test_patch_category_moves_the_file_and_puts_it_first(client, admin_headers, db):
    existing = uploaded(client, admin_headers, title="Stellwerk alt", category="certificate")
    d = uploaded(client, admin_headers, title="Stellwerk", issued_on="2026-01-02", category="other")
    moved = client.patch(f"/api/documents/{d['id']}", json={"category": "certificate"}, headers=admin_headers).json()
    assert moved["category"] == "certificate"
    db.expire_all()
    path = db.get(models.Document, d["id"]).path
    assert path == "_unterlagen/zertifikat/2026-01-02_zertifikat_Stellwerk.pdf"
    assert (config.files_dir() / path).exists()
    certificates = [x["id"] for x in listed(client, admin_headers) if x["category"] == "certificate"]
    assert certificates == [d["id"], existing["id"]]


def test_patch_category_into_an_empty_category(client, admin_headers):
    d = uploaded(client, admin_headers, category="other")
    response = client.patch(f"/api/documents/{d['id']}", json={"category": "letter"}, headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["category"] == "letter"


def test_patch_refuses_unknown_category(client, admin_headers):
    d = uploaded(client, admin_headers)
    assert client.patch(f"/api/documents/{d['id']}", json={"category": "x"}, headers=admin_headers).status_code == 422


def test_outdated_takes_it_out_of_the_dossier(client, admin_headers):
    d = uploaded(client, admin_headers)
    outdated = client.patch(f"/api/documents/{d['id']}", json={"outdated": True}, headers=admin_headers).json()
    assert (outdated["outdated"], outdated["in_dossier"]) == (True, False)
    current = client.patch(f"/api/documents/{d['id']}", json={"outdated": False}, headers=admin_headers).json()
    assert (current["outdated"], current["in_dossier"]) == (False, False)


def test_move_up_and_down_and_at_the_edges(client, admin_headers):
    a = uploaded(client, admin_headers, title="A")
    b = uploaded(client, admin_headers, title="B")  # newest first: B, A
    c = uploaded(client, admin_headers, title="C")  # C, B, A

    def move(doc, direction):
        response = client.post(f"/api/documents/{doc['id']}/move", json={"direction": direction}, headers=admin_headers)
        assert response.status_code == 200, response.text
        return [x["title"] for x in response.json()]

    assert move(a, "up") == ["C", "A", "B"]
    assert move(c, "up") == ["C", "A", "B"]  # already first
    assert move(b, "down") == ["C", "A", "B"]  # already last
    assert move(c, "down") == ["A", "C", "B"]
    positions = [x["position"] for x in listed(client, admin_headers)]
    assert len(set(positions)) == 3


def test_move_refuses_unknown_direction(client, admin_headers):
    d = uploaded(client, admin_headers)
    assert client.post(f"/api/documents/{d['id']}/move", json={"direction": "left"}, headers=admin_headers).status_code == 422


def test_download_inline_with_original_name(client, admin_headers):
    d = uploaded(client, admin_headers, name="Zeugnis Juli.pdf", content=b"%PDF-1.4 abc")
    response = client.get(f"/api/documents/{d['id']}/file", headers=admin_headers)
    assert response.status_code == 200
    assert response.content == b"%PDF-1.4 abc"
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline")


def test_missing_file_is_404_but_the_list_still_loads(client, admin_headers, db):
    d = uploaded(client, admin_headers)
    (config.files_dir() / db.get(models.Document, d["id"]).path).unlink()
    assert client.get(f"/api/documents/{d['id']}/file", headers=admin_headers).status_code == 404
    assert len(listed(client, admin_headers)) == 1


def test_delete_removes_the_file(client, admin_headers, db):
    d = uploaded(client, admin_headers)
    path = config.files_dir() / db.get(models.Document, d["id"]).path
    assert client.delete(f"/api/documents/{d['id']}", headers=admin_headers).status_code == 204
    assert not path.exists()
    assert listed(client, admin_headers) == []


def test_unknown_document_is_404(client, admin_headers):
    assert client.patch("/api/documents/99", json={}, headers=admin_headers).status_code == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_documents.py -q`
Expected: the new tests FAIL (404 from the missing routes; `test_unknown_document_is_404` may already pass for that reason, which is fine)

- [ ] **Step 3: Schemas**

Append to `backend/app/schemas.py`:

```python
DocumentCategoryName = Literal["letter", "cv", "report", "certificate", "other"]


class DocumentPatch(BaseModel):
    """Fields left out stay unchanged; null clears only the date."""

    category: DocumentCategoryName | None = None
    title: str | None = Field(None, max_length=200)
    issued_on: date | None = None
    note: str | None = None
    outdated: bool | None = None
    in_dossier: bool | None = None

    @field_validator("title")
    @classmethod
    def check_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Titel fehlt")
        return value


class DocumentMoveIn(BaseModel):
    direction: Literal["up", "down"]
```

and add `from typing import Literal` to the imports at the top of `schemas.py`.

- [ ] **Step 4: View and router**

Append to `backend/app/views.py`:

```python
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
```

Create a first version of `backend/app/dossier.py` with only the type check (Task 3 adds the rest):

```python
"""The application dossier: the son's documents as one PDF, in the usual order."""

import os

PDF_TYPES = {"application/pdf"}
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}


def kind(content_type: str, filename: str) -> str | None:
    """"pdf", "image", or None if it can't go into the dossier; by type, else by extension (phones send HEIC as
    application/octet-stream)."""
    content_type = (content_type or "").split(";")[0].strip().lower()
    ext = os.path.splitext(filename or "")[1].lower()
    if content_type in PDF_TYPES or ext in PDF_EXTENSIONS:
        return "pdf"
    if content_type in IMAGE_TYPES or ext in IMAGE_EXTENSIONS:
        return "image"
    return None
```

Create `backend/app/documents_api.py`:

```python
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import auth, models, schemas, views
from . import files as filestore
from .database import get_db
from .timeutil import local_date, utcnow

router = APIRouter(tags=["documents"], dependencies=[Depends(auth.get_current_user)])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def _get(db: Session, document_id: int) -> models.Document:
    d = db.get(models.Document, document_id)
    if d is None:
        raise HTTPException(404, "Unterlage nicht gefunden")
    return d


def ordered(db: Session) -> list[models.Document]:
    """All documents in dossier order: category, then position."""
    rank = {category: i for i, category in enumerate(models.CATEGORY_ORDER)}
    return sorted(db.query(models.Document), key=lambda d: (rank.get(d.category, len(rank)), d.position, d.id))


def _first_position(db: Session, category: str) -> int:
    lowest = db.query(func.min(models.Document.position)).filter(models.Document.category == category).scalar()
    return 0 if lowest is None else lowest - 1


@router.get("/documents")
def list_documents(db: Session = Depends(get_db)):
    return [views.document_out(d) for d in ordered(db)]


@router.post("/documents", status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    category: str = Form(...),
    title: str = Form(""),
    issued_on: str = Form(""),
    note: str = Form(""),
    user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    if category not in models.CATEGORY_ORDER:
        raise HTTPException(422, "Unbekannte Kategorie")
    try:
        issued = date.fromisoformat(issued_on) if issued_on.strip() else None
    except ValueError:
        raise HTTPException(422, "Ungültiges Datum")
    content = await file.read()
    if not content:
        raise HTTPException(422, "Die Datei ist leer")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"{file.filename} ist grösser als 25 MB")
    filename = file.filename or "dokument"
    title = title.strip()[:200] or (filename.rsplit(".", 1)[0] if "." in filename else filename)
    d = models.Document(
        category=category,
        title=title,
        issued_on=issued,
        note=note,
        position=_first_position(db, category),
        filename=filename,
        path=filestore.store_document(category, issued or local_date(utcnow()), title, filename, content),
        content_type=file.content_type or "application/octet-stream",
        size=len(content),
        created_by=user.id,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return views.document_out(d)


@router.patch("/documents/{document_id}")
def update_document(document_id: int, body: schemas.DocumentPatch, db: Session = Depends(get_db)):
    d = _get(db, document_id)
    changes = body.model_dump(exclude_unset=True)
    category = changes.pop("category", None)
    if category is not None and category != d.category:
        d.position = _first_position(db, category)
        d.path = filestore.move_document(d.path, category)
        d.category = category
    for key, value in changes.items():
        if value is None and key != "issued_on":
            continue
        setattr(d, key, value)
    if changes.get("outdated"):
        d.in_dossier = False
    db.commit()
    db.refresh(d)
    return views.document_out(d)


@router.post("/documents/{document_id}/move")
def move_document(document_id: int, body: schemas.DocumentMoveIn, db: Session = Depends(get_db)):
    """Swap with the neighbour in the same category; at the top or bottom nothing changes."""
    d = _get(db, document_id)
    siblings = [x for x in ordered(db) if x.category == d.category]
    index = siblings.index(d)
    other = index - 1 if body.direction == "up" else index + 1
    if 0 <= other < len(siblings):
        neighbour = siblings[other]
        if neighbour.position == d.position:
            # Equal positions (shouldn't happen) would make the swap a no-op: spread them first
            for i, x in enumerate(siblings):
                x.position = i
        d.position, neighbour.position = neighbour.position, d.position
        db.commit()
    return [views.document_out(x) for x in ordered(db) if x.category == d.category]


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: int, db: Session = Depends(get_db)):
    d = _get(db, document_id)
    filestore.delete(d.path)
    db.delete(d)
    db.commit()


@router.get("/documents/{document_id}/file")
def download_document(document_id: int, db: Session = Depends(get_db)):
    d = _get(db, document_id)
    path = filestore.absolute(d.path)
    if not path.exists():
        raise HTTPException(404, "Datei fehlt auf dem NAS")
    return FileResponse(path, media_type=d.content_type, filename=d.filename, content_disposition_type="inline")
```

In `backend/app/main.py`, add `documents_api` to the parenthesised import list (alphabetically, after `database`) and:

```python
app.include_router(documents_api.router, prefix="/api")
```

after the suggestions router.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_documents.py -q`
Expected: PASS

- [ ] **Step 6: Run the whole suite and commit**

Run: `venv/bin/pytest -q` → all pass.

```bash
git add backend/app tests/test_documents.py
git commit -m "feat(documents): API to upload, list, edit, reorder, download and delete documents"
```

---

### Task 3: Dossier PDF

**Files:**
- Modify: `backend/app/dossier.py`, `backend/app/documents_api.py`
- Test: `tests/test_dossier.py`

**Interfaces:**
- Consumes: Task 1 `models.Document`; Task 2 `documents_api.ordered`, router; `dossier.kind`
- Produces:
  - `dossier.A4_PX = (1240, 1754)`
  - `dossier.image_page(data: bytes) -> PIL.Image.Image` (white A4 canvas with the image fitted and centred)
  - `dossier.build(documents: list[models.Document]) -> Dossier` with `Dossier.pdf: bytes | None`, `parts: list[dict]` (`id, title, category, pages`), `skipped: list[dict]` (`id, title, reason`), `pages: int`
  - `GET /api/documents/dossier` → `{parts, skipped, pages, size}`; `GET /api/documents/dossier.pdf`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dossier.py`:

```python
import io

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from app import config, dossier, models


def pdf_bytes(pages=1, width=595, height=842, owner_password=None, user_password=None) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=width, height=height)
    if owner_password or user_password:
        writer.encrypt(user_password=user_password or "", owner_password=owner_password)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def image_bytes(size=(400, 300), fmt="PNG", color="red", exif_orientation=None) -> bytes:
    image = Image.new("RGB", size, color)
    buffer = io.BytesIO()
    kwargs = {}
    if exif_orientation:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation
        kwargs["exif"] = exif
    image.save(buffer, fmt, **kwargs)
    return buffer.getvalue()


def add(client, headers, name, content, content_type, category="report", **fields):
    response = client.post(
        "/api/documents",
        data={"category": category, **fields},
        files={"file": (name, content, content_type)},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def preview(client, headers):
    response = client.get("/api/documents/dossier", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_kind_by_type_and_extension():
    assert dossier.kind("application/pdf", "a.bin") == "pdf"
    assert dossier.kind("application/octet-stream", "IMG_0001.HEIC") == "image"
    assert dossier.kind("image/jpeg; charset=binary", "x") == "image"
    assert dossier.kind("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "cv.docx") is None


def test_image_page_is_a4_and_never_enlarged():
    page = dossier.image_page(image_bytes(size=(400, 300)))
    assert page.size == dossier.A4_PX
    bbox = Image.eval(page.convert("L"), lambda v: 255 - v).getbbox()  # where it isn't white
    assert (bbox[2] - bbox[0], bbox[3] - bbox[1]) == (400, 300)


def test_image_page_scales_large_photos_down():
    page = dossier.image_page(image_bytes(size=(4000, 3000), fmt="JPEG"))
    bbox = Image.eval(page.convert("L"), lambda v: 255 - v).getbbox()
    assert bbox[2] - bbox[0] == 1240  # landscape: limited by the page width


def test_image_page_applies_exif_orientation():
    # Stored landscape, EXIF says "rotate 90°": the page shows it in portrait
    page = dossier.image_page(image_bytes(size=(400, 200), fmt="JPEG", exif_orientation=6))
    bbox = Image.eval(page.convert("L"), lambda v: 255 - v).getbbox()
    assert bbox[3] - bbox[1] > bbox[2] - bbox[0]


def test_heic_photo_from_a_phone(client, admin_headers):
    import pillow_heif

    pillow_heif.register_heif_opener()
    buffer = io.BytesIO()
    Image.new("RGB", (300, 200), "blue").save(buffer, "HEIF")
    add(client, admin_headers, "IMG_0001.HEIC", buffer.getvalue(), "application/octet-stream", category="certificate")
    assert preview(client, admin_headers)["pages"] == 1


def test_dossier_order_pages_and_a4(client, admin_headers):
    report_old = add(client, admin_headers, "z1.pdf", pdf_bytes(2), "application/pdf", title="Zeugnis alt")
    report_new = add(client, admin_headers, "z2.pdf", pdf_bytes(1), "application/pdf", title="Zeugnis neu")
    cv = add(client, admin_headers, "cv.png", image_bytes(), "image/png", category="cv", title="Lebenslauf")
    letter = add(client, admin_headers, "m.pdf", pdf_bytes(1), "application/pdf", category="letter", title="Brief")
    info = preview(client, admin_headers)
    assert [p["id"] for p in info["parts"]] == [letter["id"], cv["id"], report_new["id"], report_old["id"]]
    assert [p["pages"] for p in info["parts"]] == [1, 1, 1, 2]
    assert info["pages"] == 5
    response = client.get("/api/documents/dossier.pdf", headers=admin_headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "Bewerbungsdossier_" in response.headers["content-disposition"]
    assert info["size"] == len(response.content)
    reader = PdfReader(io.BytesIO(response.content))
    assert len(reader.pages) == 5
    image_page = reader.pages[1]
    assert abs(float(image_page.mediabox.width) - 595.3) < 1 and abs(float(image_page.mediabox.height) - 841.9) < 1


def test_dossier_leaves_out_unticked_and_outdated(client, admin_headers):
    keep = add(client, admin_headers, "a.pdf", pdf_bytes(), "application/pdf")
    unticked = add(client, admin_headers, "b.pdf", pdf_bytes(), "application/pdf")
    old = add(client, admin_headers, "c.pdf", pdf_bytes(), "application/pdf")
    client.patch(f"/api/documents/{unticked['id']}", json={"in_dossier": False}, headers=admin_headers)
    client.patch(f"/api/documents/{old['id']}", json={"outdated": True}, headers=admin_headers)
    assert [p["id"] for p in preview(client, admin_headers)["parts"]] == [keep["id"]]


def test_dossier_skips_what_it_cannot_use(client, admin_headers, db):
    add(client, admin_headers, "ok.pdf", pdf_bytes(), "application/pdf", title="OK")
    word = add(client, admin_headers, "cv.docx", b"PK\x03\x04 word", "application/octet-stream", title="Word")
    locked = add(client, admin_headers, "l.pdf", pdf_bytes(user_password="geheim"), "application/pdf", title="Gesperrt")
    broken = add(client, admin_headers, "x.pdf", b"%PDF-1.4 kaputt", "application/pdf", title="Kaputt")
    gone = add(client, admin_headers, "g.pdf", pdf_bytes(), "application/pdf", title="Weg")
    (config.files_dir() / db.get(models.Document, gone["id"]).path).unlink()
    info = preview(client, admin_headers)
    assert [p["title"] for p in info["parts"]] == ["OK"]
    reasons = {s["id"]: s["reason"] for s in info["skipped"]}
    assert "PDF" in reasons[word["id"]]
    assert reasons[locked["id"]] == "passwortgeschützt"
    assert reasons[broken["id"]] == "PDF nicht lesbar"
    assert reasons[gone["id"]] == "Datei fehlt"


def test_pdf_protected_only_against_editing_goes_in(client, admin_headers):
    add(client, admin_headers, "o.pdf", pdf_bytes(2, owner_password="owner"), "application/pdf")
    info = preview(client, admin_headers)
    assert (info["pages"], info["skipped"]) == (2, [])


def test_empty_dossier(client, admin_headers):
    assert preview(client, admin_headers) == {"parts": [], "skipped": [], "pages": 0, "size": 0}
    assert client.get("/api/documents/dossier.pdf", headers=admin_headers).status_code == 404


def test_dossier_needs_login(client):
    assert client.get("/api/documents/dossier.pdf").status_code == 401
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_dossier.py -q`
Expected: FAIL (`AttributeError: module 'app.dossier' has no attribute 'image_page'`, 404/422 for the dossier routes)

- [ ] **Step 3: Implement the builder**

Replace `backend/app/dossier.py` with:

```python
"""The application dossier: the son's documents as one PDF, in the usual order."""

import io
import logging
import os
from dataclasses import dataclass, field

import pillow_heif
from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

from . import files as filestore
from . import models

logger = logging.getLogger(__name__)
pillow_heif.register_heif_opener()  # HEIC photos from iPhones

PDF_TYPES = {"application/pdf"}
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}

A4_PX = (1240, 1754)  # A4 at 150 dpi: sharp enough to read, small enough to send by e-mail
DPI = 150
JPEG_QUALITY = 80


def kind(content_type: str, filename: str) -> str | None:
    """"pdf", "image", or None if it can't go into the dossier; by type, else by extension (phones send HEIC as
    application/octet-stream)."""
    content_type = (content_type or "").split(";")[0].strip().lower()
    ext = os.path.splitext(filename or "")[1].lower()
    if content_type in PDF_TYPES or ext in PDF_EXTENSIONS:
        return "pdf"
    if content_type in IMAGE_TYPES or ext in IMAGE_EXTENSIONS:
        return "image"
    return None


def image_page(data: bytes) -> Image.Image:
    """A white A4 page with the image upright, fitted (never enlarged) and centred."""
    with Image.open(io.BytesIO(data)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    image.thumbnail(A4_PX)
    page = Image.new("RGB", A4_PX, "white")
    page.paste(image, ((A4_PX[0] - image.width) // 2, (A4_PX[1] - image.height) // 2))
    return page


def _image_pdf(data: bytes) -> PdfReader:
    buffer = io.BytesIO()
    image_page(data).save(buffer, "PDF", resolution=DPI, quality=JPEG_QUALITY)
    return PdfReader(io.BytesIO(buffer.getvalue()))


def _pdf(data: bytes) -> PdfReader:
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted and not reader.decrypt(""):
        raise PermissionError
    len(reader.pages)  # reading the page tree finds most broken files here
    return reader


@dataclass
class Dossier:
    pdf: bytes | None
    parts: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    pages: int = 0


def build(documents: list[models.Document]) -> Dossier:
    """One PDF from the documents marked for the dossier, in the given order; the others are reported."""
    writer = PdfWriter()
    result = Dossier(pdf=None)
    for d in documents:
        if not d.in_dossier:
            continue
        what = kind(d.content_type, d.filename)
        skip = None
        if what is None:
            skip = "kein PDF oder Bild – bitte als PDF hochladen"
        elif not filestore.absolute(d.path).exists():
            skip = "Datei fehlt"
        if skip is None:
            data = filestore.absolute(d.path).read_bytes()
            try:
                reader = _pdf(data) if what == "pdf" else _image_pdf(data)
                pages = len(reader.pages)
                writer.append(reader)
            except PermissionError:
                skip = "passwortgeschützt"
            except (PdfReadError, ValueError, OSError, KeyError, TypeError) as exc:
                logger.info("Dossier: %s unreadable: %s", d.filename, exc)
                skip = "PDF nicht lesbar" if what == "pdf" else "Bild nicht lesbar"
        if skip is not None:
            result.skipped.append({"id": d.id, "title": d.title, "reason": skip})
            continue
        result.parts.append({"id": d.id, "title": d.title, "category": d.category, "pages": pages})
        result.pages += pages
    if result.parts:
        buffer = io.BytesIO()
        writer.write(buffer)
        result.pdf = buffer.getvalue()
    return result
```

Notes:
- `writer.append` copies the pages; a reader that fails while appending is caught by the same `except` and the document is skipped. If a failure leaves partial pages in `writer`, it shows up as a page-count mismatch in `test_dossier_skips_what_it_cannot_use`; if it does, build each part into a temporary `PdfWriter` first and append that only on success.
- An `UnidentifiedImageError` from Pillow is an `OSError`.

- [ ] **Step 4: Add the endpoints**

In `backend/app/documents_api.py`, add to the imports `from fastapi.responses import FileResponse, Response` (replace the existing `FileResponse` import), `from . import dossier`, and add **above** `@router.patch("/documents/{document_id}")` (fixed paths before `{document_id}` routes):

```python
@router.get("/documents/dossier")
def dossier_preview(db: Session = Depends(get_db)):
    result = dossier.build(ordered(db))
    return {
        "parts": result.parts,
        "skipped": result.skipped,
        "pages": result.pages,
        "size": len(result.pdf) if result.pdf else 0,
    }


@router.get("/documents/dossier.pdf")
def dossier_pdf(db: Session = Depends(get_db)):
    result = dossier.build(ordered(db))
    if result.pdf is None:
        raise HTTPException(404, "Keine Unterlage kann ins Dossier")
    filename = f"Bewerbungsdossier_{local_date(utcnow()).isoformat()}.pdf"
    return Response(
        result.pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
```

Note: `/documents/dossier` and `/documents/dossier.pdf` are GET routes; the only other GET with a parameter is `/documents/{document_id}/file`, so they don't collide. They are placed above the `{document_id}` routes for readability.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_dossier.py -q`
Expected: PASS

- [ ] **Step 6: Run the whole suite and commit**

Run: `venv/bin/pytest -q` → all pass.

```bash
git add backend/app/dossier.py backend/app/documents_api.py tests/test_dossier.py
git commit -m "feat(documents): dossier PDF from the documents in the usual order"
```

---

### Task 4: Export

**Files:**
- Modify: `backend/app/export.py`
- Test: `tests/test_settings.py`

**Interfaces:**
- Consumes: Task 1 `models.Document`, `models.CATEGORY_LABELS`; `export._csv`, `_date`, `_datetime`, `_yes_no`
- Produces: `unterlagen.csv`, `documents.csv` in the ZIP

- [ ] **Step 1: Write the failing test**

Append to `tests/test_settings.py`:

```python
def test_export_documents(client, admin_headers):
    client.post(
        "/api/documents",
        data={"category": "report", "title": "Zeugnis Sommer", "issued_on": "2026-07-01"},
        files={"file": ("z.pdf", b"%PDF-1.4 x" * 200, "application/pdf")},
        headers=admin_headers,
    )
    archive = zipfile.ZipFile(io.BytesIO(client.get("/api/export", headers=admin_headers).content))
    header, *rows = read_csv(archive, "unterlagen.csv")
    row = dict(zip(header, rows[0]))
    assert (row["Kategorie"], row["Titel"], row["Datum"]) == ("Zeugnis", "Zeugnis Sommer", "01.07.2026")
    assert (row["Datei"], row["Grösse (KB)"], row["Im Dossier"], row["Veraltet"]) == ("z.pdf", "2", "Ja", "Nein")
    assert row["Hochgeladen von"] == "Admin"
    assert row["Pfad"] == "files/_unterlagen/zeugnis/2026-07-01_zeugnis_Zeugnis-Sommer.pdf"
    assert row["Pfad"] in archive.namelist()
    raw_header, *_ = read_csv(archive, "documents.csv")
    assert "in_dossier" in raw_header
```

- [ ] **Step 2: Run it to verify it fails**

Run: `venv/bin/pytest tests/test_settings.py -q -k documents`
Expected: FAIL with `KeyError: "There is no item named 'unterlagen.csv' in the archive"`

- [ ] **Step 3: Implement**

In `backend/app/export.py`:

1. Add `("documents", models.Document),` as the last entry of `TABLES`.
2. Add after `_suggestions`:

```python
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
```

3. In `build_zip`, after `archive.writestr("vorschlaege.csv", _suggestions(db))` add:

```python
        archive.writestr("unterlagen.csv", _documents(db))
```

`round(2000 / 1024)` is 2, matching the test (`b"%PDF-1.4 x" * 200` is 2000 bytes).

- [ ] **Step 4: Run the tests and commit**

Run: `venv/bin/pytest tests/test_settings.py -q` → PASS; `venv/bin/pytest -q` → all pass.

```bash
git add backend/app/export.py tests/test_settings.py
git commit -m "feat(export): documents as readable unterlagen.csv and raw table"
```

---

### Task 5: Frontend page "Unterlagen"

**Files:**
- Modify: `frontend/src/types.ts`, `frontend/src/api.ts`, `frontend/src/labels.ts`, `frontend/src/components/Layout.tsx`, `frontend/src/App.tsx`
- Create: `frontend/src/pages/Documents.tsx`, `frontend/src/components/DocumentRow.tsx`

**Interfaces:**
- Consumes: Task 2 and 3 endpoints
- Produces: route `/unterlagen`; `openFile(url)` in `api.ts`; `CATEGORY_LABELS`, `CATEGORY_ORDER` in `labels.ts`

- [ ] **Step 1: Types, labels and `openFile`**

Append to `frontend/src/types.ts`:

```ts
export type DocumentCategory = 'letter' | 'cv' | 'report' | 'certificate' | 'other';

export interface AppDocument {
    id: number;
    category: DocumentCategory;
    title: string;
    issued_on: string | null;
    note: string;
    outdated: boolean;
    in_dossier: boolean;
    position: number;
    filename: string;
    content_type: string;
    size: number;
    created_at: string;
    created_by_name: string | null;
    dossier_ok: boolean;
}

export interface DossierPreview {
    parts: { id: number; title: string; category: DocumentCategory; pages: number }[];
    skipped: { id: number; title: string; reason: string }[];
    pages: number;
    size: number;
}
```

Append to `frontend/src/labels.ts` (add `DocumentCategory` to its type import):

```ts
// Dossier order
export const CATEGORY_ORDER: DocumentCategory[] = ['letter', 'cv', 'report', 'certificate', 'other'];

export const CATEGORY_LABELS: Record<DocumentCategory, string> = {
    letter: 'Motivationsschreiben',
    cv: 'Lebenslauf',
    report: 'Zeugnis',
    certificate: 'Zertifikat/Test',
    other: 'Andere',
};
```

Append to `frontend/src/api.ts` before `export default api;`:

```ts
// Open a file that needs the login token in a new tab; the tab is opened first, so popup blockers allow it
export async function openFile(url: string): Promise<void> {
    const tab = window.open('', '_blank');
    try {
        const response = await api.get<Blob>(url, { responseType: 'blob' });
        const href = URL.createObjectURL(response.data);
        if (tab) tab.location.href = href;
        else window.location.href = href;
        setTimeout(() => URL.revokeObjectURL(href), 60_000);
    } catch (error) {
        tab?.close();
        throw error;
    }
}
```

- [ ] **Step 2: Navigation and route**

In `frontend/src/components/Layout.tsx`, add after the Posteingang `NavLink`:

```tsx
                        <NavLink to="/unterlagen" className={linkClass}>
                            Unterlagen
                        </NavLink>
```

In `frontend/src/App.tsx`: `import Documents from './pages/Documents';` and `<Route path="unterlagen" element={<Documents />} />` after the `posteingang` route.

- [ ] **Step 3: The row**

Create `frontend/src/components/DocumentRow.tsx`:

```tsx
import { useState } from 'react';
import api, { downloadFile, errorMessage, openFile } from '../api';
import { CATEGORY_LABELS, CATEGORY_ORDER, formatDate, formatSize } from '../labels';
import { useToast } from '../ToastContext';
import type { AppDocument, DocumentCategory } from '../types';
import { BUTTON, BUTTON_DANGER, BUTTON_SECONDARY, INPUT } from '../ui';

const SMALL = 'rounded border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800 disabled:opacity-40';

interface Props {
    doc: AppDocument;
    first: boolean;
    last: boolean;
    onChanged: () => void;
}

export default function DocumentRow({ doc, first, last, onChanged }: Props) {
    const toast = useToast();
    const [busy, setBusy] = useState(false);
    const [editing, setEditing] = useState(false);
    const [title, setTitle] = useState(doc.title);
    const [category, setCategory] = useState<DocumentCategory>(doc.category);
    const [issuedOn, setIssuedOn] = useState(doc.issued_on ?? '');
    const [note, setNote] = useState(doc.note);

    const run = async (action: () => Promise<unknown>) => {
        setBusy(true);
        try {
            await action();
            onChanged();
        } catch (e) {
            toast(errorMessage(e));
        } finally {
            setBusy(false);
        }
    };

    const patch = (body: Partial<Omit<AppDocument, 'issued_on'>> & { issued_on?: string | null }) =>
        run(() => api.patch(`/api/documents/${doc.id}`, body));
    const move = (direction: 'up' | 'down') => run(() => api.post(`/api/documents/${doc.id}/move`, { direction }));
    const remove = () => {
        if (!window.confirm(`„${doc.title}“ löschen?`)) return;
        run(() => api.delete(`/api/documents/${doc.id}`));
    };
    const save = () =>
        run(async () => {
            await api.patch(`/api/documents/${doc.id}`, { title, category, issued_on: issuedOn || null, note });
            setEditing(false);
        });

    if (editing) {
        return (
            <li className="space-y-2 rounded-lg border border-slate-700 p-3">
                <div className="grid gap-2 sm:grid-cols-3">
                    <input value={title} onChange={(e) => setTitle(e.target.value)} className={INPUT} />
                    <select
                        value={category}
                        onChange={(e) => setCategory(e.target.value as DocumentCategory)}
                        className={INPUT}
                    >
                        {CATEGORY_ORDER.map((c) => (
                            <option key={c} value={c}>
                                {CATEGORY_LABELS[c]}
                            </option>
                        ))}
                    </select>
                    <input type="date" value={issuedOn} onChange={(e) => setIssuedOn(e.target.value)} className={INPUT} />
                </div>
                <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} className={INPUT} />
                <div className="flex gap-2">
                    <button type="button" className={BUTTON} disabled={busy} onClick={save}>
                        Speichern
                    </button>
                    <button type="button" className={BUTTON_SECONDARY} onClick={() => setEditing(false)}>
                        Abbrechen
                    </button>
                </div>
            </li>
        );
    }

    return (
        <li className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-slate-800 p-3">
            <label className="flex items-center gap-2 text-sm" title="Im Dossier">
                <input
                    type="checkbox"
                    checked={doc.in_dossier}
                    disabled={busy || !doc.dossier_ok}
                    onChange={(e) => patch({ in_dossier: e.target.checked })}
                />
            </label>
            <div className="min-w-0 flex-1">
                <div className={`truncate font-semibold ${doc.outdated ? 'text-slate-500' : ''}`}>{doc.title}</div>
                <div className="text-xs text-slate-500">
                    {doc.issued_on ? formatDate(doc.issued_on) : 'ohne Datum'} · {formatSize(doc.size)} ·{' '}
                    {doc.created_by_name ?? 'unbekannt'}
                    {!doc.dossier_ok && ' · nicht im Dossier möglich (bitte als PDF hochladen)'}
                </div>
                {doc.note && <div className="whitespace-pre-wrap text-xs text-slate-400">{doc.note}</div>}
            </div>
            <div className="flex flex-wrap gap-1">
                <button type="button" className={SMALL} disabled={busy || first} onClick={() => move('up')} title="Nach oben">
                    ↑
                </button>
                <button type="button" className={SMALL} disabled={busy || last} onClick={() => move('down')} title="Nach unten">
                    ↓
                </button>
                <button
                    type="button"
                    className={SMALL}
                    onClick={() => openFile(`/api/documents/${doc.id}/file`).catch((e) => toast(errorMessage(e)))}
                >
                    Öffnen
                </button>
                <button
                    type="button"
                    className={SMALL}
                    onClick={() =>
                        downloadFile(`/api/documents/${doc.id}/file`, doc.filename).catch((e) => toast(errorMessage(e)))
                    }
                >
                    Herunterladen
                </button>
                <button type="button" className={SMALL} onClick={() => setEditing(true)}>
                    Bearbeiten
                </button>
                <button type="button" className={SMALL} disabled={busy} onClick={() => patch({ outdated: !doc.outdated })}>
                    {doc.outdated ? 'Aktuell' : 'Veraltet'}
                </button>
                <button type="button" className={`${BUTTON_DANGER} px-2 py-1 text-xs`} disabled={busy} onClick={remove}>
                    Löschen
                </button>
            </div>
        </li>
    );
}
```

- [ ] **Step 4: The page**

Create `frontend/src/pages/Documents.tsx`:

```tsx
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import api, { downloadFile, errorMessage } from '../api';
import DocumentRow from '../components/DocumentRow';
import { CATEGORY_LABELS, CATEGORY_ORDER, formatSize } from '../labels';
import { useToast } from '../ToastContext';
import type { AppDocument, DocumentCategory, DossierPreview } from '../types';
import { BUTTON, CARD, INPUT } from '../ui';

function stem(filename: string): string {
    const dot = filename.lastIndexOf('.');
    return dot > 0 ? filename.slice(0, dot) : filename;
}

export default function Documents() {
    const toast = useToast();
    const [docs, setDocs] = useState<AppDocument[] | null>(null);
    const [preview, setPreview] = useState<DossierPreview | null>(null);
    const [file, setFile] = useState<File | null>(null);
    const [category, setCategory] = useState<DocumentCategory>('report');
    const [title, setTitle] = useState('');
    const [issuedOn, setIssuedOn] = useState('');
    const [note, setNote] = useState('');
    const [uploading, setUploading] = useState(false);
    const [building, setBuilding] = useState(false);
    const [openOutdated, setOpenOutdated] = useState<Record<string, boolean>>({});
    const fileInput = useRef<HTMLInputElement>(null);

    const [version, setVersion] = useState(0);
    const load = useCallback(() => setVersion((v) => v + 1), []);

    useEffect(() => {
        Promise.all([api.get<AppDocument[]>('/api/documents'), api.get<DossierPreview>('/api/documents/dossier')])
            .then(([list, dossier]) => {
                setDocs(list.data);
                setPreview(dossier.data);
            })
            .catch((e) => toast(errorMessage(e)));
    }, [version, toast]);

    const submit = async (event: FormEvent) => {
        event.preventDefault();
        if (!file) return;
        setUploading(true);
        const form = new FormData();
        form.append('file', file);
        form.append('category', category);
        form.append('title', title);
        form.append('issued_on', issuedOn);
        form.append('note', note);
        try {
            await api.post('/api/documents', form);
            toast('Unterlage hochgeladen', 'success');
            setFile(null);
            setTitle('');
            setIssuedOn('');
            setNote('');
            if (fileInput.current) fileInput.current.value = '';
            load();
        } catch (e) {
            toast(errorMessage(e));
        } finally {
            setUploading(false);
        }
    };

    const download = async () => {
        setBuilding(true);
        try {
            const today = new Date().toISOString().slice(0, 10);
            await downloadFile('/api/documents/dossier.pdf', `Bewerbungsdossier_${today}.pdf`);
        } catch (e) {
            toast(errorMessage(e, 'Dossier konnte nicht erstellt werden'));
        } finally {
            setBuilding(false);
        }
    };

    if (docs === null) return <p className="text-slate-400">Laden…</p>;

    return (
        <div className="space-y-4">
            <h1 className="text-2xl font-bold">Unterlagen</h1>

            <form onSubmit={submit} className={`${CARD} space-y-3`}>
                <h2 className="font-semibold">Unterlage hochladen</h2>
                <input
                    ref={fileInput}
                    type="file"
                    accept="application/pdf,image/*,.heic,.heif"
                    required
                    onChange={(e) => {
                        const chosen = e.target.files?.[0] ?? null;
                        setFile(chosen);
                        if (chosen && !title) setTitle(stem(chosen.name));
                    }}
                    className="block w-full text-sm text-slate-300"
                />
                <div className="grid gap-3 sm:grid-cols-3">
                    <label className="block text-sm">
                        <span className="mb-1 block text-slate-400">Kategorie</span>
                        <select
                            value={category}
                            onChange={(e) => setCategory(e.target.value as DocumentCategory)}
                            className={INPUT}
                        >
                            {CATEGORY_ORDER.map((c) => (
                                <option key={c} value={c}>
                                    {CATEGORY_LABELS[c]}
                                </option>
                            ))}
                        </select>
                    </label>
                    <label className="block text-sm">
                        <span className="mb-1 block text-slate-400">Titel</span>
                        <input value={title} onChange={(e) => setTitle(e.target.value)} className={INPUT} />
                    </label>
                    <label className="block text-sm">
                        <span className="mb-1 block text-slate-400">Datum</span>
                        <input type="date" value={issuedOn} onChange={(e) => setIssuedOn(e.target.value)} className={INPUT} />
                    </label>
                </div>
                <label className="block text-sm">
                    <span className="mb-1 block text-slate-400">Notiz</span>
                    <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} className={INPUT} />
                </label>
                <button type="submit" className={BUTTON} disabled={uploading || !file}>
                    {uploading ? 'Lädt hoch…' : 'Hochladen'}
                </button>
            </form>

            <section className={`${CARD} space-y-2`}>
                <div className="flex flex-wrap items-center gap-3">
                    <h2 className="mr-auto font-semibold">Bewerbungsdossier</h2>
                    <button type="button" className={BUTTON} disabled={building || !preview?.pages} onClick={download}>
                        {building ? 'Wird erstellt…' : 'Dossier als PDF'}
                    </button>
                </div>
                {preview && preview.pages > 0 ? (
                    <>
                        <ol className="list-decimal pl-5 text-sm text-slate-300">
                            {preview.parts.map((p) => (
                                <li key={p.id}>
                                    {p.title} <span className="text-slate-500">({p.pages} S.)</span>
                                </li>
                            ))}
                        </ol>
                        <p className="text-xs text-slate-500">
                            {preview.pages} Seiten · etwa {formatSize(preview.size)}
                        </p>
                    </>
                ) : (
                    <p className="text-sm text-slate-400">Noch keine Unterlage im Dossier.</p>
                )}
                {preview && preview.skipped.length > 0 && (
                    <ul className="text-xs text-amber-300">
                        {preview.skipped.map((s) => (
                            <li key={s.id}>
                                Nicht im Dossier: {s.title} ({s.reason})
                            </li>
                        ))}
                    </ul>
                )}
            </section>

            {CATEGORY_ORDER.map((c) => {
                const inCategory = docs.filter((d) => d.category === c);
                if (inCategory.length === 0) return null;
                const current = inCategory.filter((d) => !d.outdated);
                const outdated = inCategory.filter((d) => d.outdated);
                return (
                    <section key={c} className="space-y-2">
                        <h2 className="text-lg font-semibold">
                            {CATEGORY_LABELS[c]} <span className="text-sm text-slate-500">({inCategory.length})</span>
                        </h2>
                        <ul className="space-y-2">
                            {current.map((d) => (
                                <DocumentRow
                                    key={d.id}
                                    doc={d}
                                    first={inCategory[0].id === d.id}
                                    last={inCategory[inCategory.length - 1].id === d.id}
                                    onChanged={load}
                                />
                            ))}
                        </ul>
                        {outdated.length > 0 && (
                            <div className="space-y-2">
                                <button
                                    type="button"
                                    className="text-sm text-slate-400 hover:text-white"
                                    onClick={() => setOpenOutdated((o) => ({ ...o, [c]: !o[c] }))}
                                >
                                    {openOutdated[c] ? '▾' : '▸'} Veraltet ({outdated.length})
                                </button>
                                {openOutdated[c] && (
                                    <ul className="space-y-2">
                                        {outdated.map((d) => (
                                            <DocumentRow
                                                key={d.id}
                                                doc={d}
                                                first={inCategory[0].id === d.id}
                                                last={inCategory[inCategory.length - 1].id === d.id}
                                                onChanged={load}
                                            />
                                        ))}
                                    </ul>
                                )}
                            </div>
                        )}
                    </section>
                );
            })}
        </div>
    );
}
```

- [ ] **Step 5: Lint and build**

Run: `cd frontend && npm run lint && npm run build`
Expected: no lint errors; `✓ built`. Fix formatting the way the linter asks.

- [ ] **Step 6: Commit**

```bash
git add frontend/src
git commit -m "feat(frontend): Unterlagen page with upload, categories, order and dossier PDF"
```

---

### Task 6: Documentation and final check

**Files:**
- Modify: `README.md`, `README_DOCKER.md`

- [ ] **Step 1: README.md** — in the feature list, after the "Vorschläge" bullet, add:

```markdown
- **Unterlagen:** school reports, certificates and tests, CV and cover letter in one place, by
  category; one click builds the application dossier as a single PDF in the usual order (photos
  from the phone become A4 pages).
```

- [ ] **Step 2: README_DOCKER.md** — in "Where the data is" (find it with `grep -n "Where the data is" README_DOCKER.md`), add a line in the same style for `data/files/_unterlagen/<category>/` (the documents of the Unterlagen page).

- [ ] **Step 3: Full verification**

Run:
```bash
venv/bin/pytest -q
(cd frontend && npm run lint && npm run build)
(cd cloudflare/email-worker && npm test)
docker build -q backend >/dev/null && echo "backend image builds"
```
Expected: all pass; the backend image builds with the new packages (if Docker is not available locally, note it in the ledger; CI builds the image on merge).

- [ ] **Step 4: Commit**

```bash
git add README.md README_DOCKER.md
git commit -m "docs: Unterlagen page and its folder"
```
