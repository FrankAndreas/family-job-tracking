from email.message import EmailMessage

# Declares a charset Python doesn't know, so reading the body fails
BROKEN_MAIL = (
    b"From: hr@migros.ch\r\nSubject: kaputt\r\nMessage-ID: <broken@migros.ch>\r\n"
    b"Content-Type: text/plain; charset=x-unbekannt\r\nContent-Transfer-Encoding: base64\r\n\r\nSGFsbG8=\r\n"
)


def build_mail(
    *,
    subject="Ihre Bewerbung",
    sender="Personal <hr@migros.ch>",
    to="bewerbungen+abcd@example.ch",
    cc=None,
    body="Guten Tag",
    html=None,
    attachments=(),
    message_id="<m1@migros.ch>",
    date="Thu, 15 Oct 2026 09:30:00 +0200",
) -> bytes:
    """A raw e-mail as the Cloudflare worker would deliver it; attachments are (name, bytes, content type)."""
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    msg["Subject"] = subject
    if message_id:
        msg["Message-ID"] = message_id
    if date:
        msg["Date"] = date
    if body is not None:
        msg.set_content(body)
        if html:
            msg.add_alternative(html, subtype="html")
    else:
        msg.set_content(html or "", subtype="html")
    for name, content, content_type in attachments:
        maintype, subtype = content_type.split("/")
        msg.add_attachment(content, maintype=maintype, subtype=subtype, filename=name)
    return msg.as_bytes()


INBOUND_SECRET = "s3cret"


def post_mail(client, raw, envelope_to=None, secret=INBOUND_SECRET):
    headers = {"X-Inbound-Secret": secret, "Content-Type": "message/rfc822"}
    if envelope_to:
        headers["X-Envelope-To"] = envelope_to
    return client.post("/api/inbound", content=raw, headers=headers)
