import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from . import auth, export, integrations, models, reminders, schemas
from .database import get_db
from .settings_store import get_settings
from .timeutil import local_date, utcnow

router = APIRouter(tags=["settings"], dependencies=[Depends(auth.get_current_user)])


def _settings_out(settings: models.Settings) -> dict:
    return {
        "followup_days": settings.followup_days,
        "reminder_time": settings.reminder_time,
        "inbound_address": settings.inbound_address,
    }


@router.get("/settings")
def read_settings(db: Session = Depends(get_db)):
    return _settings_out(get_settings(db))


@router.patch("/settings")
def update_settings(
    body: schemas.SettingsPatch, _admin: models.User = Depends(auth.require_admin), db: Session = Depends(get_db)
):
    settings = get_settings(db)
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(settings, key, value)
    db.commit()
    return _settings_out(settings)


@router.get("/integrations")
def read_integrations(db: Session = Depends(get_db)):
    return integrations.status(db, utcnow())


@router.post("/integrations/reminders/test", status_code=204)
def send_test_reminder(user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    try:
        reminders.send_test(db, user, utcnow())
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"Versand fehlgeschlagen: {exc}")


@router.get("/export")
def export_data(db: Session = Depends(get_db)):
    path = export.build_zip(db)
    filename = f"bewerbungen-export-{local_date(utcnow()).isoformat()}.zip"
    return FileResponse(
        path, media_type="application/zip", filename=filename, background=BackgroundTask(os.unlink, path)
    )
