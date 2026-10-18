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


def events_of(client, headers, application_id):
    """Event types, oldest first."""
    return [e["type"] for e in reversed(detail(client, headers, application_id)["events"])]


def test_first_mail_from_a_user_is_the_application(client, admin_headers):
    # BCC'ing the app on the application mail must count as "Bewerbung gesendet", so the status
    # becomes "Offen" and the follow-up reminder can start
    create_user(client, admin_headers, "Sohn", email="sohn@example.ch")
    app = create_application(client, admin_headers, "Migros")
    post_mail(client, build_mail(sender="Sohn <Sohn@Example.ch>", to="hr@migros.ch", cc=tagged(app)))
    assert events_of(client, admin_headers, app["id"]) == ["sent"]
    assert detail(client, admin_headers, app["id"])["status"] == "open"


def test_later_mails_from_a_user_are_mail_sent(client, admin_headers):
    create_user(client, admin_headers, "Sohn", email="sohn@example.ch")
    app = create_application(client, admin_headers, "Migros")
    first = build_mail(sender="sohn@example.ch", to="hr@migros.ch", cc=tagged(app), message_id="<a@x>",
                       date="Thu, 01 Oct 2026 09:00:00 +0200")
    second = build_mail(sender="sohn@example.ch", to="hr@migros.ch", cc=tagged(app), message_id="<b@x>",
                        date="Thu, 15 Oct 2026 09:00:00 +0200")
    post_mail(client, first)
    post_mail(client, second)
    assert events_of(client, admin_headers, app["id"]) == ["sent", "mail_sent"]


FORWARDED_BODY = """Hier die Antwort.

---------- Forwarded message ---------
Von: Personal Migros <HR@migros.ch>
Date: Mi., 14. Okt. 2026
Subject: Ihre Bewerbung

Gerne laden wir Sie ein ...
"""


def test_reply_forwarded_by_a_user_counts_as_reply_from_the_company(client, admin_headers, db):
    create_user(client, admin_headers, "Sohn", email="sohn@example.ch")
    app = create_application(client, admin_headers, "Migros")
    raw = build_mail(sender="sohn@example.ch", to=tagged(app), subject="WG: Ihre Bewerbung", body=FORWARDED_BODY)
    post_mail(client, raw)
    assert events_of(client, admin_headers, app["id"]) == ["reply_received"]
    assert db.query(models.Email).one().from_addr == "hr@migros.ch"
    assert detail(client, admin_headers, app["id"])["status"] == "in_contact"


def test_forwarded_reply_without_a_readable_sender_is_still_a_reply(client, admin_headers, db):
    create_user(client, admin_headers, "Sohn", email="sohn@example.ch")
    app = create_application(client, admin_headers, "Migros")
    raw = build_mail(sender="sohn@example.ch", to=tagged(app), subject="Fwd: Einladung", body="siehe unten")
    post_mail(client, raw)
    assert events_of(client, admin_headers, app["id"]) == ["reply_received"]
    assert db.query(models.Email).one().from_addr == "sohn@example.ch"


def test_forwarded_own_application_counts_as_sent(client, admin_headers):
    # Forgot the BCC and forwarded the sent application afterwards
    create_user(client, admin_headers, "Sohn", email="sohn@example.ch")
    app = create_application(client, admin_headers, "Migros")
    body = "Von: Sohn <sohn@example.ch>\nAn: hr@migros.ch\nBetreff: Bewerbung\n\nSehr geehrte Damen und Herren"
    post_mail(client, build_mail(sender="sohn@example.ch", to=tagged(app), subject="WG: Bewerbung", body=body))
    assert events_of(client, admin_headers, app["id"]) == ["sent"]


def test_forwarded_untagged_reply_is_assigned_by_the_companys_domain(client, admin_headers):
    create_user(client, admin_headers, "Sohn", email="sohn@example.ch")
    app = create_application(client, admin_headers, "Migros", contact_email="jobs@migros.ch")
    raw = build_mail(sender="sohn@example.ch", to="bewerbungen@example.ch", subject="WG: Ihre Bewerbung",
                     body=FORWARDED_BODY)
    assert post_mail(client, raw).json()["application_id"] == app["id"]
    assert events_of(client, admin_headers, app["id"]) == ["reply_received"]


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


def test_untagged_mail_from_a_known_company_is_assigned(client, admin_headers, db):
    migros = create_application(client, admin_headers, "Migros", contact_email="jobs@migros.ch")
    create_application(client, admin_headers, "Coop", contact_email="jobs@coop.ch")
    raw = build_mail(to="sohn@example.ch", sender="hr@migros.ch", attachments=[("Einladung.pdf", b"x", "application/pdf")])
    assert post_mail(client, raw, envelope_to="bewerbungen@example.ch").json()["application_id"] == migros["id"]
    assert [e["type"] for e in detail(client, admin_headers, migros["id"])["events"]] == ["mail_received"]
    assert db.query(models.Email).one().attachments[0].path.startswith("migros/")


def test_untagged_mail_matches_earlier_mails_of_the_sender_domain(client, admin_headers):
    migros = create_application(client, admin_headers, "Migros")
    post_mail(client, build_mail(sender="hr@migros.ch", message_id="<m1@migros.ch>"), envelope_to=tagged(migros))
    raw = build_mail(sender="chefin@migros.ch", to="bewerbungen@example.ch", message_id="<m2@migros.ch>")
    assert post_mail(client, raw).json()["application_id"] == migros["id"]


@pytest.mark.parametrize(
    "setup",
    [
        "two_applications",  # ambiguous: which one?
        "archived",  # finished applications get no new mails automatically
        "freemail",  # gmail.com says nothing about the company
    ],
)
def test_untagged_mail_stays_in_inbox_unless_the_match_is_unique(client, admin_headers, setup):
    sender = "hr@migros.ch"
    if setup == "two_applications":
        create_application(client, admin_headers, "Migros", contact_email="a@migros.ch")
        create_application(client, admin_headers, "Migros Bank", contact_email="b@migros.ch")
    elif setup == "archived":
        app = create_application(client, admin_headers, "Migros", contact_email="a@migros.ch")
        client.patch(f"/api/applications/{app['id']}", json={"archived": True}, headers=admin_headers)
    else:
        sender = "chef@gmail.com"
        create_application(client, admin_headers, "Garage Meier", contact_email=sender)
    raw = build_mail(sender=sender, to="bewerbungen@example.ch")
    assert post_mail(client, raw).json()["application_id"] is None


def test_untagged_mail_from_a_user_stays_in_inbox(client, admin_headers):
    # A forwarded mail comes from the user, not from the company
    create_user(client, admin_headers, "Sohn", email="sohn@firma-papa.ch")
    create_application(client, admin_headers, "Firma Papa", contact_email="hr@firma-papa.ch")
    raw = build_mail(sender="sohn@firma-papa.ch", to="bewerbungen@example.ch")
    assert post_mail(client, raw).json()["application_id"] is None
