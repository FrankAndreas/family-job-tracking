"""The application dossier: the son's documents as one PDF, in the usual order."""

import io
import logging
import os
from dataclasses import dataclass, field

import pillow_heif
from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

from . import files as filestore
from . import models

logger = logging.getLogger(__name__)
pillow_heif.register_heif_opener()  # HEIC photos from iPhones

PDF_TYPES = {"application/pdf"}
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}

A4_PX = (1240, 1754)  # A4 at 150 dpi: sharp enough to read, small enough to send by e-mail
DPI = 150
JPEG_QUALITY = 80


def kind(content_type: str, filename: str) -> str | None:
    """"pdf", "image", or None if it can't go into the dossier; by type, else by extension (phones send HEIC as
    application/octet-stream)."""
    content_type = (content_type or "").split(";")[0].strip().lower()
    ext = os.path.splitext(filename or "")[1].lower()
    if content_type in PDF_TYPES or ext in PDF_EXTENSIONS:
        return "pdf"
    if content_type in IMAGE_TYPES or ext in IMAGE_EXTENSIONS:
        return "image"
    return None


def image_page(data: bytes) -> Image.Image:
    """A white A4 page with the image upright, fitted (never enlarged) and centred."""
    with Image.open(io.BytesIO(data)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    image.thumbnail(A4_PX)
    page = Image.new("RGB", A4_PX, "white")
    page.paste(image, ((A4_PX[0] - image.width) // 2, (A4_PX[1] - image.height) // 2))
    return page


def _image_pdf(data: bytes) -> PdfReader:
    buffer = io.BytesIO()
    image_page(data).save(buffer, "PDF", resolution=DPI, quality=JPEG_QUALITY)
    return PdfReader(io.BytesIO(buffer.getvalue()))


def _pdf(data: bytes) -> PdfReader:
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted and not reader.decrypt(""):
        raise PermissionError
    len(reader.pages)  # reading the page tree finds most broken files here
    return reader


@dataclass
class Dossier:
    pdf: bytes | None
    parts: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    pages: int = 0


def build(documents: list[models.Document]) -> Dossier:
    """One PDF from the documents marked for the dossier, in the given order; the others are reported."""
    writer = PdfWriter()
    result = Dossier(pdf=None)
    for d in documents:
        if not d.in_dossier:
            continue
        what = kind(d.content_type, d.filename)
        skip = None
        if what is None:
            skip = "kein PDF oder Bild – bitte als PDF hochladen"
        elif not filestore.absolute(d.path).exists():
            skip = "Datei fehlt"
        if skip is None:
            data = filestore.absolute(d.path).read_bytes()
            try:
                reader = _pdf(data) if what == "pdf" else _image_pdf(data)
                pages = len(reader.pages)
                writer.append(reader)
            except PermissionError:
                skip = "passwortgeschützt"
            except (PdfReadError, ValueError, OSError, KeyError, TypeError) as exc:
                logger.info("Dossier: %s unreadable: %s", d.filename, exc)
                skip = "PDF nicht lesbar" if what == "pdf" else "Bild nicht lesbar"
        if skip is not None:
            result.skipped.append({"id": d.id, "title": d.title, "reason": skip})
            continue
        result.parts.append({"id": d.id, "title": d.title, "category": d.category, "pages": pages})
        result.pages += pages
    if result.parts:
        buffer = io.BytesIO()
        writer.write(buffer)
        result.pdf = buffer.getvalue()
    return result
