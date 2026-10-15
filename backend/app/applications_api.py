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
