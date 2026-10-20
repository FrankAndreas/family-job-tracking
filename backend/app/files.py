import os
import re
import shutil
import unicodedata
from datetime import date
from pathlib import Path

from . import config

# Unassigned e-mails keep their files here until they are assigned to an application
INBOX_FOLDER = "_posteingang"
# The son's application documents, one subfolder per category
DOCUMENTS_FOLDER = "_unterlagen"

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"})


def slugify(text: str, *, lower: bool = True, max_len: int = 40, fallback: str = "unbenannt") -> str:
    """ASCII letters, digits and dashes only, for folder and file names that read well in File Station."""
    text = unicodedata.normalize("NFKD", (text or "").translate(_UMLAUTS)).encode("ascii", "ignore").decode()
    if lower:
        text = text.lower()
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")
    return text[:max_len].strip("-") or fallback


def safe_filename(name: str) -> tuple[str, str]:
    """(stem, extension) of an uploaded or attached file name, cleaned for the file system."""
    stem, ext = os.path.splitext(os.path.basename(name or ""))
    ext = re.sub(r"[^a-z0-9.]", "", ext.lower())[:10]
    return slugify(stem, lower=False, max_len=80, fallback="datei"), ext


def company_slug(company: str) -> str:
    return slugify(company, fallback="firma")


def _unique(folder: Path, base: str, ext: str) -> Path:
    candidate = folder / f"{base}{ext}"
    counter = 2
    while candidate.exists():
        candidate = folder / f"{base}_{counter}{ext}"
        counter += 1
    return candidate


def _store(folder_name: str, day: date, prefix: str, original_name: str, content: bytes) -> str:
    root = config.files_dir()
    folder = root / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    stem, ext = safe_filename(original_name)
    path = _unique(folder, f"{day:%Y-%m-%d}_{prefix}_{stem}", ext)
    path.write_bytes(content)
    return path.relative_to(root).as_posix()


def store_for_company(company: str, day: date, original_name: str, content: bytes) -> str:
    """Save a file as <company>/<date>_<company>_<name>.<ext>; returns the path relative to files_dir()."""
    slug = company_slug(company)
    return _store(slug, day, slug, original_name, content)


def store_in_inbox(sender_domain: str, day: date, original_name: str, content: bytes) -> str:
    """Save a file of an unassigned e-mail as _posteingang/<date>_<sender domain>_<name>.<ext>."""
    return _store(INBOX_FOLDER, day, slugify(sender_domain, fallback="unbekannt"), original_name, content)


def absolute(rel_path: str) -> Path:
    root = config.files_dir().resolve()
    path = (root / rel_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Path outside the files folder: {rel_path}")
    return path


def _move(rel_path: str, folder_name: str, prefix: str) -> str:
    """Move a stored file to <folder>/<date>_<prefix>_<rest>; a missing file keeps its old path."""
    source = absolute(rel_path)
    if not source.exists():
        return rel_path
    parts = source.name.split("_", 2)
    if len(parts) == 3:
        day, _prefix, rest = parts
    else:
        day, rest = date.today().isoformat(), source.name
    stem, ext = os.path.splitext(rest)
    folder = config.files_dir() / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    target = _unique(folder, f"{day}_{prefix}_{stem}", ext)
    shutil.move(source, target)
    return target.relative_to(config.files_dir()).as_posix()


def move_to_company(rel_path: str, company: str) -> str:
    """Move a stored file into the company's folder, renamed with the company; returns the new path."""
    slug = company_slug(company)
    return _move(rel_path, slug, slug)


def move_to_inbox(rel_path: str, sender_domain: str) -> str:
    """Move a stored file back to the inbox folder, renamed with the sender's domain."""
    return _move(rel_path, INBOX_FOLDER, slugify(sender_domain, fallback="unbekannt"))


def rename(rel_from: str, rel_to: str) -> None:
    """Undo a move: put the file back where it was."""
    shutil.move(absolute(rel_from), absolute(rel_to))


def delete(rel_path: str) -> None:
    absolute(rel_path).unlink(missing_ok=True)


def _document_folder(category: str) -> str:
    from .models import CATEGORY_FOLDERS

    return CATEGORY_FOLDERS[category]


def store_document(category: str, day: date, title: str, original_name: str, content: bytes) -> str:
    """Save a document as _unterlagen/<folder>/<date>_<folder>_<title>.<ext of the upload>."""
    folder = _document_folder(category)
    _stem, ext = safe_filename(original_name)
    # The title is slugified first, so dots in it can't be taken for the extension
    name = slugify(title, lower=False, max_len=80, fallback="dokument") + ext
    return _store(f"{DOCUMENTS_FOLDER}/{folder}", day, folder, name, content)


def move_document(rel_path: str, category: str) -> str:
    """Move a document's file into the folder of its new category."""
    folder = _document_folder(category)
    return _move(rel_path, f"{DOCUMENTS_FOLDER}/{folder}", folder)
