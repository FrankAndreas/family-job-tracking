"""The application dossier: the son's documents as one PDF, in the usual order."""

import os

PDF_TYPES = {"application/pdf"}
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}


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
