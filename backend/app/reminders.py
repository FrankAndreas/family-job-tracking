import asyncio
import html
import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session, selectinload

from . import config, database, models, suggestions
from . import status as st
from .settings_store import get_settings
from .timeutil import local_date, to_local, to_utc, utcnow

logger = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"
CHECK_INTERVAL_SECONDS = 15 * 60

# (from, to, subject, text, html)
Sender = Callable[[str, list[str], str, str, str], None]


def is_configured() -> bool:
    return bool(config.env("RESEND_API_KEY") and config.env("MAIL_FROM"))


def resend_send(mail_from: str, to: list[str], subject: str, text: str, html_body: str) -> None:
    payload = json.dumps({"from": mail_from, "to": to, "subject": subject, "text": text, "html": html_body})
    request = urllib.request.Request(
        RESEND_URL,
        data=payload.encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {config.env('RESEND_API_KEY')}",
            "Content-Type": "application/json",
            # Resend sits behind Cloudflare, which rejects requests without a User-Agent
            "User-Agent": "family-job-tracking",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise RuntimeError(f"Resend {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Resend nicht erreichbar: {exc.reason}") from exc


@dataclass
class DueItem:
    id: int
    company: str
    position: str
    days: int


@dataclass
class SuggestionItem:
    id: int
    label: str
    deadline: date | None


@dataclass
class Digest:
    due: list[DueItem]
    inbox_count: int
    new_suggestions: list[SuggestionItem] = field(default_factory=list)
    deadline_soon: list[SuggestionItem] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.due and self.inbox_count == 0 and not self.new_suggestions and not self.deadline_soon


SOON_DAYS = 7


def _suggestion_lists(db: Session, since: datetime | None, today: date) -> tuple[list, list]:
    """Open suggestions created after the last reminder, and older ones whose deadline is within SOON_DAYS."""
    new, soon = [], []
    open_ones = (
        db.query(models.Suggestion)
        .filter(models.Suggestion.status == models.SuggestionStatus.OPEN.value)
        .order_by(models.Suggestion.created_at, models.Suggestion.id)
    )
    for s in open_ones:
        item = SuggestionItem(s.id, suggestions.label(s), s.deadline)
        if since is None or s.created_at > since:
            new.append(item)
        elif s.deadline and today <= s.deadline <= today + timedelta(days=SOON_DAYS):
            soon.append(item)
    soon.sort(key=lambda item: item.deadline)
    return new, soon


def build_digest(db: Session, now: datetime) -> Digest:
    settings = get_settings(db)
    applications = (
        db.query(models.Application)
        .options(selectinload(models.Application.events))
        .filter(models.Application.archived.is_(False))
        .all()
    )
    due = []
    for application in applications:
        status = st.derive_status(application.events)
        if st.is_due(status, application.archived, application.events, settings.followup_days, now):
            last = st.latest(application.events)
            due.append(
                DueItem(application.id, application.company, application.position, st.days_since(last.occurred_at, now))
            )
    due.sort(key=lambda item: item.days, reverse=True)
    inbox_count = (
        db.query(models.Email)
        .filter(models.Email.application_id.is_(None), models.Email.dismissed.is_(False))
        .count()
    )
    new, soon = _suggestion_lists(db, settings.last_reminder_sent_at, local_date(now))
    return Digest(due, inbox_count, new, soon)


def _plural(count: int, one: str, many: str) -> str:
    return one if count == 1 else many


def render(digest: Digest, app_url: str) -> tuple[str, str, str]:
    """(subject, plain text, HTML) of the reminder e-mail, in German."""
    base = app_url.rstrip("/")

    def link(path: str) -> str:
        return f"{base}{path}" if base else ""

    due_count = len(digest.due)
    new_count = len(digest.new_suggestions)
    if due_count:
        subject = f"Bewerbungen: {due_count} {_plural(due_count, 'Nachfrage', 'Nachfragen')} fällig"
    elif digest.deadline_soon:
        subject = "Bewerbungen: Frist läuft ab"
    elif new_count:
        subject = f"Bewerbungen: {new_count} {_plural(new_count, 'neuer Vorschlag', 'neue Vorschläge')}"
    elif digest.inbox_count:
        subject = f"Bewerbungen: {digest.inbox_count} {_plural(digest.inbox_count, 'Mail', 'Mails')} im Posteingang"
    else:
        subject = "Bewerbungen: nichts fällig"

    text_lines: list[str] = []
    html_parts: list[str] = []
    if digest.due:
        text_lines.append("Nachfragen fällig:")
        html_parts.append("<h2>Nachfragen fällig</h2><ul>")
        for item in digest.due:
            title = item.company + (f" – {item.position}" if item.position else "")
            age = f"{item.days} {_plural(item.days, 'Tag', 'Tage')} seit dem letzten Kontakt"
            url = link(f"/bewerbungen/{item.id}")
            text_lines.append(f"- {title} ({age})" + (f": {url}" if url else ""))
            label = html.escape(title)
            if url:
                html_parts.append(f'<li><a href="{html.escape(url)}">{label}</a> ({age})</li>')
            else:
                html_parts.append(f"<li>{label} ({age})</li>")
        text_lines.append("")
        html_parts.append("</ul>")
    if digest.new_suggestions or digest.deadline_soon:
        text_lines.append("Vorschläge:")
        html_parts.append("<h2>Vorschläge</h2>")
        for heading, items in (("Frist läuft bald ab", digest.deadline_soon), ("Neu", digest.new_suggestions)):
            if not items:
                continue
            text_lines.append(f"{heading}:")
            html_parts.append(f"<p>{heading}:</p><ul>")
            for item in items:
                deadline = f" (Frist {item.deadline.strftime('%d.%m.%Y')})" if item.deadline else ""
                text_lines.append(f"- {item.label}{deadline}")
                html_parts.append(f"<li>{html.escape(item.label)}{deadline}</li>")
            html_parts.append("</ul>")
        url = link("/vorschlaege")
        if url:
            text_lines.append(f"Zu den Vorschlägen: {url}")
            html_parts.append(f'<p><a href="{html.escape(url)}">Zu den Vorschlägen</a></p>')
        text_lines.append("")
    if digest.inbox_count:
        message = (
            f"{digest.inbox_count} {_plural(digest.inbox_count, 'Mail wartet', 'Mails warten')} "
            "im Posteingang auf die Zuordnung."
        )
        url = link("/posteingang")
        text_lines.append(message + (f" {url}" if url else ""))
        anchor = f' <a href="{html.escape(url)}">Zum Posteingang</a>' if url else ""
        html_parts.append(f"<p>{html.escape(message)}{anchor}</p>")
    if digest.empty:
        text_lines.append("Zurzeit ist nichts fällig.")
        html_parts.append("<p>Zurzeit ist nichts fällig.</p>")
    return subject, "\n".join(text_lines).strip() + "\n", "".join(html_parts)


def recipients(db: Session) -> list[str]:
    users = (
        db.query(models.User)
        .filter(models.User.wants_reminders.is_(True), models.User.email.isnot(None))
        .order_by(models.User.name)
        .all()
    )
    return [u.email for u in users]


def _reminder_time(settings: models.Settings) -> time:
    hours, minutes = settings.reminder_time.split(":")
    return time(int(hours), int(minutes))


def _is_due_today(settings: models.Settings, now: datetime) -> bool:
    local_now = to_local(now)
    already_done = settings.last_reminder_date == local_now.date().isoformat()
    return not already_done and local_now.time() >= _reminder_time(settings)


def next_run(settings: models.Settings, now: datetime) -> datetime:
    """When the next digest goes out (naive UTC); now, if today's is still pending."""
    if _is_due_today(settings, now):
        return now
    local_now = to_local(now)
    day = local_now.date()
    if settings.last_reminder_date == day.isoformat():
        day += timedelta(days=1)
    return to_utc(datetime.combine(day, _reminder_time(settings), tzinfo=config.tz()))


def run_once(db: Session, now: datetime, send: Sender | None = None) -> str:
    """Send today's digest if it is time and it has not been sent yet."""
    if not is_configured():
        return "not_configured"
    settings = get_settings(db)
    if not _is_due_today(settings, now):
        return "not_due"
    today = to_local(now).date().isoformat()
    digest = build_digest(db, now)
    to = recipients(db)
    if digest.empty or not to:
        settings.last_reminder_date = today
        db.commit()
        return "empty" if digest.empty else "no_recipients"
    subject, text, html_body = render(digest, config.env("APP_URL"))
    settings.last_reminder_attempt_at = now
    try:
        (send or resend_send)(config.env("MAIL_FROM"), to, subject, text, html_body)
    except Exception as exc:
        logger.error("Sending the reminder failed: %s", exc)
        settings.last_reminder_error = str(exc)[:500]
        db.commit()
        return "error"
    settings.last_reminder_date = today
    settings.last_reminder_sent_at = now
    settings.last_reminder_error = None
    db.commit()
    return "sent"


def send_test(db: Session, user: models.User, now: datetime, send: Sender | None = None) -> None:
    """Send the current digest to one user right away (Einstellungen > Test-Erinnerung)."""
    if not is_configured():
        raise ValueError("Erinnerungen sind nicht konfiguriert (RESEND_API_KEY und MAIL_FROM fehlen)")
    if not user.email:
        raise ValueError("Bitte zuerst eine E-Mail-Adresse speichern")
    subject, text, html_body = render(build_digest(db, now), config.env("APP_URL"))
    settings = get_settings(db)
    settings.last_reminder_attempt_at = now
    try:
        (send or resend_send)(config.env("MAIL_FROM"), [user.email], f"[Test] {subject}", text, html_body)
    except Exception as exc:
        settings.last_reminder_error = str(exc)[:500]
        db.commit()
        raise
    settings.last_reminder_sent_at = now
    settings.last_reminder_error = None
    db.commit()


def _tick() -> None:
    with database.SessionLocal() as db:
        result = run_once(db, utcnow())
    if result == "sent":
        logger.info("Sent the daily reminder")


async def loop() -> None:
    """Background task: check every 15 minutes whether the daily digest is due."""
    while True:
        try:
            await asyncio.to_thread(_tick)
        except Exception:
            logger.exception("Reminder check failed")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
