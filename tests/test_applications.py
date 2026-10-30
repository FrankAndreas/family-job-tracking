from datetime import datetime, timedelta, timezone

from app import applications_api, config
from app.settings_store import get_settings
from helpers import add_event, create_application, create_user, login, remove_from_hub


def ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def get(client, headers, application_id):
    response = client.get(f"/api/applications/{application_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_endpoints_need_login(client):
    assert client.get("/api/applications").status_code == 401
    assert client.get("/api/dashboard").status_code == 401


def test_create_application(client, admin_headers):
    app = create_application(client, admin_headers, "Migros", position="Kaufmann EFZ", channel="portal")
    assert app["status"] == "draft"
    assert app["channel"] == "portal"
    assert len(app["mail_tag"]) == 4
    assert app["mail_address"] is None
    assert app["created_by_name"] == "Admin"
    assert app["events"] == []


def test_mail_address_uses_inbound_address(client, admin_headers, db):
    get_settings(db).inbound_address = "bewerbungen@example.ch"
    db.commit()
    app = create_application(client, admin_headers)
    assert app["mail_address"] == f"bewerbungen+{app['mail_tag']}@example.ch"


def test_blank_company_is_rejected(client, admin_headers):
    assert client.post("/api/applications", json={"company": "   "}, headers=admin_headers).status_code == 422


def test_status_follows_events(client, admin_headers):
    app = create_application(client, admin_headers)
    add_event(client, admin_headers, app["id"], "sent", "2026-10-01T10:00:00+02:00")
    assert get(client, admin_headers, app["id"])["status"] == "open"
    add_event(client, admin_headers, app["id"], "reply_received", "2026-10-03T10:00:00+02:00")
    assert get(client, admin_headers, app["id"])["status"] == "in_contact"
    add_event(client, admin_headers, app["id"], "rejection", "2026-10-05T10:00:00+02:00")
    assert get(client, admin_headers, app["id"])["status"] == "closed_rejection"
    add_event(client, admin_headers, app["id"], "offer", "2026-10-07T10:00:00+02:00")
    detail = get(client, admin_headers, app["id"])
    assert detail["status"] == "closed_offer"
    assert [e["type"] for e in detail["events"]] == ["offer", "rejection", "reply_received", "sent"]


def test_event_time_is_converted_to_utc(client, admin_headers):
    app = create_application(client, admin_headers)
    with_offset = add_event(client, admin_headers, app["id"], occurred_at="2026-10-01T10:00:00+02:00")
    naive_local = add_event(client, admin_headers, app["id"], occurred_at="2026-10-01T10:00:00")
    assert with_offset["occurred_at"] == naive_local["occurred_at"] == "2026-10-01T08:00:00Z"
    bad = client.post(
        f"/api/applications/{app['id']}/events",
        data={"type": "sent", "occurred_at": "gestern"},
        headers=admin_headers,
    )
    assert bad.status_code == 422


def test_event_with_files(client, admin_headers):
    app = create_application(client, admin_headers, "Migros")
    event = add_event(
        client,
        admin_headers,
        app["id"],
        occurred_at="2026-10-15T09:00:00+02:00",
        files=[
            ("files", ("Lebenslauf.pdf", b"%PDF-1", "application/pdf")),
            ("files", ("Lebenslauf.pdf", b"%PDF-2", "application/pdf")),
        ],
    )
    assert event["created_by_name"] == "Admin"
    assert [a["path"] for a in event["attachments"]] == [
        "migros/2026-10-15_migros_Lebenslauf.pdf",
        "migros/2026-10-15_migros_Lebenslauf_2.pdf",
    ]
    download = client.get(f"/api/attachments/{event['attachments'][0]['id']}", headers=admin_headers)
    assert download.status_code == 200
    assert download.content == b"%PDF-1"
    assert "Lebenslauf.pdf" in download.headers["content-disposition"]


def test_too_large_upload_is_413(client, admin_headers, monkeypatch):
    monkeypatch.setattr(applications_api, "MAX_UPLOAD_BYTES", 5)
    app = create_application(client, admin_headers, "Migros")
    response = client.post(
        f"/api/applications/{app['id']}/events",
        data={"type": "sent", "occurred_at": "2026-10-01T10:00:00"},
        files=[("files", ("gross.pdf", b"123456", "application/pdf"))],
        headers=admin_headers,
    )
    assert response.status_code == 413
    assert not (config.files_dir() / "migros").exists()
    assert get(client, admin_headers, app["id"])["events"] == []


def test_update_and_delete_event(client, admin_headers):
    app = create_application(client, admin_headers)
    event = add_event(client, admin_headers, app["id"])
    updated = client.patch(
        f"/api/events/{event['id']}", json={"type": "followed_up", "note": " Telefon "}, headers=admin_headers
    ).json()
    assert updated["type"] == "followed_up"
    assert updated["note"] == "Telefon"
    assert client.delete(f"/api/events/{event['id']}", headers=admin_headers).status_code == 204
    assert get(client, admin_headers, app["id"])["events"] == []


def test_delete_attachment_removes_file(client, admin_headers):
    app = create_application(client, admin_headers)
    event = add_event(client, admin_headers, app["id"], files=[("files", ("cv.pdf", b"x", "application/pdf"))])
    attachment = event["attachments"][0]
    assert client.delete(f"/api/attachments/{attachment['id']}", headers=admin_headers).status_code == 204
    assert not (config.files_dir() / attachment["path"]).exists()
    assert get(client, admin_headers, app["id"])["events"][0]["attachments"] == []


def test_list_filters(client, admin_headers):
    migros = create_application(client, admin_headers, "Migros")
    coop = create_application(client, admin_headers, "Coop", position="Logistiker EFZ")
    add_event(client, admin_headers, migros["id"])
    client.patch(f"/api/applications/{coop['id']}", json={"archived": True}, headers=admin_headers)

    def companies(**params):
        response = client.get("/api/applications", params=params, headers=admin_headers)
        return [a["company"] for a in response.json()]

    assert companies() == ["Migros"]
    assert sorted(companies(include_archived=True)) == ["Coop", "Migros"]
    assert companies(include_archived=True, q="logis") == ["Coop"]
    assert companies(status="open") == ["Migros"]


def test_update_application(client, admin_headers):
    app = create_application(client, admin_headers)
    updated = client.patch(
        f"/api/applications/{app['id']}",
        json={"company": "Migros Aare", "contact_email": " Jobs@Migros.CH ", "position": None},
        headers=admin_headers,
    ).json()
    assert updated["company"] == "Migros Aare"
    assert updated["contact_email"] == "jobs@migros.ch"
    assert updated["position"] == ""


def test_dashboard_counts_and_due(client, admin_headers):
    migros = create_application(client, admin_headers, "Migros")
    add_event(client, admin_headers, migros["id"], occurred_at=ago(20))
    coop = create_application(client, admin_headers, "Coop")
    add_event(client, admin_headers, coop["id"], occurred_at=ago(2))
    dashboard = client.get("/api/dashboard", headers=admin_headers).json()
    assert dashboard["counts"]["open"] == 2
    assert dashboard["counts"]["draft"] == 0
    assert [a["company"] for a in dashboard["due"]] == ["Migros"]
    assert dashboard["due"][0]["days_since_last"] >= 19
    assert dashboard["inbox_count"] == 0


def test_delete_application_removes_files(client, admin_headers):
    app = create_application(client, admin_headers)
    event = add_event(client, admin_headers, app["id"], files=[("files", ("cv.pdf", b"x", "application/pdf"))])
    assert client.delete(f"/api/applications/{app['id']}", headers=admin_headers).status_code == 204
    assert client.get(f"/api/applications/{app['id']}", headers=admin_headers).status_code == 404
    assert not (config.files_dir() / event["attachments"][0]["path"]).exists()


def test_deleting_user_keeps_their_events(client, admin_headers):
    create_user(client, admin_headers, "Sohn")
    son = login(client, "Sohn", "5678")
    app = create_application(client, son)
    add_event(client, son, app["id"])
    son_id = next(u["id"] for u in client.get("/api/users", headers=admin_headers).json() if u["name"] == "Sohn")
    # Only someone the family hub no longer lists is deleted here
    remove_from_hub("Sohn")
    client.get("/api/users", headers=admin_headers)
    assert client.delete(f"/api/users/{son_id}", headers=admin_headers).status_code == 204
    detail = get(client, admin_headers, app["id"])
    assert detail["created_by_name"] is None
    assert len(detail["events"]) == 1
    assert detail["events"][0]["created_by_name"] is None


def test_closing_kind_and_reason_in_list_and_detail(client, admin_headers):
    app = create_application(client, admin_headers, "Migros")
    add_event(client, admin_headers, app["id"], "sent", "2026-10-01T10:00:00+02:00")
    add_event(client, admin_headers, app["id"], "position_filled", "2026-10-05T10:00:00+02:00", note="Stelle seit Juli besetzt")
    detail = client.get(f"/api/applications/{app['id']}", headers=admin_headers).json()
    assert (detail["status"], detail["closed_by"], detail["closed_note"]) == (
        "closed_rejection", "position_filled", "Stelle seit Juli besetzt"
    )
    item = client.get("/api/applications", headers=admin_headers).json()[0]
    assert (item["closed_by"], item["closed_note"]) == ("position_filled", "Stelle seit Juli besetzt")
    assert client.get("/api/dashboard", headers=admin_headers).json()["counts"]["closed_rejection"] == 1


def test_open_application_has_no_closing_kind(client, admin_headers):
    app = create_application(client, admin_headers, "Coop")
    add_event(client, admin_headers, app["id"], "sent")
    detail = client.get(f"/api/applications/{app['id']}", headers=admin_headers).json()
    assert (detail["closed_by"], detail["closed_note"]) == (None, None)


def test_an_old_rejection_can_be_turned_into_another_kind(client, admin_headers):
    app = create_application(client, admin_headers, "Migros")
    event = add_event(client, admin_headers, app["id"], "rejection")
    response = client.patch(
        f"/api/events/{event['id']}", json={"type": "no_position", "note": "Kein Lehrbetrieb"}, headers=admin_headers
    )
    assert response.status_code == 200, response.text
    detail = client.get(f"/api/applications/{app['id']}", headers=admin_headers).json()
    assert (detail["closed_by"], detail["closed_note"]) == ("no_position", "Kein Lehrbetrieb")
