import json
from datetime import date, datetime, timedelta

import pytest

from app import models, reminders, suggestions
from app.settings_store import get_settings
from app.timeutil import to_utc


def local(*args):
    """A local (Zurich) wall-clock time as stored naive UTC."""
    return to_utc(datetime(*args))


MORNING = local(2026, 10, 15, 6, 0)
AFTER = local(2026, 10, 15, 7, 5)


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("MAIL_FROM", "Bewerbungen <bewerbungen@example.ch>")
    monkeypatch.setenv("APP_URL", "https://bewerbungen.example.ch")


class Outbox:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    def __call__(self, mail_from, to, subject, text, html):
        if self.fail:
            raise RuntimeError("Resend 422: invalid from")
        self.sent.append({"from": mail_from, "to": to, "subject": subject, "text": text, "html": html})


def add_application(db, company, days_ago, event_type="sent", archived=False):
    application = models.Application(company=company, mail_tag=company[:4].lower(), archived=archived)
    application.events.append(models.Event(type=event_type, occurred_at=AFTER - timedelta(days=days_ago)))
    db.add(application)
    db.commit()
    return application


def add_user(db, name, email, wants=True):
    db.add(models.User(name=name, email=email, wants_reminders=wants))
    db.commit()


def test_build_digest(db):
    add_application(db, "Migros", 15)
    add_application(db, "Coop", 3)
    add_application(db, "Lidl", 30, archived=True)
    add_application(db, "Aldi", 30, event_type="rejection")
    db.add(models.Email(message_id="<x@y>", received_at=AFTER))
    db.commit()
    digest = reminders.build_digest(db, AFTER)
    assert [(d.company, d.days) for d in digest.due] == [("Migros", 15)]
    assert digest.inbox_count == 1
    assert not digest.empty


def test_render_with_and_without_links(db):
    application = add_application(db, "Migros", 15)
    digest = reminders.build_digest(db, AFTER)
    subject, text, html = reminders.render(digest, "https://bewerbungen.example.ch/")
    assert subject == "Bewerbungen: 1 Nachfrage fällig"
    url = f"https://bewerbungen.example.ch/bewerbungen/{application.id}"
    assert url in text
    assert url in html
    assert "15 Tage seit dem letzten Kontakt" in text
    _, text_without_links, _ = reminders.render(digest, "")
    assert "http" not in text_without_links


def test_run_once_not_configured(db):
    assert reminders.run_once(db, AFTER, send=Outbox()) == "not_configured"


def test_run_once_sends_once_per_day(db, configured):
    add_user(db, "Papa", "papa@example.ch")
    add_user(db, "Sohn", "sohn@example.ch")
    add_user(db, "Mama", "mama@example.ch", wants=False)
    add_application(db, "Migros", 15)
    outbox = Outbox()
    assert reminders.run_once(db, MORNING, send=outbox) == "not_due"
    assert reminders.run_once(db, AFTER, send=outbox) == "sent"
    assert outbox.sent[0]["to"] == ["papa@example.ch", "sohn@example.ch"]
    assert outbox.sent[0]["from"] == "Bewerbungen <bewerbungen@example.ch>"
    assert reminders.run_once(db, AFTER + timedelta(hours=1), send=outbox) == "not_due"
    assert len(outbox.sent) == 1
    settings = get_settings(db)
    assert settings.last_reminder_date == "2026-10-15"
    assert settings.last_reminder_sent_at == AFTER


def test_empty_digest_sends_nothing(db, configured):
    add_user(db, "Papa", "papa@example.ch")
    outbox = Outbox()
    assert reminders.run_once(db, AFTER, send=outbox) == "empty"
    assert outbox.sent == []
    assert get_settings(db).last_reminder_date == "2026-10-15"


def test_no_recipients(db, configured):
    add_application(db, "Migros", 15)
    assert reminders.run_once(db, AFTER, send=Outbox()) == "no_recipients"


def test_failure_is_recorded_and_retried(db, configured):
    add_user(db, "Papa", "papa@example.ch")
    add_application(db, "Migros", 15)
    assert reminders.run_once(db, AFTER, send=Outbox(fail=True)) == "error"
    settings = get_settings(db)
    assert "Resend 422" in settings.last_reminder_error
    assert settings.last_reminder_date is None
    assert settings.last_reminder_attempt_at == AFTER

    assert reminders.run_once(db, AFTER + timedelta(minutes=15), send=Outbox()) == "sent"
    assert get_settings(db).last_reminder_error is None


