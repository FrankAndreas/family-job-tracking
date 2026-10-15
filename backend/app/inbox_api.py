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
