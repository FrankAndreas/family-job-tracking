import os
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import auth, dossier, models, schemas, views
from . import files as filestore
from .database import get_db
from .timeutil import local_date, utcnow

router = APIRouter(tags=["documents"], dependencies=[Depends(auth.get_current_user)])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# What can be uploaded, by extension; the type is ours, never the browser's, so an HTML file can't be
# served as a page that runs scripts in the app
ALLOWED_TYPES = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".rtf": "application/rtf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".heif": "image/heif",
}


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
    filename = file.filename or "dokument"
    content_type = ALLOWED_TYPES.get(os.path.splitext(filename)[1].lower())
    if content_type is None:
        raise HTTPException(422, "Erlaubt sind PDF, Word-Dateien (doc, docx, odt, rtf) und Fotos (jpg, png, heic)")
    content = await file.read()
    if not content:
        raise HTTPException(422, "Die Datei ist leer")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"{file.filename} ist grösser als 25 MB")
    title = title.strip()[:200] or (filename.rsplit(".", 1)[0] if "." in filename else filename)
    path = filestore.store_document(category, issued or local_date(utcnow()), title, filename, content)
    d = models.Document(
        category=category,
        title=title,
        issued_on=issued,
        note=note,
        # Word files can't go into the dossier: start them unticked
        in_dossier=dossier.kind(content_type, filename) is not None,
        position=_first_position(db, category),
        filename=filename,
        path=path,
        content_type=content_type,
        size=len(content),
        created_by=user.id,
    )
    db.add(d)
    try:
        db.commit()
    except Exception:
        db.rollback()
        filestore.delete(path)  # not saved: don't leave the file behind
        raise
    db.refresh(d)
    return views.document_out(d)


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


@router.patch("/documents/{document_id}")
def update_document(document_id: int, body: schemas.DocumentPatch, db: Session = Depends(get_db)):
    d = _get(db, document_id)
    changes = body.model_dump(exclude_unset=True)
    category = changes.pop("category", None)
    old_path = d.path
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
    new_path = d.path
    try:
        db.commit()
    except Exception:
        db.rollback()
        if new_path != old_path:
            filestore.rename(new_path, old_path)  # not saved: put the file back where the database has it
        raise
    db.refresh(d)
    return views.document_out(d)


@router.post("/documents/{document_id}/move")
def move_document(document_id: int, body: schemas.DocumentMoveIn, db: Session = Depends(get_db)):
    """Swap with the neighbour in the same category; at the top or bottom nothing changes."""
    d = _get(db, document_id)
    # Current and outdated documents are listed apart: move only among those shown together
    siblings = [x for x in ordered(db) if x.category == d.category and x.outdated == d.outdated]
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
    # Only PDFs and photos open in the browser; anything else is a download
    disposition = "inline" if dossier.kind(d.content_type, d.filename) else "attachment"
    return FileResponse(path, media_type=d.content_type, filename=d.filename, content_disposition_type=disposition)
