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


def upload(client, headers, name="zeugnis.pdf", content=b"%PDF-1.4 x", category="report", **fields):
    response = client.post(
        "/api/documents",
        data={"category": category, **fields},
        files={"file": (name, content, "application/pdf")},
        headers=headers,
    )
    return response


def uploaded(client, headers, *args, **kwargs) -> dict:
    response = upload(client, headers, *args, **kwargs)
    assert response.status_code == 201, response.text
    return response.json()


def listed(client, headers) -> list[dict]:
    response = client.get("/api/documents", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_documents_need_login(client):
    assert client.get("/api/documents").status_code == 401


def test_upload_and_list(client, admin_headers, db):
    d = uploaded(client, admin_headers, title="Zeugnis 1. Semester", issued_on="2026-02-01", note="gut")
    assert (d["category"], d["title"], d["issued_on"], d["note"]) == ("report", "Zeugnis 1. Semester", "2026-02-01", "gut")
    assert (d["filename"], d["size"], d["in_dossier"], d["outdated"]) == ("zeugnis.pdf", 10, True, False)
    assert d["created_by_name"] == "Admin"
    stored = db.get(models.Document, d["id"])
    assert stored.path == "_unterlagen/zeugnis/2026-02-01_zeugnis_Zeugnis-1-Semester.pdf"
    assert listed(client, admin_headers)[0]["id"] == d["id"]


def test_title_defaults_to_the_file_name(client, admin_headers):
    assert uploaded(client, admin_headers, name="Multicheck_Informatik.pdf")["title"] == "Multicheck_Informatik"


@pytest.mark.parametrize(
    "kwargs, status",
    [({"category": "zeugnis"}, 422), ({"content": b""}, 422), ({"issued_on": "gestern"}, 422)],
)
def test_upload_refuses_bad_input(client, admin_headers, kwargs, status):
    assert upload(client, admin_headers, **kwargs).status_code == status


def test_upload_refuses_files_over_25_mb(client, admin_headers, monkeypatch):
    from app import documents_api

    monkeypatch.setattr(documents_api, "MAX_UPLOAD_BYTES", 5)
    assert upload(client, admin_headers, content=b"123456").status_code == 413


def test_list_order_is_category_then_newest_first(client, admin_headers):
    first = uploaded(client, admin_headers, title="Zeugnis alt")
    second = uploaded(client, admin_headers, title="Zeugnis neu")
    cv = uploaded(client, admin_headers, title="CV", category="cv")
    other = uploaded(client, admin_headers, title="Foto", category="other")
    assert [d["id"] for d in listed(client, admin_headers)] == [cv["id"], second["id"], first["id"], other["id"]]


def test_patch_fields_and_clear_date(client, admin_headers):
    d = uploaded(client, admin_headers, issued_on="2026-02-01")
    response = client.patch(
        f"/api/documents/{d['id']}", json={"title": "Neu", "note": "x", "issued_on": None}, headers=admin_headers
    )
    assert response.status_code == 200, response.text
    assert (response.json()["title"], response.json()["note"], response.json()["issued_on"]) == ("Neu", "x", None)


def test_patch_category_moves_the_file_and_puts_it_first(client, admin_headers, db):
    existing = uploaded(client, admin_headers, title="Stellwerk alt", category="certificate")
    d = uploaded(client, admin_headers, title="Stellwerk", issued_on="2026-01-02", category="other")
    moved = client.patch(f"/api/documents/{d['id']}", json={"category": "certificate"}, headers=admin_headers).json()
    assert moved["category"] == "certificate"
    db.expire_all()
    path = db.get(models.Document, d["id"]).path
    assert path == "_unterlagen/zertifikat/2026-01-02_zertifikat_Stellwerk.pdf"
    assert (config.files_dir() / path).exists()
    certificates = [x["id"] for x in listed(client, admin_headers) if x["category"] == "certificate"]
    assert certificates == [d["id"], existing["id"]]


def test_patch_category_into_an_empty_category(client, admin_headers):
    d = uploaded(client, admin_headers, category="other")
    response = client.patch(f"/api/documents/{d['id']}", json={"category": "letter"}, headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["category"] == "letter"


def test_patch_refuses_unknown_category(client, admin_headers):
    d = uploaded(client, admin_headers)
    assert client.patch(f"/api/documents/{d['id']}", json={"category": "x"}, headers=admin_headers).status_code == 422


def test_outdated_takes_it_out_of_the_dossier(client, admin_headers):
    d = uploaded(client, admin_headers)
    outdated = client.patch(f"/api/documents/{d['id']}", json={"outdated": True}, headers=admin_headers).json()
    assert (outdated["outdated"], outdated["in_dossier"]) == (True, False)
    current = client.patch(f"/api/documents/{d['id']}", json={"outdated": False}, headers=admin_headers).json()
    assert (current["outdated"], current["in_dossier"]) == (False, False)


def test_move_up_and_down_and_at_the_edges(client, admin_headers):
    a = uploaded(client, admin_headers, title="A")
    b = uploaded(client, admin_headers, title="B")  # newest first: B, A
    c = uploaded(client, admin_headers, title="C")  # C, B, A

    def move(doc, direction):
        response = client.post(f"/api/documents/{doc['id']}/move", json={"direction": direction}, headers=admin_headers)
        assert response.status_code == 200, response.text
        return [x["title"] for x in response.json()]

    assert move(a, "up") == ["C", "A", "B"]
    assert move(c, "up") == ["C", "A", "B"]  # already first
    assert move(b, "down") == ["C", "A", "B"]  # already last
    assert move(c, "down") == ["A", "C", "B"]
    positions = [x["position"] for x in listed(client, admin_headers)]
    assert len(set(positions)) == 3


def test_move_refuses_unknown_direction(client, admin_headers):
    d = uploaded(client, admin_headers)
    assert client.post(f"/api/documents/{d['id']}/move", json={"direction": "left"}, headers=admin_headers).status_code == 422


def test_download_inline_with_original_name(client, admin_headers):
    d = uploaded(client, admin_headers, name="Zeugnis Juli.pdf", content=b"%PDF-1.4 abc")
    response = client.get(f"/api/documents/{d['id']}/file", headers=admin_headers)
    assert response.status_code == 200
    assert response.content == b"%PDF-1.4 abc"
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline")


def test_missing_file_is_404_but_the_list_still_loads(client, admin_headers, db):
    d = uploaded(client, admin_headers)
    (config.files_dir() / db.get(models.Document, d["id"]).path).unlink()
    assert client.get(f"/api/documents/{d['id']}/file", headers=admin_headers).status_code == 404
    assert len(listed(client, admin_headers)) == 1


def test_delete_removes_the_file(client, admin_headers, db):
    d = uploaded(client, admin_headers)
    path = config.files_dir() / db.get(models.Document, d["id"]).path
    assert client.delete(f"/api/documents/{d['id']}", headers=admin_headers).status_code == 204
    assert not path.exists()
    assert listed(client, admin_headers) == []


def test_unknown_document_is_404(client, admin_headers):
    assert client.patch("/api/documents/99", json={}, headers=admin_headers).status_code == 404


def test_move_skips_outdated_documents_shown_apart(client, admin_headers):
    c = uploaded(client, admin_headers, title="C")
    b = uploaded(client, admin_headers, title="B")
    a = uploaded(client, admin_headers, title="A")  # order A, B, C
    client.patch(f"/api/documents/{b['id']}", json={"outdated": True}, headers=admin_headers)
    titles = [x["title"] for x in client.post(
        f"/api/documents/{a['id']}/move", json={"direction": "down"}, headers=admin_headers
    ).json()]
    assert [t for t in titles if t != "B"] == ["C", "A"]
