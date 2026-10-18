import pytest

from app import models, suggestions
from helpers import create_user, login
from mails import INBOUND_SECRET, build_mail, post_mail


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.Yousty.ch/de-CH/lehrstellen/123/", "https://yousty.ch/de-CH/lehrstellen/123"),
        ("HTTPS://jobs.ch/a?b=2&a=1#top", "https://jobs.ch/a?a=1&b=2"),
        ("https://jobs.ch/a?utm_source=x&id=7&fbclid=y&gclid=z", "https://jobs.ch/a?id=7"),
        ("  https://jobs.ch/a  ", "https://jobs.ch/a"),
        ("Inserat auf Papier", "inserat auf papier"),
    ],
)
def test_normalize_url(url, expected):
    assert suggestions.normalize_url(url) == expected


def add_suggestion(db, url, **fields):
    s = models.Suggestion(url=url, url_key=suggestions.normalize_url(url), **fields)
    db.add(s)
    db.commit()
    return s


def test_label_falls_back_to_host(db):
    assert suggestions.label(add_suggestion(db, "https://www.yousty.ch/x")) == "yousty.ch"
    s = add_suggestion(db, "https://jobs.ch/y", company="Migros", position="Informatiker")
    assert suggestions.label(s) == "Migros – Informatiker"


def test_find_duplicates_in_suggestions_and_applications(db):
    first = add_suggestion(db, "https://www.yousty.ch/x?utm_source=mail", company="Migros")
    db.add(models.Application(company="Coop", posting_url="https://yousty.ch/x/", mail_tag="abcd"))
    db.add(models.Application(company="Lidl", posting_url="Inserat auf Papier", mail_tag="efgh"))
    db.commit()
    found = suggestions.find_duplicates(db, "https://yousty.ch/x")
    assert [(d["kind"], d["label"]) for d in found] == [("suggestion", "Migros"), ("application", "Coop")]
    assert found[0]["status"] == "open"
    assert suggestions.find_duplicates(db, "https://yousty.ch/x", exclude_id=first.id)[0]["kind"] == "application"


def test_extract_links():
    text = "Schau mal: https://yousty.ch/a. Und (https://jobs.ch/b?x=1), nochmals https://yousty.ch/a"
    html_links = ["https://jobs.ch/b?x=1", "mailto:hr@migros.ch", "https://migros.ch/c"]
    assert suggestions.extract_links(text, *html_links) == [
        "https://yousty.ch/a",
        "https://jobs.ch/b?x=1",
        "https://migros.ch/c",
    ]


@pytest.mark.parametrize(
    "subject, expected",
    [("Fwd: Lehrstelle Informatiker", "Lehrstelle Informatiker"), ("WG: Fw: FWD:  Koch", "Koch"), ("Koch", "Koch")],
)
def test_clean_subject(subject, expected):
    assert suggestions.clean_subject(subject) == expected


