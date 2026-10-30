"""Logging in through the family hub, and the people the hub gives the app (spec 2026-10-30). Invented people."""

import sqlite3

import fake_hub
from helpers import ADMIN, bearer, create_user, login, remove_from_hub
from mails import INBOUND_SECRET, build_mail, post_mail
from sqlalchemy import create_engine

from app import database, models, reminders, upgrade


def me(client, headers=None):
    return client.get("/api/me", headers=headers)


def row(name):
    with database.SessionLocal() as db:
        return db.query(models.User).filter(models.User.name == name).one()


# Logging in


def test_no_login_401(client):
    response = me(client)
    assert response.status_code == 401 and response.json()["detail"] == "not_logged_in"


def test_unknown_token_401(client):
    assert me(client, bearer("tok-nobody")).status_code == 401


def test_cookie_login_needs_the_header_for_changes(client):
    client.cookies.set("hub_session", fake_hub.token(ADMIN))
    assert me(client).json()["name"] == ADMIN
    refused = client.post("/api/applications", json={"company": "Migros"})
    assert refused.status_code == 403 and refused.json()["detail"] == "csrf"
    allowed = client.post("/api/applications", json={"company": "Migros"}, headers={"X-Requested-With": "jobs"})
    assert allowed.status_code == 201


def test_no_access_403(client, family_hub):
    family_hub.add("Max", "PARENT", access=False)
    response = me(client, bearer(fake_hub.token("Max")))
    assert response.status_code == 403 and response.json()["detail"] == "no_access"


def test_hub_down_503(client, family_hub):
    family_hub.down = True
    response = me(client, bearer(fake_hub.token(ADMIN)))
    assert response.status_code == 503 and response.json()["detail"] == "hub_unavailable"


def test_no_login_through_the_tunnel(client):
    # Home only (2026-10-30): only the e-mail worker comes through the tunnel, with its own secret
    response = me(client, {**bearer(fake_hub.token(ADMIN)), "Cf-Connecting-Ip": "203.0.113.7"})
    assert response.status_code == 401


def test_hub_login_url(client, monkeypatch):
    monkeypatch.setenv("HUB_PUBLIC_URL", "https://home.local.example.ch")
    assert client.get("/api/hub").json() == {"login_url": "https://home.local.example.ch"}


def test_removed_endpoints(client):
    headers = login(client)
    admin_id = me(client, headers).json()["id"]
    assert client.post("/api/token", json={"name": ADMIN, "pin": "1234"}).status_code in (404, 405)
    assert client.get("/api/users/public").status_code in (404, 405)
    assert client.post("/api/users", json={"name": "X", "pin": "1234"}, headers=headers).status_code in (404, 405)
    assert client.post("/api/me/pin", json={"current_pin": "1", "new_pin": "2"}, headers=headers).status_code in (
        404,
        405,
    )
    assert client.post(f"/api/users/{admin_id}/pin", json={"pin": "9999"}, headers=headers).status_code in (404, 405)


def test_own_email_and_reminders(client, admin_headers):
    response = client.patch(
        "/api/me", json={"email": " Papa@Example.CH ", "wants_reminders": True}, headers=admin_headers
    )
    assert response.status_code == 200
    assert (response.json()["email"], response.json()["wants_reminders"]) == ("papa@example.ch", True)
    assert client.patch("/api/me", json={"email": ""}, headers=admin_headers).json()["email"] is None
    assert client.patch("/api/me", json={"email": "keine-adresse"}, headers=admin_headers).status_code == 422


# The people from the hub: a parent there is admin here


def test_existing_admin_linked_at_the_switch(client, family_hub):
    before = row(ADMIN)
    assert before.hub_id is None
    login(client)
    after = row(ADMIN)
    assert (after.id, after.hub_id) == (before.id, family_hub.people[ADMIN].id)


def test_linking_needs_the_matching_role(client, family_hub):
    with database.SessionLocal() as db:
        db.add(models.User(name="Sohn", is_admin=False))
        db.add(models.User(name="Mama", is_admin=False))
        db.commit()
    family_hub.add("Sohn", "CHILD")
    # The hub calls Mama a parent: not the old non-admin row
    family_hub.add("Mama", "PARENT")
    login(client)
    assert row("Sohn").hub_id == family_hub.people["Sohn"].id
    with database.SessionLocal() as db:
        assert db.query(models.User).filter(models.User.hub_id.is_(None)).one().is_active is False


def test_old_rows_linked_by_name_only_at_the_switch(client, family_hub):
    with database.SessionLocal() as db:
        db.add(models.User(name="Beat", is_admin=False))
        db.commit()
    login(client)
    family_hub.add("Beat", "CHILD")
    login(client, "Beat")
    with database.SessionLocal() as db:
        rows = db.query(models.User).filter(models.User.name.like("Beat%")).all()
        assert len(rows) == 2 and {r.hub_id is None for r in rows} == {True, False}


def test_admin_follows_the_hub(client, family_hub):
    create_user(client, None, "Mama", is_admin=True)
    assert client.get("/api/users", headers=login(client, "Mama")).status_code == 200
    family_hub.set_role("Mama", "CHILD")
    assert client.get("/api/users", headers=login(client, "Mama")).status_code == 403


def test_names_and_admin_only_in_the_hub(client, admin_headers):
    sohn = create_user(client, None, "Sohn")
    refused = client.patch(f"/api/users/{sohn['id']}", json={"name": "Junior"}, headers=admin_headers)
    assert refused.status_code == 400 and refused.json()["detail"] == "from_hub"
    refused = client.patch(f"/api/users/{sohn['id']}", json={"is_admin": True}, headers=admin_headers)
    assert refused.status_code == 400 and refused.json()["detail"] == "from_hub"
    changed = client.patch(f"/api/users/{sohn['id']}", json={"email": "sohn@example.ch"}, headers=admin_headers)
    assert changed.status_code == 200 and changed.json()["email"] == "sohn@example.ch"


