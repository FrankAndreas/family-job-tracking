from helpers import create_user, login


def test_admin_creates_user_who_can_log_in(client, admin_headers):
    user = create_user(client, admin_headers, "Sohn", pin="5678", email="sohn@example.ch")
    assert user["is_admin"] is False
    assert user["email"] == "sohn@example.ch"
    headers = login(client, "Sohn", "5678")
    assert client.get("/api/me", headers=headers).json()["name"] == "Sohn"
    names = [u["name"] for u in client.get("/api/users", headers=admin_headers).json()]
    assert names == ["Admin", "Sohn"]


def test_non_admin_cannot_manage_users(client, admin_headers):
    create_user(client, admin_headers, "Sohn")
    headers = login(client, "Sohn", "5678")
    assert client.get("/api/users", headers=headers).status_code == 403
    assert client.post("/api/users", json={"name": "X", "pin": "1111"}, headers=headers).status_code == 403


def test_duplicate_name_is_409(client, admin_headers):
    create_user(client, admin_headers, "Sohn")
    response = client.post("/api/users", json={"name": "Sohn", "pin": "1111"}, headers=admin_headers)
    assert response.status_code == 409


def test_admin_renames_resets_pin_and_promotes(client, admin_headers):
    user = create_user(client, admin_headers, "Sohn")
    renamed = client.patch(f"/api/users/{user['id']}", json={"name": "Luca", "is_admin": True}, headers=admin_headers)
    assert renamed.json()["name"] == "Luca"
    assert renamed.json()["is_admin"] is True
    assert client.post(f"/api/users/{user['id']}/pin", json={"pin": "2468"}, headers=admin_headers).status_code == 204
    login(client, "Luca", "2468")


def test_last_admin_cannot_be_demoted_and_self_cannot_be_deleted(client, admin_headers):
    me = client.get("/api/me", headers=admin_headers).json()
    demote = client.patch(f"/api/users/{me['id']}", json={"is_admin": False}, headers=admin_headers)
    assert demote.status_code == 400
    assert client.delete(f"/api/users/{me['id']}", headers=admin_headers).status_code == 400


def test_admin_deletes_user(client, admin_headers):
    user = create_user(client, admin_headers, "Sohn")
    assert client.delete(f"/api/users/{user['id']}", headers=admin_headers).status_code == 204
    assert [u["name"] for u in client.get("/api/users/public").json()] == ["Admin"]
