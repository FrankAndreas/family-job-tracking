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
