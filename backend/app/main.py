import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import (
    hub,
    upgrade,
    applications_api,
    config,
    database,
    documents_api,
    inbox_api,
    models,
    reminders,
    settings_api,
    suggestions_api,
    users_api,
)
from .settings_store import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

models.Base.metadata.create_all(bind=database.engine)
# Columns added since (the people from the family hub, 2026-10-30)
upgrade.upgrade(database.engine)

# A fresh database gets the settings row; the people come from the family hub
with database.SessionLocal() as _db:
    get_settings(_db)
logger.info("Family hub: %s (logins at %s, app key %s)", hub.hub_url(), hub.public_url(), hub.app_key())

# Both integrations are optional; say which ones are on, but never refuse to start
logger.info(
    "Inbound e-mail: %s", "configured" if config.env("INBOUND_SECRET") else "not configured (INBOUND_SECRET empty)"
)
logger.info(
    "Reminder e-mails: %s",
    "configured" if reminders.is_configured() else "not configured (RESEND_API_KEY or MAIL_FROM empty)",
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(reminders.loop()) if reminders.is_configured() else None
    yield
    if task is not None:
        task.cancel()


app = FastAPI(title="Family Job Tracking API", version="0.1.0", lifespan=lifespan)
app.include_router(users_api.router, prefix="/api")
app.include_router(applications_api.router, prefix="/api")
app.include_router(inbox_api.router, prefix="/api")
app.include_router(settings_api.router, prefix="/api")
app.include_router(suggestions_api.router, prefix="/api")
app.include_router(documents_api.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}
