from datetime import datetime
from email import message_from_bytes, policy
from email.message import EmailMessage

import pytest

from app import mailparse
from mails import BROKEN_MAIL, build_mail


def test_parses_plain_mail():
    mail = mailparse.parse(build_mail(cc="Papa <Papa@Example.ch>"))
    assert mail.message_id == "<m1@migros.ch>"
    assert mail.from_addr == "hr@migros.ch"
    assert mail.to_addrs == ["bewerbungen+abcd@example.ch", "papa@example.ch"]
    assert mail.subject == "Ihre Bewerbung"
    assert mail.body_text == "Guten Tag"
    assert mail.date == datetime(2026, 10, 15, 7, 30)
    assert mail.attachments == []


def test_decodes_umlauts_in_subject_and_filename():
    raw = build_mail(
        subject="Einladung zum Gespräch", attachments=[("Lebenslauf Müller.pdf", b"%PDF", "application/pdf")]
    )
    mail = mailparse.parse(raw)
    assert mail.subject == "Einladung zum Gespräch"
    assert [(a.filename, a.content_type, a.content) for a in mail.attachments] == [
        ("Lebenslauf Müller.pdf", "application/pdf", b"%PDF")
    ]


def test_html_only_mail_becomes_text():
    html = "<html><style>p{}</style><body><p>Guten&nbsp;Tag</p><p>Wir laden Sie <b>ein</b>.</p></body></html>"
    body = mailparse.parse(build_mail(body=None, html=html)).body_text
    assert "Guten" in body
    assert "Wir laden Sie ein." in body
    assert "<" not in body
    assert "p{}" not in body


def test_missing_or_invalid_date_is_none():
    assert mailparse.parse(build_mail(date=None)).date is None
    raw = build_mail(date=None).replace(b"Subject:", b"Date: gestern\nSubject:", 1)
    assert mailparse.parse(raw).date is None


def test_missing_message_id_uses_hash():
    raw = build_mail(message_id=None)
    assert mailparse.parse(raw).message_id == mailparse.fallback_message_id(raw)


def test_envelope_recipient_comes_first():
    mail = mailparse.parse(build_mail(to="hr@migros.ch"), envelope_to="Bewerbungen+ABCD@example.ch")
    assert mail.recipients[0] == "bewerbungen+abcd@example.ch"


def test_find_tag():
    assert mailparse.find_tag(["hr@migros.ch", "bewerbungen+abcd@example.ch"], {"abcd"}) == "abcd"
    assert mailparse.find_tag(["Bewerbungen+ABCD@example.ch"], {"abcd"}) == "abcd"
    assert mailparse.find_tag(["bewerbungen+zzzz@example.ch"], {"abcd"}) is None
    assert mailparse.find_tag(["bewerbungen@example.ch"], {"abcd"}) is None


def test_sender_domain():
    assert mailparse.sender_domain("hr@Migros.ch") == "migros.ch"
    assert mailparse.sender_domain("") == ""


def test_forwarded_mail_as_attachment():
    outer = EmailMessage()
    outer["From"] = "sohn@example.ch"
    outer["To"] = "bewerbungen+abcd@example.ch"
    outer["Subject"] = "Fwd: Original"
    outer.set_content("siehe Anhang")
    outer.add_attachment(message_from_bytes(build_mail(subject="Original"), policy=policy.default))
    mail = mailparse.parse(outer.as_bytes())
    assert mail.attachments[0].filename == "weitergeleitet.eml"
    assert b"Subject: Original" in mail.attachments[0].content


def test_broken_and_empty_mail_raise():
    with pytest.raises(mailparse.MailParseError):
        mailparse.parse(BROKEN_MAIL)
    with pytest.raises(mailparse.MailParseError):
        mailparse.parse(b"  \r\n")
