import hashlib
import mimetypes
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from html.parser import HTMLParser

from .timeutil import to_utc


class MailParseError(Exception):
    """The raw e-mail could not be read."""


@dataclass
class ParsedAttachment:
    filename: str
    content_type: str
    content: bytes


@dataclass
class ParsedMail:
    message_id: str
    from_addr: str
    to_addrs: list[str]
    recipients: list[str]  # envelope recipient first, then To/Cc/Delivered-To/X-Original-To
    subject: str
    body_text: str
    date: datetime | None  # naive UTC; None if missing or unreadable
    attachments: list[ParsedAttachment] = field(default_factory=list)
    html_links: list[str] = field(default_factory=list)  # hrefs of the HTML part, for suggestion mails


def fallback_message_id(raw: bytes) -> str:
    """A stable id for mails without Message-ID, so a second delivery is still recognised."""
    return f"<{hashlib.sha256(raw).hexdigest()}@family-job-tracking.local>"


def sender_domain(address: str) -> str:
    return address.rpartition("@")[2].lower() if "@" in address else ""


_TAG = re.compile(r"^[^@+\s]+\+([a-z0-9]+)@", re.IGNORECASE)


def find_tag(recipients: list[str], known_tags: set[str]) -> str | None:
    """The first +tag of a recipient address that belongs to an application."""
    for address in recipients:
        match = _TAG.match(address.strip().lower())
        if match and match.group(1) in known_tags:
            return match.group(1)
    return None


class _TextExtractor(HTMLParser):
    _BLOCKS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    lines = [re.sub(r"\s+", " ", line).strip() for line in "".join(parser.parts).splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


class _LinkCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href.strip())


def _html_links(msg: EmailMessage) -> list[str]:
    part = msg.get_body(preferencelist=("html",))
    if part is None:
        return []
    collector = _LinkCollector()
    collector.feed(part.get_content())
    collector.close()
    return collector.links


def _addresses(msg: EmailMessage, *headers: str) -> list[str]:
    values = [str(value) for header in headers for value in msg.get_all(header, [])]
    return [address.lower() for _name, address in getaddresses(values) if address]


def _date(msg: EmailMessage) -> datetime | None:
    try:
        value = msg.get("Date")
        if not value:
            return None
        parsed = parsedate_to_datetime(str(value))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return to_utc(parsed)


def _body(msg: EmailMessage) -> str:
    part = msg.get_body(preferencelist=("plain",))
    if part is not None:
        return part.get_content().strip()
    part = msg.get_body(preferencelist=("html",))
    if part is not None:
        return html_to_text(part.get_content())
    return ""


def _attachments(msg: EmailMessage) -> list[ParsedAttachment]:
    result = []
    for index, part in enumerate(msg.iter_attachments(), start=1):
        content_type = part.get_content_type()
        if content_type == "message/rfc822":
            # A mail forwarded "as attachment": keep it as an .eml file
            content = part.get_content().as_bytes()
            default_name = "weitergeleitet.eml"
        else:
            content = part.get_payload(decode=True) or b""
            default_name = f"anhang-{index}{mimetypes.guess_extension(content_type) or ''}"
        result.append(ParsedAttachment(part.get_filename() or default_name, content_type, content))
    return result


def parse(raw: bytes, envelope_to: str | None = None) -> ParsedMail:
    if not raw.strip():
        raise MailParseError("Leere Nachricht")
    try:
        msg = BytesParser(policy=policy.default).parsebytes(raw)
        to_addrs = _addresses(msg, "To", "Cc")
        envelope = [envelope_to.strip().lower()] if envelope_to else []
        return ParsedMail(
            message_id=str(msg.get("Message-ID", "")).strip() or fallback_message_id(raw),
            from_addr=parseaddr(str(msg.get("From", "")))[1].lower(),
            to_addrs=to_addrs,
            recipients=envelope + to_addrs + _addresses(msg, "Delivered-To", "X-Original-To"),
            subject=" ".join(str(msg.get("Subject", "")).split()),
            body_text=_body(msg),
            date=_date(msg),
            attachments=_attachments(msg),
            html_links=_html_links(msg),
        )
    except Exception as exc:
        raise MailParseError(f"{type(exc).__name__}: {exc}") from exc
