"""Suggestions: links to open apprenticeships, their duplicates and the links in e-mails."""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.orm import Session

from . import models
from .timeutil import iso

# bewerbungen+vorschlag@<domain>; application tags never contain an "o", so this can't clash
SUGGESTION_TAG = "vorschlag"
MAX_MAIL_LINKS = 10

_TRACKING_PARAMS = {"fbclid", "gclid"}
_LINK = re.compile(r"https?://[^\s<>\"'()\[\]]+", re.IGNORECASE)
_FORWARD_PREFIX = re.compile(r"^\s*((fwd?|wg)\s*:\s*)+", re.IGNORECASE)


def normalize_url(url: str) -> str:
    """The form of a link used to find duplicates: no www., fragment, tracking parameters or trailing slash."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    try:
        port = parts.port
    except ValueError:
        port = None
    netloc = f"{host}:{port}" if port else host
    query = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_PARAMS
    )
    if not netloc:
        # Not a link (an application's posting_url may be free text): compare it as text
        return " ".join(url.split()).lower()
    return urlunsplit((parts.scheme.lower(), netloc, parts.path.rstrip("/"), urlencode(query), ""))


def label(s: models.Suggestion) -> str:
    """"Company – position", either one alone, or the link's host if both are empty."""
    text = " – ".join(part for part in (s.company, s.position) if part)
    if text:
        return text
    host = (urlsplit(s.url).hostname or s.url).lower()
    return host[4:] if host.startswith("www.") else host


def find_duplicates(db: Session, url: str, exclude_id: int | None = None) -> list[dict]:
    """Earlier suggestions and applications with the same normalised link."""
    key = normalize_url(url)
    found = [
        {"kind": "suggestion", "id": s.id, "label": label(s), "date": iso(s.created_at), "status": s.status}
        for s in db.query(models.Suggestion)
        .filter(models.Suggestion.url_key == key)
        .order_by(models.Suggestion.created_at, models.Suggestion.id)
        if s.id != exclude_id
    ]
    applications = db.query(models.Application).filter(models.Application.posting_url != "").order_by(
        models.Application.created_at, models.Application.id
    )
    for a in applications:
        if normalize_url(a.posting_url) == key:
            title = a.company + (f" – {a.position}" if a.position else "")
            found.append({"kind": "application", "id": a.id, "label": title, "date": iso(a.created_at)})
    return found


def extract_links(*texts: str) -> list[str]:
    """The http(s) links in the texts, in order, without repeats; trailing punctuation is not part of a link."""
    links: list[str] = []
    for text in texts:
        for match in _LINK.findall(text or ""):
            link = match.rstrip(".,;:!?")
            if link not in links:
                links.append(link)
    return links


def clean_subject(subject: str) -> str:
    """A forwarded mail's subject without "Fwd:", "Fw:" or "WG:"."""
    return _FORWARD_PREFIX.sub("", subject).strip()
