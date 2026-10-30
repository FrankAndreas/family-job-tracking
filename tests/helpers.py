ADMIN = "Admin"
ADMIN_PIN = "1234"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def login(client, name=ADMIN, pin=None) -> dict:
    """The (fake) hub's login of a person it lists, as the app gets it. `pin` is from before the hub and ignored."""
    import fake_hub

    headers = bearer(fake_hub.token(name))
    assert client.get("/api/me", headers=headers).status_code == 200
    return headers


def create_user(client, headers, name, pin=None, is_admin=False, **extra) -> dict:
    """A family member added in the (fake) hub with access to the app (a parent there is admin here), with the
    app's own settings (e-mail, reminders) set by an admin. `headers` and `pin` are from before the hub."""
    import fake_hub

    fake_hub.current.add(name, "PARENT" if is_admin else "CHILD")
    login(client, name)
    user = next(u for u in client.get("/api/users", headers=login(client)).json() if u["name"] == name)
    if extra:
        response = client.patch(f"/api/users/{user['id']}", json=extra, headers=login(client))
        assert response.status_code == 200, response.text
        user = response.json()
    return user


def remove_from_hub(name: str) -> None:
    """The hub no longer lists the person for the app; their data stays here, hidden."""
    import fake_hub

    fake_hub.current.remove_access(name)


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
