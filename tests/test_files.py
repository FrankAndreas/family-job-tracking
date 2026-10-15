from datetime import date

import pytest

from app import config, files

DAY = date(2026, 10, 15)


def test_slugify_umlauts_and_symbols():
    assert files.slugify("Müller & Söhne AG") == "mueller-soehne-ag"
    assert files.slugify("Straße Zürich") == "strasse-zuerich"


def test_slugify_fallback_and_length():
    assert files.slugify("!!!", fallback="firma") == "firma"
    assert files.slugify("株式会社", fallback="firma") == "firma"
    long = files.slugify("Sehr " * 30)
    assert len(long) <= 40
    assert not long.endswith("-")


def test_safe_filename_keeps_case():
    assert files.safe_filename("Lebenslauf Müller (final).PDF") == ("Lebenslauf-Mueller-final", ".pdf")
    assert files.safe_filename("../../etc/passwd") == ("passwd", "")
    assert files.safe_filename("") == ("datei", "")


def test_store_for_company_uses_readable_names_and_counter():
    first = files.store_for_company("Migros Genossenschaft", DAY, "Lebenslauf.pdf", b"a")
    second = files.store_for_company("Migros Genossenschaft", DAY, "Lebenslauf.pdf", b"b")
    third = files.store_for_company("Migros Genossenschaft", DAY, "Lebenslauf.pdf", b"c")
    assert first == "migros-genossenschaft/2026-10-15_migros-genossenschaft_Lebenslauf.pdf"
    assert second == "migros-genossenschaft/2026-10-15_migros-genossenschaft_Lebenslauf_2.pdf"
    assert third == "migros-genossenschaft/2026-10-15_migros-genossenschaft_Lebenslauf_3.pdf"
    assert (config.files_dir() / first).read_bytes() == b"a"


def test_unusable_company_name_gets_fallback_folder():
    assert files.store_for_company("!!!", DAY, "cv.pdf", b"x") == "firma/2026-10-15_firma_cv.pdf"


def test_inbox_and_move_to_company():
    rel = files.store_in_inbox("migros.ch", DAY, "Zeugnis.pdf", b"x")
    assert rel == "_posteingang/2026-10-15_migros-ch_Zeugnis.pdf"
    moved = files.move_to_company(rel, "Migros")
    assert moved == "migros/2026-10-15_migros_Zeugnis.pdf"
    assert not (config.files_dir() / rel).exists()
    assert (config.files_dir() / moved).read_bytes() == b"x"


def test_absolute_rejects_paths_outside_files_dir():
    with pytest.raises(ValueError):
        files.absolute("../test.db")


def test_delete_ignores_missing_file():
    files.delete("migros/nicht-da.pdf")
