from datetime import datetime

from app import models
from app.settings_store import get_settings
from app.timeutil import iso, to_utc


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_settings_row_is_created_once(db):
    first = get_settings(db)
    second = get_settings(db)
    assert first.id == second.id == 1
    assert first.followup_days == 10
    assert first.reminder_time == "07:00"
    assert db.query(models.Settings).count() == 1


def test_naive_input_is_local_time():
    # 10:00 in Zurich (summer time, UTC+2) is 08:00 UTC
    assert iso(to_utc(datetime(2026, 7, 1, 10, 0))) == "2026-07-01T08:00:00Z"


def test_deleting_a_user_nulls_created_by(db):
    user = models.User(name="Sohn")
    db.add(user)
    db.flush()
    application = models.Application(company="Migros", mail_tag="abcd", created_by=user.id)
    db.add(application)
    db.commit()
    db.delete(user)
    db.commit()
    db.refresh(application)
    assert application.created_by is None
