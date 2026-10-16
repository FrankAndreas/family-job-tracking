import codecs
import csv
import io
import zipfile

from fastapi.testclient import TestClient

from app import reminders
from app.main import app as fastapi_app
from helpers import add_event, create_application, create_user, login
from mails import BROKEN_MAIL, INBOUND_SECRET, build_mail, post_mail


def integrations(client, headers):
    response = client.get("/api/integrations", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def configure_resend(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("MAIL_FROM", "bewerbungen@example.ch")


def test_app_starts_without_optional_integrations():
    with TestClient(fastapi_app) as client:
        assert client.get("/health").status_code == 200


def test_settings_defaults_and_admin_update(client, admin_headers):
    defaults = client.get("/api/settings", headers=admin_headers).json()
    assert defaults == {"followup_days": 10, "reminder_time": "07:00", "inbound_address": ""}
    response = client.patch(
        "/api/settings",
        json={"followup_days": 7, "reminder_time": "18:30", "inbound_address": " Bewerbungen@Example.ch "},
        headers=admin_headers,
    )
    assert response.json() == {"followup_days": 7, "reminder_time": "18:30", "inbound_address": "bewerbungen@example.ch"}


def test_settings_validation_and_permissions(client, admin_headers):
    for body in ({"followup_days": 0}, {"reminder_time": "25:00"}, {"inbound_address": "keine-adresse"}):
        assert client.patch("/api/settings", json=body, headers=admin_headers).status_code == 422
    create_user(client, admin_headers, "Sohn")
    son = login(client, "Sohn", "5678")
    assert client.get("/api/settings", headers=son).status_code == 200
    assert client.patch("/api/settings", json={"followup_days": 5}, headers=son).status_code == 403


def test_integrations_not_configured(client, admin_headers):
    data = integrations(client, admin_headers)
    assert data["inbound"]["state"] == "not_configured"
    assert data["reminders"]["state"] == "not_configured"
    assert data["reminders"]["details"]["next_run"] is None


def test_inbound_integration_states(client, admin_headers, monkeypatch):
    monkeypatch.setenv("INBOUND_SECRET", INBOUND_SECRET)
    assert integrations(client, admin_headers)["inbound"]["state"] == "waiting"
    post_mail(client, BROKEN_MAIL)
    broken = integrations(client, admin_headers)["inbound"]
    assert broken["state"] == "error"
    assert broken["details"]["last_error"]
    post_mail(client, build_mail())
    ok = integrations(client, admin_headers)["inbound"]
    assert ok["state"] == "ok"
    assert ok["details"]["last_received_at"] is not None


def test_reminder_integration_states(client, admin_headers, monkeypatch):
    configure_resend(monkeypatch)
    data = integrations(client, admin_headers)["reminders"]
    assert data["state"] == "ok"
    assert data["details"]["mail_from"] == "bewerbungen@example.ch"
    assert data["details"]["next_run"] is not None
    assert any("APP_URL" in w for w in data["warnings"])
    assert any("Niemand" in w for w in data["warnings"])

    client.patch("/api/me", json={"email": "papa@example.ch", "wants_reminders": True}, headers=admin_headers)

    def failing(*args):
        raise RuntimeError("Resend 401: bad key")

    monkeypatch.setattr(reminders, "resend_send", failing)
    response = client.post("/api/integrations/reminders/test", headers=admin_headers)
    assert response.status_code == 502
    assert "Resend 401" in response.json()["detail"]
    data = integrations(client, admin_headers)["reminders"]
    assert data["state"] == "error"
    assert "Resend 401" in data["details"]["last_error"]
    assert data["details"]["recipients"] == ["papa@example.ch"]


def test_test_reminder(client, admin_headers, monkeypatch):
    assert client.post("/api/integrations/reminders/test", headers=admin_headers).status_code == 400
    configure_resend(monkeypatch)
    assert client.post("/api/integrations/reminders/test", headers=admin_headers).status_code == 400
    client.patch("/api/me", json={"email": "papa@example.ch"}, headers=admin_headers)
    sent = []
    monkeypatch.setattr(reminders, "resend_send", lambda *args: sent.append(args))
    assert client.post("/api/integrations/reminders/test", headers=admin_headers).status_code == 204
    assert sent[0][1] == ["papa@example.ch"]


def test_export_zip(client, admin_headers):
    application = create_application(client, admin_headers, "Migros")
    add_event(client, admin_headers, application["id"], files=[("files", ("cv.pdf", b"x", "application/pdf"))])
    response = client.get("/api/export", headers=admin_headers)
    assert response.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = set(archive.namelist())
    assert {"users.csv", "applications.csv", "events.csv", "emails.csv", "attachments.csv"} <= names
    assert any(name.startswith("files/migros/") for name in names)
    users_csv = archive.read("users.csv").decode()
    assert "Admin" in users_csv
    assert "pin_hash" not in users_csv


def read_csv(archive, name):
    raw = archive.read(name)
    assert raw.startswith(codecs.BOM_UTF8), f"{name} needs a BOM so Excel reads it as UTF-8"
    return list(csv.reader(io.StringIO(raw.decode("utf-8-sig")), delimiter=";"))


def test_export_is_excel_friendly(client, admin_headers):
    create_application(client, admin_headers, "Bäckerei Zürich")
    archive = zipfile.ZipFile(io.BytesIO(client.get("/api/export", headers=admin_headers).content))
    for name in ("users.csv", "applications.csv", "events.csv", "emails.csv", "attachments.csv"):
        rows = read_csv(archive, name)
        assert len(rows[0]) > 1, f"{name} must be split on semicolons"
    assert any("Bäckerei Zürich" in row for row in read_csv(archive, "applications.csv"))


def test_export_overview_one_row_per_application(client, admin_headers):
    migros = create_application(client, admin_headers, "Migros", position="Lehrstelle Informatiker")
    add_event(client, admin_headers, migros["id"], "sent", "2026-09-01T10:00:00+02:00")
    add_event(client, admin_headers, migros["id"], "interview", "2026-09-20T14:30:00+02:00")
    create_application(client, admin_headers, "Coop")
    archive = zipfile.ZipFile(io.BytesIO(client.get("/api/export", headers=admin_headers).content))
    header, *rows = read_csv(archive, "uebersicht.csv")
    by_company = {row[header.index("Firma")]: dict(zip(header, row)) for row in rows}
    assert set(by_company) == {"Migros", "Coop"}
    migros_row = by_company["Migros"]
    assert migros_row["Stelle"] == "Lehrstelle Informatiker"
    assert migros_row["Status"] == "In Kontakt"
    assert migros_row["Beworben am"] == "01.09.2026"
    assert migros_row["Letztes Ereignis"] == "Vorstellungsgespräch"
    assert migros_row["Letzter Kontakt"] == "20.09.2026"
    assert migros_row["Nachfassen ab"] == "30.09.2026"
    assert migros_row["Ereignisse"] == "2"
    assert by_company["Coop"]["Status"] == "Entwurf"
    assert by_company["Coop"]["Beworben am"] == ""


def test_export_timeline_readable(client, admin_headers):
    migros = create_application(client, admin_headers, "Migros")
    add_event(
        client, admin_headers, migros["id"], "followed_up", "2026-09-10T09:15:00+02:00", note="Telefonisch",
        files=[("files", ("brief.pdf", b"x", "application/pdf"))],
    )
    archive = zipfile.ZipFile(io.BytesIO(client.get("/api/export", headers=admin_headers).content))
    header, *rows = read_csv(archive, "zeitleiste.csv")
    row = dict(zip(header, rows[0]))
    assert row["Datum"] == "10.09.2026 09:15"
    assert row["Firma"] == "Migros"
    assert row["Ereignis"] == "Nachgefragt"
    assert row["Notiz"] == "Telefonisch"
    assert row["Erfasst von"] == "Admin"
    assert row["Anhänge"] == "brief.pdf"
