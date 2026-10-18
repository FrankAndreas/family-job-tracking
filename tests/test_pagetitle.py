import pytest

from app import pagetitle
from helpers import create_application


@pytest.fixture
def web(monkeypatch):
    """A fake internet: hostname -> addresses, (host, target) -> response."""
    dns: dict[str, list[str]] = {"yousty.ch": ["8.8.8.8"]}
    pages: dict[tuple[str, str], tuple[int, str | None, str, bytes]] = {}
    requests: list[tuple[str, str, str, int, str]] = []

    def resolve(host, port, deadline):
        if host not in dns:
            raise pagetitle.Refused(f"Unbekannter Host: {host}")
        return dns[host]

    def request(scheme, host, ip, port, target, deadline):
        requests.append((scheme, host, ip, port, target))
        return pages.get((host, target), (404, None, "text/html", b""))

    monkeypatch.setattr(pagetitle, "_resolve", resolve)
    monkeypatch.setattr(pagetitle, "_request", request)
    return dns, pages, requests


def html(title_tags: str, charset="utf-8"):
    return (200, None, f"text/html; charset={charset}", f"<html><head>{title_tags}</head></html>".encode(charset))


def test_title_from_og_title_then_title(web):
    _dns, pages, requests = web
    pages[("yousty.ch", "/a")] = html('<title>Fallback</title><meta property="og:title" content="Lehrstelle &amp; Mehr">')
    pages[("yousty.ch", "/b?x=1")] = html("<title>\n  Informatiker   EFZ\n</title>")
    assert pagetitle.fetch_title("https://yousty.ch/a") == "Lehrstelle & Mehr"
    assert pagetitle.fetch_title("https://yousty.ch/b?x=1#frag") == "Informatiker EFZ"
    # Connects to the address it checked, with the hostname for TLS and the Host header
    assert requests[0] == ("https", "yousty.ch", "8.8.8.8", 443, "/a")


def test_title_in_latin1(web):
    _dns, pages, _requests = web
    pages[("yousty.ch", "/")] = html("<title>Bäcker/in EFZ, Zürich</title>", charset="iso-8859-1")
    assert pagetitle.fetch_title("http://yousty.ch") == "Bäcker/in EFZ, Zürich"


def test_title_is_cut_to_200_characters(web):
    _dns, pages, _requests = web
    pages[("yousty.ch", "/")] = html(f"<title>{'x' * 300}</title>")
    assert len(pagetitle.fetch_title("https://yousty.ch/")) == 200


@pytest.mark.parametrize(
    "url",
    ["ftp://yousty.ch/a", "https://yousty.ch:8443/a", "file:///etc/passwd", "https:///nohost"],
)
def test_refuses_other_schemes_and_ports(web, url):
    assert pagetitle.fetch_title(url) is None
    assert web[2] == []


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.0.0.5", "192.168.1.10", "172.16.0.1", "169.254.169.254", "100.64.0.1", "0.0.0.0",
     "::1", "fe80::1", "fd00::1", "::ffff:192.168.1.10", "224.0.0.1"],
)
def test_refuses_non_public_addresses(web, address):
    dns, pages, requests = web
    dns["nas.example.ch"] = ["8.8.8.8", address]  # one bad address is enough
    pages[("nas.example.ch", "/")] = html("<title>NAS</title>")
    assert pagetitle.fetch_title("https://nas.example.ch/") is None
    assert requests == []


def test_follows_redirects_to_public_hosts_only(web):
    dns, pages, requests = web
    dns["jobs.ch"] = ["8.8.4.4"]
    dns["intern.example.ch"] = ["192.168.1.10"]
    pages[("yousty.ch", "/short")] = (301, "https://jobs.ch/long", "text/html", b"")
    pages[("jobs.ch", "/long")] = html("<title>Koch EFZ</title>")
    assert pagetitle.fetch_title("https://yousty.ch/short") == "Koch EFZ"
    pages[("yousty.ch", "/evil")] = (302, "http://intern.example.ch/admin", "text/html", b"")
    assert pagetitle.fetch_title("https://yousty.ch/evil") is None
    assert ("http", "intern.example.ch", "192.168.1.10", 80, "/admin") not in requests


def test_gives_up_after_three_redirects(web):
    _dns, pages, requests = web
    for i in range(5):
        pages[("yousty.ch", f"/{i}")] = (302, f"/{i + 1}", "text/html", b"")
    pages[("yousty.ch", "/5")] = html("<title>Ende</title>")
    assert pagetitle.fetch_title("https://yousty.ch/0") is None
    assert len(requests) == 4


@pytest.mark.parametrize(
    "response",
    [(500, None, "text/html", b"<title>x</title>"), (200, None, "application/pdf", b"%PDF"), (200, None, "text/html", b"")],
)
def test_no_title_for_errors_and_other_content(web, response):
    web[1][("yousty.ch", "/")] = response
    assert pagetitle.fetch_title("https://yousty.ch/") is None


def test_network_errors_give_none(web, monkeypatch):
    def broken(*args):
        raise TimeoutError("timed out")

    monkeypatch.setattr(pagetitle, "_request", broken)
    assert pagetitle.fetch_title("https://yousty.ch/") is None


def test_check_endpoint(client, admin_headers, web):
    web[1][("yousty.ch", "/a")] = html("<title>Informatiker EFZ</title>")
    create_application(client, admin_headers, "Migros", posting_url="https://www.yousty.ch/a/")
    response = client.post("/api/suggestions/check", json={"url": "https://yousty.ch/a"}, headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Informatiker EFZ"
    assert [(d["kind"], d["label"]) for d in body["duplicates"]] == [("application", "Migros")]


def test_check_endpoint_refuses_non_links(client, admin_headers):
    assert client.post("/api/suggestions/check", json={"url": "yousty.ch"}, headers=admin_headers).status_code == 422


def test_a_slow_page_is_given_up_after_the_overall_timeout(monkeypatch):
    """A server that drips bytes slower than nothing but faster than the socket timeout must not hold the request."""
    import socket
    import threading
    import time

    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def drip():
        conn, _ = server.accept()
        conn.recv(4096)
        conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n<html><head><title>")
        for _ in range(30):
            time.sleep(0.2)
            try:
                conn.sendall(b"x")
            except OSError:
                break
        conn.close()

    threading.Thread(target=drip, daemon=True).start()
    monkeypatch.setattr(pagetitle, "TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(pagetitle, "PORTS", {"http": port, "https": 443})
    monkeypatch.setattr(pagetitle, "_public_address", lambda host, port, deadline: "127.0.0.1")
    start = time.monotonic()
    assert pagetitle.fetch_title(f"http://slow.example.ch:{port}/") is None
    assert time.monotonic() - start < 2.5
    server.close()


def test_a_hanging_dns_lookup_is_given_up(monkeypatch):
    import time

    monkeypatch.setattr(pagetitle, "TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(pagetitle.socket, "getaddrinfo", lambda *args, **kwargs: time.sleep(3) or [])
    start = time.monotonic()
    assert pagetitle.fetch_title("https://hangs.example.ch/") is None
    assert time.monotonic() - start < 2.5


def test_check_holds_no_database_connection_while_fetching(client, admin_headers, monkeypatch):
    from app import database

    seen = []
    monkeypatch.setattr(pagetitle, "fetch_title", lambda url: seen.append(database.engine.pool.checkedout()) or None)
    client.post("/api/suggestions/check", json={"url": "https://yousty.ch/a"}, headers=admin_headers)
    assert seen == [0]
