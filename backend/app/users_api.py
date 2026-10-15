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
