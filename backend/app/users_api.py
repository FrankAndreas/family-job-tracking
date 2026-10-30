"""Who is logged in, and the app's people. They come from the family hub (spec 2026-10-30): login, name and admin (a
parent there) are managed there; the app keeps each person's e-mail and reminders, and deletes the data of people the
hub removed."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import auth, hub, hub_people, models, schemas
from .database import get_db

router = APIRouter(tags=["users"])


def _get_user(db: Session, user_id: int) -> models.User:
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(404, "Benutzer nicht gefunden")
    return user


def _ask_the_hub(request: Request, db: Session) -> None:
    """The people lists show the hub's current state, not the one of up to a minute ago."""
    token, _ = auth.request_token(request)
    if token:
        try:
            hub_people.refresh(db, token, force=True)
        except hub.HubUnavailable:
            raise HTTPException(503, "hub_unavailable") from None


def _keep_hub_email(user: models.User, data: dict) -> None:
    """An address from the family hub is changed there: here it would be overwritten at the next sync."""
    if user.email_from_hub and "email" in data and data["email"] != user.email:
        raise HTTPException(400, "from_hub")


@router.get("/hub")
def hub_link(request: Request):
    """Where browsers log in (the family hub's address at home) and out: at home the hub's logout page, which ends the
    login for every app; from outside Cloudflare Access's logout."""
    outside = auth.TUNNEL_HEADER in request.headers
    logout = "/cdn-cgi/access/logout" if outside else f"{hub.public_url()}/logout"
    return {"login_url": hub.public_url(), "logout_url": logout}


@router.get("/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(auth.get_current_user)):
    return user


@router.patch("/me", response_model=schemas.UserOut)
def update_me(
    body: schemas.MePatch, user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)
):
    data = body.model_dump(exclude_unset=True)
    _keep_hub_email(user, data)
    for key, value in data.items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user


@router.get("/users", response_model=list[schemas.UserOut])
def list_users(request: Request, _admin: models.User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    """The people the hub lists for the app."""
    _ask_the_hub(request, db)
    return db.query(models.User).filter(models.User.is_active.is_(True)).order_by(models.User.name).all()


@router.get("/users/removed", response_model=list[schemas.UserOut])
def removed_users(request: Request, _admin: models.User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    """People the hub no longer lists: hidden until an admin deletes them."""
    _ask_the_hub(request, db)
    return db.query(models.User).filter(models.User.is_active.is_(False)).order_by(models.User.name).all()


@router.patch("/users/{user_id}", response_model=schemas.UserOut)
def update_user(
    user_id: int,
    body: schemas.UserPatch,
    _admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    """An admin sets a person's e-mail and reminders; the name and admin come from the family hub."""
    user = _get_user(db, user_id)
    data = body.model_dump(exclude_unset=True)
    if ("name" in data and data["name"] != user.name) or ("is_admin" in data and data["is_admin"] != user.is_admin):
        raise HTTPException(400, "from_hub")
    _keep_hub_email(user, data)
    for key in ("email", "wants_reminders"):
        if key in data and not (key == "wants_reminders" and data[key] is None):
            setattr(user, key, data[key])
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, _admin: models.User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    user = _get_user(db, user_id)
    # Only people the hub no longer lists: an active family member's data is never deleted by mistake
    if user.is_active:
        raise HTTPException(409, "still_in_hub")
    # Their applications and events stay; "created_by" becomes empty (ON DELETE SET NULL)
    db.delete(user)
    db.commit()
