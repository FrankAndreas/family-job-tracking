from datetime import timedelta

from app import models
from app.timeutil import utcnow
from helpers import ADMIN, ADMIN_PIN, login


def test_public_users_lists_admin(client):
    response = client.get("/api/users/public")
    assert response.status_code == 200
    assert [u["name"] for u in response.json()] == [ADMIN]


def test_login_and_me(client):
    headers = login(client)
    me = client.get("/api/me", headers=headers).json()
    assert me["name"] == ADMIN
    assert me["is_admin"] is True
    assert me["email"] is None


def test_wrong_pin_and_unknown_user_are_401(client):
    assert client.post("/api/token", json={"name": ADMIN, "pin": "0000"}).status_code == 401
    assert client.post("/api/token", json={"name": "Niemand", "pin": ADMIN_PIN}).status_code == 401


def test_requests_without_valid_token_are_401(client):
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers={"Authorization": "Bearer kaputt"}).status_code == 401


def test_five_wrong_pins_lock_the_user(client, db):
    for _ in range(5):
        assert client.post("/api/token", json={"name": ADMIN, "pin": "0000"}).status_code == 401
    locked = client.post("/api/token", json={"name": ADMIN, "pin": ADMIN_PIN})
    assert locked.status_code == 429
    assert "Minuten" in locked.json()["detail"]

    # Once the lock has expired the right PIN works again
    user = db.query(models.User).filter_by(name=ADMIN).one()
    user.locked_until = utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.post("/api/token", json={"name": ADMIN, "pin": ADMIN_PIN}).status_code == 200


def test_successful_login_resets_failed_count(client, db):
    for _ in range(4):
        client.post("/api/token", json={"name": ADMIN, "pin": "0000"})
    login(client)
    assert db.query(models.User).filter_by(name=ADMIN).one().failed_logins == 0


def test_change_own_pin(client, admin_headers):
    wrong = client.post("/api/me/pin", json={"current_pin": "9999", "new_pin": "4321"}, headers=admin_headers)
    assert wrong.status_code == 400
    too_short = client.post("/api/me/pin", json={"current_pin": ADMIN_PIN, "new_pin": "12"}, headers=admin_headers)
    assert too_short.status_code == 422
    ok = client.post("/api/me/pin", json={"current_pin": ADMIN_PIN, "new_pin": "43210"}, headers=admin_headers)
    assert ok.status_code == 204
    login(client, pin="43210")


def test_update_own_email_and_reminders(client, admin_headers):
    response = client.patch(
        "/api/me", json={"email": " Papa@Example.CH ", "wants_reminders": True}, headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["email"] == "papa@example.ch"
    assert response.json()["wants_reminders"] is True
    cleared = client.patch("/api/me", json={"email": ""}, headers=admin_headers).json()
    assert cleared["email"] is None
    assert client.patch("/api/me", json={"email": "keine-adresse"}, headers=admin_headers).status_code == 422
