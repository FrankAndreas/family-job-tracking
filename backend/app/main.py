import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import applications_api, config, database, inbox_api, models, reminders, settings_api, users_api
from .seed import seed_admin
from .settings_store import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

models.Base.metadata.create_all(bind=database.engine)

# A fresh database gets the settings row and a first admin to log in with
with database.SessionLocal() as _db:
    get_settings(_db)
    _initial_pin = seed_admin(_db)
if _initial_pin:
    logger.warning("Created user 'Admin' with INITIAL PIN %s. Log in and change it in Einstellungen.", _initial_pin)

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


@app.get("/health")
def health():
    return {"status": "ok"}
