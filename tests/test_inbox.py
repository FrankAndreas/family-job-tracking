import pytest

from app import config
from helpers import create_application
from mails import INBOUND_SECRET, build_mail, post_mail


@pytest.fixture(autouse=True)
def inbound_secret(monkeypatch):
    monkeypatch.setenv("INBOUND_SECRET", INBOUND_SECRET)


def inbox(client, headers):
    response = client.get("/api/inbox", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_inbox_needs_login(client):
    assert client.get("/api/inbox").status_code == 401


def test_inbox_suggests_application_by_sender_domain(client, admin_headers):
    # Two applications at the same company: no automatic assignment, but a suggestion
    create_application(client, admin_headers, "Migros", position="Logistiker", contact_email="jobs@migros.ch")
    migros = create_application(client, admin_headers, "Migros", position="Informatiker", contact_email="it@migros.ch")
    create_application(client, admin_headers, "Coop", contact_email="jobs@coop.ch")
    post_mail(client, build_mail(to="bewerbungen@example.ch", sender="hr@migros.ch"))
    items = inbox(client, admin_headers)
    assert len(items) == 1
    assert items[0]["subject"] == "Ihre Bewerbung"
    assert items[0]["suggestion"] == {"id": migros["id"], "company": "Migros", "position": "Informatiker"}


def test_freemail_sender_gets_no_suggestion(client, admin_headers):
    create_application(client, admin_headers, "Garage Meier", contact_email="chef@gmail.com")
    post_mail(client, build_mail(to="bewerbungen@example.ch", sender="chef@gmail.com"))
    assert inbox(client, admin_headers)[0]["suggestion"] is None


def test_assign_moves_files_and_creates_event(client, admin_headers):
    migros = create_application(client, admin_headers, "Migros")
    post_mail(
        client,
        build_mail(to="bewerbungen@example.ch", attachments=[("Zeugnis.pdf", b"x", "application/pdf")]),
    )
    email = inbox(client, admin_headers)[0]
    response = client.post(
        f"/api/inbox/{email['id']}/assign", json={"application_id": migros["id"]}, headers=admin_headers
    )
    assert response.status_code == 200, response.text
    assert inbox(client, admin_headers) == []

    event = client.get(f"/api/applications/{migros['id']}", headers=admin_headers).json()["events"][0]
    assert event["type"] == "mail_received"
    path = event["email"]["attachments"][0]["path"]
    assert path == "migros/2026-10-15_migros_Zeugnis.pdf"
    assert (config.files_dir() / path).exists()
    assert list((config.files_dir() / "_posteingang").iterdir()) == []


def test_assign_with_event_type(client, admin_headers):
    migros = create_application(client, admin_headers, "Migros")
    post_mail(client, build_mail(to="bewerbungen@example.ch"))
    email = inbox(client, admin_headers)[0]
    client.post(
        f"/api/inbox/{email['id']}/assign",
        json={"application_id": migros["id"], "event_type": "reply_received"},
        headers=admin_headers,
    )
    events = client.get(f"/api/applications/{migros['id']}", headers=admin_headers).json()["events"]
    assert [e["type"] for e in events] == ["reply_received"]


def test_assign_twice_is_409(client, admin_headers):
    migros = create_application(client, admin_headers, "Migros")
    post_mail(client, build_mail(to="bewerbungen@example.ch"))
    email_id = inbox(client, admin_headers)[0]["id"]
    body = {"application_id": migros["id"]}
    assert client.post(f"/api/inbox/{email_id}/assign", json=body, headers=admin_headers).status_code == 200
    assert client.post(f"/api/inbox/{email_id}/assign", json=body, headers=admin_headers).status_code == 409


def test_create_application_from_mail(client, admin_headers):
    post_mail(client, build_mail(to="bewerbungen@example.ch", sender="hr@coop.ch"))
    email_id = inbox(client, admin_headers)[0]["id"]
    response = client.post(
        f"/api/inbox/{email_id}/create-application",
        json={"company": "Coop", "position": "Logistiker EFZ"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    application = client.get(f"/api/applications/{response.json()['application_id']}", headers=admin_headers).json()
    assert application["company"] == "Coop"
    assert application["position"] == "Logistiker EFZ"
    assert application["contact_email"] == "hr@coop.ch"
    assert [e["type"] for e in application["events"]] == ["mail_received"]
    assert application["status"] == "in_contact"


def test_dismiss(client, admin_headers):
    post_mail(client, build_mail(to="bewerbungen@example.ch"))
    email_id = inbox(client, admin_headers)[0]["id"]
    assert client.post(f"/api/inbox/{email_id}/dismiss", headers=admin_headers).status_code == 204
    assert inbox(client, admin_headers) == []
    assert client.get("/api/dashboard", headers=admin_headers).json()["inbox_count"] == 0


def test_read_email_and_raw(client, admin_headers):
    raw = build_mail(to="bewerbungen@example.ch")
    post_mail(client, raw)
    email_id = inbox(client, admin_headers)[0]["id"]
    assert client.get(f"/api/emails/{email_id}", headers=admin_headers).json()["body_text"] == "Guten Tag"
    response = client.get(f"/api/emails/{email_id}/raw", headers=admin_headers)
    assert response.status_code == 200
    assert response.content == raw


def test_assign_with_a_missing_file_still_works(client, admin_headers):
    migros = create_application(client, admin_headers, "Migros")
    attachments = [("Zeugnis.pdf", b"x", "application/pdf"), ("Brief.pdf", b"y", "application/pdf")]
    post_mail(client, build_mail(to="bewerbungen@example.ch", attachments=attachments))
    email = inbox(client, admin_headers)[0]
    # Someone deleted one attachment in File Station
    (config.files_dir() / email["attachments"][0]["path"]).unlink()
    response = client.post(
        f"/api/inbox/{email['id']}/assign", json={"application_id": migros["id"]}, headers=admin_headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["attachments"][1]["path"] == "migros/2026-10-15_migros_Brief.pdf"
    assert client.get(f"/api/emails/{email['id']}/raw", headers=admin_headers).status_code == 200


def test_failed_assign_moves_files_back(client, admin_headers, monkeypatch):
    from app import files

    migros = create_application(client, admin_headers, "Migros")
    post_mail(client, build_mail(to="bewerbungen@example.ch", attachments=[("Zeugnis.pdf", b"x", "application/pdf")]))
    email = inbox(client, admin_headers)[0]
    real_move = files.move_to_company
    calls = []

    def failing_second_move(rel_path, company):
        calls.append(rel_path)
        if len(calls) == 2:
            raise OSError("disk full")
        return real_move(rel_path, company)

    monkeypatch.setattr(files, "move_to_company", failing_second_move)
    with pytest.raises(OSError):
        client.post(f"/api/inbox/{email['id']}/assign", json={"application_id": migros["id"]}, headers=admin_headers)
    assert sorted(p.name for p in (config.files_dir() / "_posteingang").iterdir()) == [
        "2026-10-15_migros-ch_Zeugnis.pdf",
        "2026-10-15_migros-ch_mail-Ihre-Bewerbung.eml",
    ]
    assert len(inbox(client, admin_headers)) == 1


def test_deleting_the_mail_event_returns_the_mail_to_the_inbox(client, admin_headers):
    migros = create_application(client, admin_headers, "Migros")
    post_mail(client, build_mail(to="bewerbungen@example.ch", attachments=[("Zeugnis.pdf", b"x", "application/pdf")]))
    email_id = inbox(client, admin_headers)[0]["id"]
    client.post(f"/api/inbox/{email_id}/assign", json={"application_id": migros["id"]}, headers=admin_headers)
    event = client.get(f"/api/applications/{migros['id']}", headers=admin_headers).json()["events"][0]
    assert client.delete(f"/api/events/{event['id']}", headers=admin_headers).status_code == 204

    items = inbox(client, admin_headers)
    assert [i["id"] for i in items] == [email_id]
    path = items[0]["attachments"][0]["path"]
    assert path == "_posteingang/2026-10-15_migros-ch_Zeugnis.pdf"
    assert (config.files_dir() / path).exists()
