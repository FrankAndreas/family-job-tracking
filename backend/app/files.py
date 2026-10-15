import os
import re
import shutil
import unicodedata
from datetime import date
from pathlib import Path

from . import config

# Unassigned e-mails keep their files here until they are assigned to an application
INBOX_FOLDER = "_posteingang"

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


def move_to_company(rel_path: str, company: str) -> str:
    """Move a stored file into the company's folder, renamed with the company; returns the new path."""
    source = absolute(rel_path)
    slug = company_slug(company)
    parts = source.name.split("_", 2)
    if len(parts) == 3:
        day, _prefix, rest = parts
    else:
        day, rest = date.today().isoformat(), source.name
    stem, ext = os.path.splitext(rest)
    folder = config.files_dir() / slug
    folder.mkdir(parents=True, exist_ok=True)
    target = _unique(folder, f"{day}_{slug}_{stem}", ext)
    shutil.move(source, target)
    return target.relative_to(config.files_dir()).as_posix()


def delete(rel_path: str) -> None:
    absolute(rel_path).unlink(missing_ok=True)
