from datetime import timedelta

import pytest

from app import config, inbox_api, models
from app.settings_store import get_settings
from app.timeutil import utcnow
from helpers import create_application, create_user
from mails import BROKEN_MAIL, INBOUND_SECRET, build_mail, post_mail


@pytest.fixture(autouse=True)
def inbound_secret(monkeypatch):
    monkeypatch.setenv("INBOUND_SECRET", INBOUND_SECRET)


def tagged(application):
    return f"bewerbungen+{application['mail_tag']}@example.ch"


def detail(client, headers, application_id):
    return client.get(f"/api/applications/{application_id}", headers=headers).json()


def test_not_configured_is_503(client, monkeypatch):
    monkeypatch.delenv("INBOUND_SECRET")
    assert post_mail(client, build_mail()).status_code == 503


def test_wrong_secret_is_401(client):
    assert post_mail(client, build_mail(), secret="falsch").status_code == 401


def test_tagged_mail_creates_event_and_files(client, admin_headers):
    app = create_application(client, admin_headers, "Migros")
    raw = build_mail(
        to=tagged(app),
        subject="Einladung zum Gespräch",
        attachments=[("Lebenslauf Müller.pdf", b"%PDF", "application/pdf")],
    )
    response = post_mail(client, raw)
    assert response.status_code == 200
    assert response.json()["status"] == "stored"
    assert response.json()["application_id"] == app["id"]

    result = detail(client, admin_headers, app["id"])
    assert result["status"] == "in_contact"
    event = result["events"][0]
    assert event["type"] == "mail_received"
    assert event["note"] == "Einladung zum Gespräch"
    assert event["occurred_at"] == "2026-10-15T07:30:00Z"
    assert event["created_by_name"] is None
    attachment = event["email"]["attachments"][0]
    assert attachment["filename"] == "Lebenslauf Müller.pdf"
    assert attachment["path"] == "migros/2026-10-15_migros_Lebenslauf-Mueller.pdf"
    assert (config.files_dir() / attachment["path"]).read_bytes() == b"%PDF"
    assert [p.name for p in (config.files_dir() / "migros").glob("*.eml")] == [
        "2026-10-15_migros_mail-Einladung-zum-Gespraech.eml"
    ]


def test_bcc_uses_envelope_recipient(client, admin_headers):
    app = create_application(client, admin_headers, "Migros")
    raw = build_mail(sender="sohn@example.ch", to="hr@migros.ch")
    response = post_mail(client, raw, envelope_to=tagged(app))
    assert response.json()["application_id"] == app["id"]


def test_mail_from_a_user_is_mail_sent(client, admin_headers):
    create_user(client, admin_headers, "Sohn", email="sohn@example.ch")
    app = create_application(client, admin_headers, "Migros")
    post_mail(client, build_mail(sender="Sohn <Sohn@Example.ch>", to="hr@migros.ch", cc=tagged(app)))
    assert [e["type"] for e in detail(client, admin_headers, app["id"])["events"]] == ["mail_sent"]


def test_untagged_mail_goes_to_inbox(client, admin_headers, db):
    raw = build_mail(to="bewerbungen@example.ch", attachments=[("Zeugnis.pdf", b"x", "application/pdf")])
    assert post_mail(client, raw).json()["application_id"] is None
    email = db.query(models.Email).one()
    assert email.application_id is None
    assert email.attachments[0].path == "_posteingang/2026-10-15_migros-ch_Zeugnis.pdf"
    assert client.get("/api/dashboard", headers=admin_headers).json()["inbox_count"] == 1


def test_duplicate_message_id_is_ignored(client, db):
    raw = build_mail()
    assert post_mail(client, raw).json()["status"] == "stored"
    assert post_mail(client, raw).json()["status"] == "duplicate"
    assert db.query(models.Email).count() == 1


def test_broken_mail_is_kept_and_reported(client, db):
    response = post_mail(client, BROKEN_MAIL)
    assert response.status_code == 200
    email = db.query(models.Email).one()
    assert email.parse_error
    assert email.subject == "(konnte nicht gelesen werden)"
    assert (config.files_dir() / email.raw_path).read_bytes() == BROKEN_MAIL
    settings = get_settings(db)
    assert settings.last_inbound_error
    assert settings.last_inbound_at is not None

    post_mail(client, build_mail())
    db.expire_all()
    assert get_settings(db).last_inbound_error is None


def test_mail_without_date_uses_arrival_time(client, db):
    before = utcnow() - timedelta(seconds=1)
    post_mail(client, build_mail(date=None))
    email = db.query(models.Email).one()
    assert before <= email.received_at <= utcnow()


def test_oversize_mail_is_413(client, monkeypatch):
    monkeypatch.setattr(inbox_api, "MAX_INBOUND_BYTES", 10)
    assert post_mail(client, build_mail()).status_code == 413
