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
