"""The title of a web page for a suggested link, without letting a link reach into the home network."""

import http.client
import ipaddress
import logging
import socket
import ssl
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5
MAX_BYTES = 1024 * 1024
MAX_REDIRECTS = 3
MAX_TITLE = 200
PORTS = {"http": 80, "https": 443}
REDIRECTS = {301, 302, 303, 307, 308}
USER_AGENT = "Mozilla/5.0 (compatible; FamilyJobTracking/1.0)"

# getaddrinfo has no timeout of its own: look up in a worker and stop waiting when time is up
_dns = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pagetitle-dns")


class Refused(Exception):
    """The link may not be fetched."""


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def _remaining(deadline: float) -> float:
    """Seconds left until the deadline of the whole fetch (time.monotonic())."""
    left = deadline - time.monotonic()
    if left <= 0:
        raise TimeoutError("Zeitlimit überschritten")
    return left


def _resolve(host: str, port: int, deadline: float) -> list[str]:
    lookup = _dns.submit(socket.getaddrinfo, host, port, type=socket.SOCK_STREAM)
    try:
        infos = lookup.result(timeout=_remaining(deadline))
    except FutureTimeout as exc:
        raise Refused(f"Keine Antwort für {host}") from exc
    except OSError as exc:
        raise Refused(f"Unbekannter Host: {host}") from exc
    return [info[4][0] for info in infos]


def _public_address(host: str, port: int, deadline: float) -> str:
    """The address to connect to; refused if any address of the host is not on the public internet."""
    addresses = _resolve(host, port, deadline)
    if not addresses or not all(_is_public(a) for a in addresses):
        raise Refused(f"{host} ist keine öffentliche Adresse")
    return addresses[0]


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """Connects to the checked address, so a second DNS answer can't point it elsewhere."""

    def __init__(self, host: str, ip: str, port: int, timeout: float):
        super().__init__(host, port, timeout=timeout)
        self._ip = ip

    def connect(self):
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, ip: str, port: int, timeout: float):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _request(
    scheme: str, host: str, ip: str, port: int, target: str, deadline: float
) -> tuple[int, str | None, str, bytes]:
    """One GET; every socket operation gets only the time left until the deadline, so a slow server can't stall."""
    connection_class = _PinnedHTTPSConnection if scheme == "https" else _PinnedHTTPConnection
    connection = connection_class(host, ip, port, _remaining(deadline))
    try:
        connection.request("GET", target, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
        sock = connection.sock  # the response reads from it even after http.client lets go of it
        sock.settimeout(_remaining(deadline))
        response = connection.getresponse()
        chunks: list[bytes] = []
        size = 0
        while size < MAX_BYTES:
            sock.settimeout(_remaining(deadline))
            chunk = response.read1(min(64 * 1024, MAX_BYTES - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        return response.status, response.getheader("Location"), response.getheader("Content-Type", ""), b"".join(chunks)
    finally:
        connection.close()


def _split(url: str) -> tuple[str, str, int, str]:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in PORTS or not parts.hostname:
        raise Refused("Nur http- und https-Links")
    port = parts.port or PORTS[scheme]
    if port != PORTS[scheme]:
        raise Refused("Nur die Standard-Ports 80 und 443")
    target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    return scheme, parts.hostname, port, target


def _charset(content_type: str) -> str:
    for param in content_type.split(";")[1:]:
        key, _, value = param.partition("=")
        if key.strip().lower() == "charset" and value.strip():
            return value.strip().strip('"')
    return "utf-8"


class _TitleParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.og_title: str | None = None
        self.title_parts: list[str] = []
        self._in_title = False
        self._title_done = False

    def handle_starttag(self, tag, attrs):
        values = {key.lower(): value or "" for key, value in attrs}
        kind = (values.get("property") or values.get("name") or "").lower()
        if tag == "meta" and kind == "og:title" and values.get("content") and self.og_title is None:
            self.og_title = values["content"]
        elif tag == "title" and not self._title_done:
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title" and self._in_title:
            self._in_title = False
            self._title_done = True

    def handle_data(self, data):
        if self._in_title:
            self.title_parts.append(data)


def extract_title(html: str) -> str | None:
    """og:title, else <title>; whitespace collapsed, at most MAX_TITLE characters."""
    parser = _TitleParser()
    parser.feed(html)
    title = parser.og_title or "".join(parser.title_parts)
    title = " ".join(title.split())[:MAX_TITLE]
    return title or None


def fetch_title(url: str) -> str | None:
    """The page's title, or None if it can't or may not be fetched."""
    deadline = time.monotonic() + TIMEOUT_SECONDS  # for the whole fetch, redirects included
    try:
        for _ in range(MAX_REDIRECTS + 1):
            scheme, host, port, target = _split(url)
            ip = _public_address(host, port, deadline)
            status, location, content_type, body = _request(scheme, host, ip, port, target, deadline)
            if status in REDIRECTS and location:
                url = urljoin(url, location)
                continue
            if status != 200 or "text/html" not in content_type.lower():
                return None
            try:
                text = body.decode(_charset(content_type), errors="replace")
            except LookupError:
                text = body.decode("utf-8", errors="replace")
            return extract_title(text)
        return None
    except Exception as exc:
        logger.info("No title for %s: %s", url, exc)
        return None
