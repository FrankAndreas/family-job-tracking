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


def create_application(client, headers, company="Migros", **fields) -> dict:
    response = client.post("/api/applications", json={"company": company, **fields}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def add_event(
    client, headers, application_id, event_type="sent", occurred_at="2026-10-01T10:00:00+02:00", note="", files=None
) -> dict:
    response = client.post(
        f"/api/applications/{application_id}/events",
        data={"type": event_type, "occurred_at": occurred_at, "note": note},
        files=files,
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()