# E-mail addresses from the hub, when its tile for this app shares them (2026-10-30): one place to keep them


def test_addresses_come_from_the_hub_when_shared(client, family_hub):
    family_hub.share_email = True
    family_hub.emails[ADMIN] = "papa@example.ch"
    family_hub._changed()
    headers = login(client)
    found = me(client, headers).json()
    assert (found["email"], found["email_from_hub"]) == ("papa@example.ch", True)
    refused = client.patch("/api/me", json={"email": "other@example.ch"}, headers=headers)
    assert refused.status_code == 400 and refused.json()["detail"] == "from_hub"
    assert client.patch("/api/me", json={"wants_reminders": True}, headers=headers).status_code == 200


def test_no_address_in_the_hub_means_none_here(client, family_hub, admin_headers):
    client.patch("/api/me", json={"email": "alt@example.ch"}, headers=admin_headers)
    family_hub.share_email = True
    family_hub._changed()
    assert me(client, login(client)).json()["email"] is None


def test_without_sharing_the_app_keeps_its_own(client, admin_headers):
    client.patch("/api/me", json={"email": "papa@example.ch"}, headers=admin_headers)
    found = me(client, admin_headers).json()
    assert (found["email"], found["email_from_hub"]) == ("papa@example.ch", False)


# Removed in the hub: hidden with their data, until an admin deletes it


def test_removed_person_hidden_and_deleted(client, admin_headers):
    sohn = create_user(client, None, "Sohn")
    refused = client.delete(f"/api/users/{sohn['id']}", headers=admin_headers)
    assert refused.status_code == 409 and refused.json()["detail"] == "still_in_hub"
    remove_from_hub("Sohn")
    assert "Sohn" not in [u["name"] for u in client.get("/api/users", headers=admin_headers).json()]
    assert [u["name"] for u in client.get("/api/users/removed", headers=admin_headers).json()] == ["Sohn"]
    assert client.delete(f"/api/users/{sohn['id']}", headers=admin_headers).status_code == 204
    assert client.get("/api/users/removed", headers=admin_headers).json() == []


def test_the_people_list_asks_the_hub_now(client, family_hub, admin_headers):
    create_user(client, None, "Sohn")
    family_hub.access.discard("Sohn")  # changed in the hub, without the app hearing about it
    assert "Sohn" not in [u["name"] for u in client.get("/api/users", headers=admin_headers).json()]


def test_removed_person_gets_no_reminders(client, db, admin_headers):
    create_user(client, None, "Sohn", email="sohn@example.ch", wants_reminders=True)
    remove_from_hub("Sohn")
    client.get("/api/users", headers=admin_headers)
    assert "sohn@example.ch" not in reminders.recipients(db)


def test_suggestion_links_only_from_active_people(client, admin_headers, db, monkeypatch):
    monkeypatch.setenv("INBOUND_SECRET", INBOUND_SECRET)
    create_user(client, None, "Sohn", email="sohn@example.ch")
    remove_from_hub("Sohn")
    client.get("/api/users", headers=admin_headers)
    raw = build_mail(
        sender="Sohn <sohn@example.ch>", to="bewerbungen+vorschlag@example.ch", body="https://www.yousty.ch/x"
    )
    assert post_mail(client, raw).json()["status"] != "suggestions"
    assert db.query(models.Suggestion).count() == 0


# The database from before the hub gets the new columns on start


def test_upgrade_of_an_old_database(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, name VARCHAR(50) NOT NULL UNIQUE,"
            " pin_hash VARCHAR NOT NULL, is_admin BOOLEAN NOT NULL, email VARCHAR(200),"
            " wants_reminders BOOLEAN NOT NULL, failed_logins INTEGER NOT NULL, locked_until DATETIME,"
            " created_at DATETIME NOT NULL)"
        )
        conn.execute(
            "INSERT INTO users (name, pin_hash, is_admin, email, wants_reminders, failed_logins, created_at)"
            " VALUES ('Papa', 'x', 1, 'papa@example.ch', 1, 0, '2026-10-01 10:00:00')"
        )
    engine = create_engine(f"sqlite:///{path}")
    upgrade.upgrade(engine)
    upgrade.upgrade(engine)  # a second start changes nothing
    with sqlite3.connect(path) as conn:
        columns = [r[1] for r in conn.execute("PRAGMA table_info(users)")]
        assert "pin_hash" not in columns and {"hub_id", "is_active", "email_from_hub"} <= set(columns)
        assert conn.execute("SELECT name, email, is_admin, is_active, hub_id FROM users").fetchall() == [
            ("Papa", "papa@example.ch", 1, 1, None)
        ]


def test_missing_address_hint_points_to_the_hub(client, family_hub, db):
    from app import integrations
    from app.timeutil import utcnow

    create_user(client, None, "Sohn")
    remove_from_hub("Sohn")
    family_hub.share_email = True
    family_hub._changed()
    client.get("/api/users", headers=login(client))
    warnings = " ".join(integrations.status(db, utcnow())["inbound"]["warnings"])
    # Someone removed in the hub isn't listed; the address is added (and confirmed) in the hub
    assert "Ohne E-Mail-Adresse: Admin." in warnings and "Familien-Hub" in warnings and "Sohn" not in warnings
