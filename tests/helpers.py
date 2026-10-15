ADMIN = "Admin"
ADMIN_PIN = "1234"


def login(client, name=ADMIN, pin=ADMIN_PIN) -> dict:
    response = client.post("/api/token", json={"name": name, "pin": pin})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_user(client, headers, name, pin="5678", **extra) -> dict:
    response = client.post("/api/users", json={"name": name, "pin": pin, **extra}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()
