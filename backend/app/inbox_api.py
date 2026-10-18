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
    if isinstance(email, list):
        return {"status": "suggestions", "suggestion_ids": [s.id for s in email]}
    return {"status": "stored", "email_id": email.id, "application_id": email.application_id}


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