def post_suggestion(client, headers, url="https://yousty.ch/lehrstellen/1", **fields):
    response = client.post("/api/suggestions", json={"url": url, **fields}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_suggestions_need_login(client):
    assert client.get("/api/suggestions").status_code == 401


def test_create_and_list(client, admin_headers):
    created = post_suggestion(
        client, admin_headers, " https://yousty.ch/lehrstellen/1 ", company="Migros", deadline="2026-11-01", note="nah"
    )
    assert created["url"] == "https://yousty.ch/lehrstellen/1"
    assert created["status"] == "open"
    assert created["source"] == "app"
    assert created["created_by_name"] == "Admin"
    assert created["deadline"] == "2026-11-01"
    assert client.get("/api/suggestions", headers=admin_headers).json()[0]["id"] == created["id"]


@pytest.mark.parametrize("url", ["www.yousty.ch/x", "ftp://yousty.ch/x", "javascript:alert(1)", "", "https://" + "a" * 500])
def test_create_refuses_other_links(client, admin_headers, url):
    assert client.post("/api/suggestions", json={"url": url}, headers=admin_headers).status_code == 422


def test_patch_and_clear_deadline(client, admin_headers):
    s = post_suggestion(client, admin_headers, deadline="2026-11-01")
    response = client.patch(
        f"/api/suggestions/{s['id']}", json={"company": "Coop", "deadline": None}, headers=admin_headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["company"] == "Coop"
    assert response.json()["deadline"] is None


def test_patch_url_updates_duplicate_key(client, admin_headers, db):
    s = post_suggestion(client, admin_headers)
    client.patch(f"/api/suggestions/{s['id']}", json={"url": "https://www.jobs.ch/z/"}, headers=admin_headers)
    assert db.get(models.Suggestion, s["id"]).url_key == "https://jobs.ch/z"


def test_delete(client, admin_headers):
    s = post_suggestion(client, admin_headers)
    assert client.delete(f"/api/suggestions/{s['id']}", headers=admin_headers).status_code == 204
    assert client.get("/api/suggestions", headers=admin_headers).json() == []


def test_apply_creates_application(client, admin_headers):
    sohn = create_user(client, admin_headers, "Sohn")
    s = post_suggestion(client, admin_headers, company="Migros", position="Informatiker", location="Bern", note="toll")
    sohn_headers = login(client, "Sohn", "5678")
    response = client.post(f"/api/suggestions/{s['id']}/apply", json={}, headers=sohn_headers)
    assert response.status_code == 201, response.text
    application = client.get(f"/api/applications/{response.json()['application_id']}", headers=admin_headers).json()
    assert (application["company"], application["position"], application["location"]) == ("Migros", "Informatiker", "Bern")
    assert application["posting_url"] == s["url"]
    assert application["notes"] == "toll"
    after = client.get("/api/suggestions", headers=admin_headers).json()[0]
    assert after["status"] == "applied"
    assert after["decided_by_name"] == sohn["name"]
    assert after["application"]["id"] == application["id"]


def test_apply_needs_a_company(client, admin_headers):
    s = post_suggestion(client, admin_headers)
    assert client.post(f"/api/suggestions/{s['id']}/apply", json={}, headers=admin_headers).status_code == 422
    response = client.post(f"/api/suggestions/{s['id']}/apply", json={"company": " Coop "}, headers=admin_headers)
    assert response.status_code == 201
    assert client.get("/api/suggestions", headers=admin_headers).json()[0]["company"] == "Coop"


def test_apply_twice_is_409_and_creates_one_application(client, admin_headers):
    s = post_suggestion(client, admin_headers, company="Migros")
    assert client.post(f"/api/suggestions/{s['id']}/apply", json={}, headers=admin_headers).status_code == 201
    assert client.post(f"/api/suggestions/{s['id']}/apply", json={}, headers=admin_headers).status_code == 409
    assert len(client.get("/api/applications", headers=admin_headers).json()) == 1


def test_decline_and_reopen(client, admin_headers):
    s = post_suggestion(client, admin_headers)
    response = client.post(f"/api/suggestions/{s['id']}/decline", json={"reason": "zu weit"}, headers=admin_headers)
    assert response.json()["status"] == "declined"
    assert response.json()["decline_reason"] == "zu weit"
    assert client.post(f"/api/suggestions/{s['id']}/decline", json={}, headers=admin_headers).status_code == 409
    reopened = client.post(f"/api/suggestions/{s['id']}/reopen", headers=admin_headers).json()
    assert (reopened["status"], reopened["decline_reason"], reopened["decided_by_name"]) == ("open", "", None)
    assert client.post(f"/api/suggestions/{s['id']}/reopen", headers=admin_headers).status_code == 409


def test_reopen_keeps_the_application(client, admin_headers):
    s = post_suggestion(client, admin_headers, company="Migros")
    client.post(f"/api/suggestions/{s['id']}/apply", json={}, headers=admin_headers)
    reopened = client.post(f"/api/suggestions/{s['id']}/reopen", headers=admin_headers).json()
    assert reopened["application"] is None
    assert len(client.get("/api/applications", headers=admin_headers).json()) == 1


def test_deleted_application_leaves_the_suggestion_applied(client, admin_headers):
    s = post_suggestion(client, admin_headers, company="Migros")
    app_id = client.post(f"/api/suggestions/{s['id']}/apply", json={}, headers=admin_headers).json()["application_id"]
    assert client.delete(f"/api/applications/{app_id}", headers=admin_headers).status_code == 204
    after = client.get("/api/suggestions", headers=admin_headers).json()[0]
    assert (after["status"], after["application"]) == ("applied", None)


def test_deadline_passed(client, admin_headers):
    s = post_suggestion(client, admin_headers, deadline="2020-01-01")
    assert s["deadline_passed"] is True
    assert post_suggestion(client, admin_headers, "https://jobs.ch/2", deadline="2099-01-01")["deadline_passed"] is False


def test_unknown_suggestion_is_404(client, admin_headers):
    assert client.post("/api/suggestions/99/decline", json={}, headers=admin_headers).status_code == 404


def test_dashboard_counts_open_suggestions(client, admin_headers):
    post_suggestion(client, admin_headers, "https://jobs.ch/1")
    declined = post_suggestion(client, admin_headers, "https://jobs.ch/2")
    client.post(f"/api/suggestions/{declined['id']}/decline", json={}, headers=admin_headers)
    assert client.get("/api/dashboard", headers=admin_headers).json()["suggestion_count"] == 1


SUGGESTION_ADDRESS = "bewerbungen+vorschlag@example.ch"


@pytest.fixture
def inbound(monkeypatch):
    monkeypatch.setenv("INBOUND_SECRET", INBOUND_SECRET)


def test_mail_from_a_user_creates_suggestions(client, admin_headers, inbound, db):
    create_user(client, admin_headers, "Papa", email="papa@example.ch")
    raw = build_mail(
        sender="Papa <papa@example.ch>",
        to=SUGGESTION_ADDRESS,
        subject="Fwd: Lehrstelle Informatiker EFZ",
        body="Schau mal https://www.yousty.ch/x?utm_source=share",
    )
    response = post_mail(client, raw)
    assert response.json()["status"] == "suggestions"
    s = db.query(models.Suggestion).one()
    assert (s.url, s.position, s.source) == ("https://www.yousty.ch/x?utm_source=share", "Lehrstelle Informatiker EFZ", "mail")
    assert s.creator.name == "Papa"
    assert db.query(models.Email).count() == 0


def test_mail_with_several_links_and_duplicates(client, admin_headers, inbound, db):
    create_user(client, admin_headers, "Papa", email="papa@example.ch")
    post_suggestion(client, admin_headers, "https://jobs.ch/1")
    links = " ".join(f"https://yousty.ch/{i}" for i in range(12))
    raw = build_mail(sender="papa@example.ch", to=SUGGESTION_ADDRESS, subject="Ideen", body=f"https://jobs.ch/1/ {links}")
    ids = post_mail(client, raw).json()["suggestion_ids"]
    assert len(ids) == 9  # 10 links read, the first is a duplicate
    new = db.query(models.Suggestion).filter(models.Suggestion.source == "mail").all()
    assert all(s.position == "" for s in new)  # several links: the subject says nothing about each


def test_html_only_mail_uses_the_links_behind_the_text(client, admin_headers, inbound, db):
    create_user(client, admin_headers, "Papa", email="papa@example.ch")
    raw = build_mail(
        sender="papa@example.ch",
        to=SUGGESTION_ADDRESS,
        body=None,
        html='<p><a href="https://www.yousty.ch/lehrstelle/42">Lehrstelle ansehen</a></p>',
    )
    assert post_mail(client, raw).json()["status"] == "suggestions"
    assert db.query(models.Suggestion).one().url == "https://www.yousty.ch/lehrstelle/42"


def test_bcc_to_the_suggestion_address_counts(client, admin_headers, inbound, db):
    create_user(client, admin_headers, "Papa", email="papa@example.ch")
    raw = build_mail(sender="papa@example.ch", to="sohn@example.ch", body="https://yousty.ch/a")
    assert post_mail(client, raw, envelope_to=SUGGESTION_ADDRESS).json()["status"] == "suggestions"


@pytest.mark.parametrize(
    "sender, body",
    [("fremd@spam.example", "https://yousty.ch/a"), ("papa@example.ch", "Keine Links hier")],
)
def test_other_suggestion_mails_land_in_the_inbox(client, admin_headers, inbound, db, sender, body):
    create_user(client, admin_headers, "Papa", email="papa@example.ch")
    response = post_mail(client, build_mail(sender=sender, to=SUGGESTION_ADDRESS, body=body))
    assert response.json()["status"] == "stored"
    assert response.json()["application_id"] is None
    assert db.query(models.Suggestion).count() == 0
    assert db.query(models.Email).count() == 1
