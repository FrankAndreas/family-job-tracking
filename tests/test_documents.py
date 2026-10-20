import io
from datetime import date

import pytest

from app import config, files, models
from helpers import create_user, login


def test_category_tables_agree():
    assert models.CATEGORY_ORDER == ["letter", "cv", "report", "certificate", "other"]
    assert set(models.CATEGORY_FOLDERS) == set(models.CATEGORY_ORDER) == set(models.CATEGORY_LABELS)
    assert models.CATEGORY_FOLDERS["report"] == "zeugnis"


def test_store_document_names_the_file_after_title_and_date():
    path = files.store_document("report", date(2026, 7, 1), "Zeugnis 2. Sek, 1. Semester", "scan.PDF", b"x")
    assert path == "_unterlagen/zeugnis/2026-07-01_zeugnis_Zeugnis-2-Sek-1-Semester.pdf"
    assert (config.files_dir() / path).read_bytes() == b"x"
    again = files.store_document("report", date(2026, 7, 1), "Zeugnis 2. Sek, 1. Semester", "scan.pdf", b"y")
    assert again == "_unterlagen/zeugnis/2026-07-01_zeugnis_Zeugnis-2-Sek-1-Semester_2.pdf"


def test_store_document_title_with_dots_and_slashes_keeps_the_extension():
    path = files.store_document("certificate", date(2026, 3, 5), "Multicheck 2./3. Teil", "IMG_1234.heic", b"x")
    assert path == "_unterlagen/zertifikat/2026-03-05_zertifikat_Multicheck-2-3-Teil.heic"


def test_store_document_without_extension():
    assert files.store_document("other", date(2026, 1, 2), "Notizen", "notes", b"x").endswith("_andere_Notizen")


def test_move_document_to_another_category():
    path = files.store_document("other", date(2026, 1, 2), "Stellwerk", "s.pdf", b"x")
    moved = files.move_document(path, "certificate")
    assert moved == "_unterlagen/zertifikat/2026-01-02_zertifikat_Stellwerk.pdf"
    assert (config.files_dir() / moved).exists()
    assert not (config.files_dir() / path).exists()
