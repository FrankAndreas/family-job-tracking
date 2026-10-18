from datetime import datetime

from sqlalchemy.orm import Session

from . import config, models, reminders
from .settings_store import get_settings
from .timeutil import iso


def _inbound(db: Session, settings: models.Settings) -> dict:
    if not config.env("INBOUND_SECRET"):
        state = "not_configured"
    elif settings.last_inbound_error:
        state = "error"
    elif settings.last_inbound_at:
        state = "ok"
    else:
        state = "waiting"
    warnings = []
    if not settings.inbound_address:
        warnings.append("Die Eingangsadresse ist in den Einstellungen nicht gesetzt.")
    users_without = db.query(models.User.name).filter(models.User.email.is_(None)).order_by(models.User.name)
    without = [name for (name,) in users_without]
    if without:
        warnings.append(
            f"Ohne E-Mail-Adresse: {', '.join(without)}. Ihre Mails an die App zählen als erhalten statt gesendet "
            "(unter Einstellungen → Mein Konto speichern)."
        )
    return {
        "state": state,
        "details": {
            "address": settings.inbound_address or None,
            "last_received_at": iso(settings.last_inbound_at),
            "last_error": settings.last_inbound_error,
        },
        "warnings": warnings,
    }


def _reminders(db: Session, settings: models.Settings, now: datetime) -> dict:
    configured = reminders.is_configured()
    if not configured:
        state = "not_configured"
    elif settings.last_reminder_error:
        state = "error"
    else:
        state = "ok"
    to = reminders.recipients(db)
    warnings = []
    if configured and not config.env("APP_URL"):
        warnings.append("APP_URL fehlt: die Erinnerungen enthalten keine Links.")
    if configured and not to:
        warnings.append("Niemand hat Erinnerungen eingeschaltet.")
    return {
        "state": state,
        "details": {
            "mail_from": config.env("MAIL_FROM") or None,
            "recipients": to,
            "next_run": iso(reminders.next_run(settings, now)) if configured else None,
            "last_attempt_at": iso(settings.last_reminder_attempt_at),
            "last_sent_at": iso(settings.last_reminder_sent_at),
            "last_error": settings.last_reminder_error,
        },
        "warnings": warnings,
    }


def status(db: Session, now: datetime) -> dict:
    settings = get_settings(db)
    return {"inbound": _inbound(db, settings), "reminders": _reminders(db, settings, now)}