def test_next_run(db, configured):
    settings = get_settings(db)
    assert reminders.next_run(settings, MORNING) == local(2026, 10, 15, 7, 0)
    settings.last_reminder_date = "2026-10-15"
    assert reminders.next_run(settings, AFTER) == local(2026, 10, 16, 7, 0)


def test_send_test_requires_email(db, configured):
    admin = db.query(models.User).filter_by(name="Admin").one()
    with pytest.raises(ValueError):
        reminders.send_test(db, admin, AFTER, send=Outbox())
    admin.email = "papa@example.ch"
    db.commit()
    outbox = Outbox()
    reminders.send_test(db, admin, AFTER, send=outbox)
    assert outbox.sent[0]["subject"].startswith("[Test] ")
    assert outbox.sent[0]["to"] == ["papa@example.ch"]


def test_resend_send_posts_json(monkeypatch, configured):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"id": "1"}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data)
        return FakeResponse()

    monkeypatch.setattr(reminders.urllib.request, "urlopen", fake_urlopen)
    reminders.resend_send("a@example.ch", ["b@example.ch"], "Betreff", "Text", "<p>Text</p>")
    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["headers"]["Authorization"] == "Bearer re_test"
    assert captured["body"] == {
        "from": "a@example.ch",
        "to": ["b@example.ch"],
        "subject": "Betreff",
        "text": "Text",
        "html": "<p>Text</p>",
    }


def add_suggestion(db, url, created_at, deadline=None, status="open", company=""):
    db.add(
        models.Suggestion(
            url=url, url_key=suggestions.normalize_url(url), created_at=created_at, deadline=deadline,
            status=status, company=company,
        )
    )
    db.commit()


def test_digest_lists_new_and_soon_due_suggestions(db):
    settings = get_settings(db)
    settings.last_reminder_sent_at = AFTER - timedelta(days=1)
    db.commit()
    add_suggestion(db, "https://jobs.ch/new", AFTER - timedelta(hours=2), company="Neu AG")
    add_suggestion(db, "https://jobs.ch/old-soon", AFTER - timedelta(days=5), deadline=date(2026, 10, 20))
    add_suggestion(db, "https://jobs.ch/old-later", AFTER - timedelta(days=5), deadline=date(2026, 10, 30))
    add_suggestion(db, "https://jobs.ch/old-passed", AFTER - timedelta(days=5), deadline=date(2026, 10, 14))
    add_suggestion(db, "https://jobs.ch/declined", AFTER - timedelta(hours=2), status="declined")
    digest = reminders.build_digest(db, AFTER)
    assert [s.label for s in digest.new_suggestions] == ["Neu AG"]
    assert [s.label for s in digest.deadline_soon] == ["jobs.ch"]
    assert digest.deadline_soon[0].deadline == date(2026, 10, 20)
    assert not digest.empty


def test_all_open_suggestions_are_new_before_the_first_reminder(db):
    add_suggestion(db, "https://jobs.ch/a", AFTER - timedelta(days=30))
    assert len(reminders.build_digest(db, AFTER).new_suggestions) == 1


def test_old_suggestions_without_near_deadline_send_nothing(db):
    settings = get_settings(db)
    settings.last_reminder_sent_at = AFTER - timedelta(days=1)
    db.commit()
    add_suggestion(db, "https://jobs.ch/a", AFTER - timedelta(days=5))
    assert reminders.build_digest(db, AFTER).empty


def test_render_suggestions_and_subject_priority():
    soon = reminders.SuggestionItem(1, "Migros – Koch", date(2026, 10, 20))
    new = reminders.SuggestionItem(2, "jobs.ch", None)
    subject, text, html_body = reminders.render(
        reminders.Digest(due=[], inbox_count=1, new_suggestions=[new], deadline_soon=[soon]), "https://app.example.ch"
    )
    assert subject == "Bewerbungen: Frist läuft ab"
    assert "Migros – Koch (Frist 20.10.2026)" in text
    assert "jobs.ch" in text
    assert "https://app.example.ch/vorschlaege" in text
    assert "Vorschläge" in html_body
    subject, _text, _html = reminders.render(
        reminders.Digest(due=[], inbox_count=1, new_suggestions=[new, new]), ""
    )
    assert subject == "Bewerbungen: 2 neue Vorschläge"
    subject, _text, _html = reminders.render(reminders.Digest(due=[], inbox_count=0, new_suggestions=[new]), "")
    assert subject == "Bewerbungen: 1 neuer Vorschlag"
