from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from . import auth, models, pagetitle, schemas, suggestions, views
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


@router.post("/suggestions/check")
def check_link(body: schemas.SuggestionCheckIn, db: Session = Depends(get_db)):
    """Earlier suggestions and applications with this link, and the page's title as a suggested position."""
    return {"duplicates": suggestions.find_duplicates(db, body.url), "title": pagetitle.fetch_title(body.url)}


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
