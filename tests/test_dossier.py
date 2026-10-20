import io

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from app import config, dossier, models


def pdf_bytes(pages=1, width=595, height=842, owner_password=None, user_password=None) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=width, height=height)
    if owner_password or user_password:
        writer.encrypt(user_password=user_password or "", owner_password=owner_password)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def image_bytes(size=(400, 300), fmt="PNG", color="red", exif_orientation=None) -> bytes:
    image = Image.new("RGB", size, color)
    buffer = io.BytesIO()
    kwargs = {}
    if exif_orientation:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation
        kwargs["exif"] = exif
    image.save(buffer, fmt, **kwargs)
    return buffer.getvalue()


def add(client, headers, name, content, content_type, category="report", **fields):
    response = client.post(
        "/api/documents",
        data={"category": category, **fields},
        files={"file": (name, content, content_type)},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def preview(client, headers):
    response = client.get("/api/documents/dossier", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_kind_by_type_and_extension():
    assert dossier.kind("application/pdf", "a.bin") == "pdf"
    assert dossier.kind("application/octet-stream", "IMG_0001.HEIC") == "image"
    assert dossier.kind("image/jpeg; charset=binary", "x") == "image"
    assert dossier.kind("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "cv.docx") is None


def test_image_page_is_a4_and_never_enlarged():
    page = dossier.image_page(image_bytes(size=(400, 300)))
    assert page.size == dossier.A4_PX
    bbox = Image.eval(page.convert("L"), lambda v: 255 - v).getbbox()  # where it isn't white
    assert (bbox[2] - bbox[0], bbox[3] - bbox[1]) == (400, 300)


def test_image_page_scales_large_photos_down():
    page = dossier.image_page(image_bytes(size=(4000, 3000), fmt="JPEG"))
    bbox = Image.eval(page.convert("L"), lambda v: 255 - v).getbbox()
    assert bbox[2] - bbox[0] == 1240  # landscape: limited by the page width


def test_image_page_applies_exif_orientation():
    # Stored landscape, EXIF says "rotate 90°": the page shows it in portrait
    page = dossier.image_page(image_bytes(size=(400, 200), fmt="JPEG", exif_orientation=6))
    bbox = Image.eval(page.convert("L"), lambda v: 255 - v).getbbox()
    assert bbox[3] - bbox[1] > bbox[2] - bbox[0]


def test_heic_photo_from_a_phone(client, admin_headers):
    import pillow_heif

    pillow_heif.register_heif_opener()
    buffer = io.BytesIO()
    Image.new("RGB", (300, 200), "blue").save(buffer, "HEIF")
    add(client, admin_headers, "IMG_0001.HEIC", buffer.getvalue(), "application/octet-stream", category="certificate")
    assert preview(client, admin_headers)["pages"] == 1


def test_dossier_order_pages_and_a4(client, admin_headers):
    report_old = add(client, admin_headers, "z1.pdf", pdf_bytes(2), "application/pdf", title="Zeugnis alt")
    report_new = add(client, admin_headers, "z2.pdf", pdf_bytes(1), "application/pdf", title="Zeugnis neu")
    cv = add(client, admin_headers, "cv.png", image_bytes(), "image/png", category="cv", title="Lebenslauf")
    letter = add(client, admin_headers, "m.pdf", pdf_bytes(1), "application/pdf", category="letter", title="Brief")
    info = preview(client, admin_headers)
    assert [p["id"] for p in info["parts"]] == [letter["id"], cv["id"], report_new["id"], report_old["id"]]
    assert [p["pages"] for p in info["parts"]] == [1, 1, 1, 2]
    assert info["pages"] == 5
    response = client.get("/api/documents/dossier.pdf", headers=admin_headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "Bewerbungsdossier_" in response.headers["content-disposition"]
    assert info["size"] == len(response.content)
    reader = PdfReader(io.BytesIO(response.content))
    assert len(reader.pages) == 5
    image_page = reader.pages[1]
    assert abs(float(image_page.mediabox.width) - 595.3) < 1 and abs(float(image_page.mediabox.height) - 841.9) < 1


def test_dossier_leaves_out_unticked_and_outdated(client, admin_headers):
    keep = add(client, admin_headers, "a.pdf", pdf_bytes(), "application/pdf")
    unticked = add(client, admin_headers, "b.pdf", pdf_bytes(), "application/pdf")
    old = add(client, admin_headers, "c.pdf", pdf_bytes(), "application/pdf")
    client.patch(f"/api/documents/{unticked['id']}", json={"in_dossier": False}, headers=admin_headers)
    client.patch(f"/api/documents/{old['id']}", json={"outdated": True}, headers=admin_headers)
    assert [p["id"] for p in preview(client, admin_headers)["parts"]] == [keep["id"]]


def test_dossier_skips_what_it_cannot_use(client, admin_headers, db):
    add(client, admin_headers, "ok.pdf", pdf_bytes(), "application/pdf", title="OK")
    word = add(client, admin_headers, "cv.docx", b"PK\x03\x04 word", "application/octet-stream", title="Word")
    client.patch(f"/api/documents/{word['id']}", json={"in_dossier": True}, headers=admin_headers)
    locked = add(client, admin_headers, "l.pdf", pdf_bytes(user_password="geheim"), "application/pdf", title="Gesperrt")
    broken = add(client, admin_headers, "x.pdf", b"%PDF-1.4 kaputt", "application/pdf", title="Kaputt")
    gone = add(client, admin_headers, "g.pdf", pdf_bytes(), "application/pdf", title="Weg")
    (config.files_dir() / db.get(models.Document, gone["id"]).path).unlink()
    info = preview(client, admin_headers)
    assert [p["title"] for p in info["parts"]] == ["OK"]
    reasons = {s["id"]: s["reason"] for s in info["skipped"]}
    assert "PDF" in reasons[word["id"]]
    assert reasons[locked["id"]] == "passwortgeschützt"
    assert reasons[broken["id"]] == "PDF nicht lesbar"
    assert reasons[gone["id"]] == "Datei fehlt"


def test_pdf_protected_only_against_editing_goes_in(client, admin_headers):
    add(client, admin_headers, "o.pdf", pdf_bytes(2, owner_password="owner"), "application/pdf")
    info = preview(client, admin_headers)
    assert (info["pages"], info["skipped"]) == (2, [])


def test_empty_dossier(client, admin_headers):
    assert preview(client, admin_headers) == {"parts": [], "skipped": [], "pages": 0, "size": 0}
    assert client.get("/api/documents/dossier.pdf", headers=admin_headers).status_code == 404


def test_dossier_needs_login(client):
    assert client.get("/api/documents/dossier.pdf").status_code == 401


def test_an_oversized_photo_is_skipped_and_the_rest_still_works(client, admin_headers, monkeypatch):
    # Pillow refuses images above 2 × MAX_IMAGE_PIXELS (a 200 MP phone photo) with DecompressionBombError
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)
    add(client, admin_headers, "ok.pdf", pdf_bytes(), "application/pdf", title="OK")
    big = add(client, admin_headers, "big.png", image_bytes(size=(400, 300)), "image/png", title="Riesig")
    info = preview(client, admin_headers)
    assert [p["title"] for p in info["parts"]] == ["OK"]
    assert info["skipped"][0]["id"] == big["id"]
    assert client.get("/api/documents/dossier.pdf", headers=admin_headers).status_code == 200


def test_a_pdf_failing_half_way_leaves_no_pages_behind(client, admin_headers, monkeypatch):
    add(client, admin_headers, "ok.pdf", pdf_bytes(1), "application/pdf", title="OK")
    add(client, admin_headers, "bad.pdf", pdf_bytes(3), "application/pdf", title="Halb")
    original = PdfWriter.append

    def append_then_fail(self, reader, *args, **kwargs):
        original(self, reader, *args, **kwargs)
        if len(reader.pages) == 3:
            raise IndexError("broken object")

    monkeypatch.setattr(PdfWriter, "append", append_then_fail)
    info = preview(client, admin_headers)
    assert [p["title"] for p in info["parts"]] == ["OK"]
    pdf = client.get("/api/documents/dossier.pdf", headers=admin_headers).content
    assert len(PdfReader(io.BytesIO(pdf)).pages) == info["pages"] == 1


def test_images_are_converted_once_while_unchanged(client, admin_headers, monkeypatch):
    add(client, admin_headers, "a.png", image_bytes(), "image/png")
    calls = []
    original = dossier.image_page
    monkeypatch.setattr(dossier, "image_page", lambda data: calls.append(1) or original(data))
    preview(client, admin_headers)
    preview(client, admin_headers)
    client.get("/api/documents/dossier.pdf", headers=admin_headers)
    assert len(calls) == 1
