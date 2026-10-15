import os
from pathlib import Path
from zoneinfo import ZoneInfo


def env(name: str, default: str = "") -> str:
    """An environment variable, stripped; read on every call so tests can change it."""
    return (os.getenv(name) or default).strip()


def data_dir() -> Path:
    return Path(env("DATA_DIR", "./data"))


def files_dir() -> Path:
    """Attachments and raw e-mails, below the data folder."""
    return data_dir() / "files"


def tz() -> ZoneInfo:
    return ZoneInfo(env("TZ", "Europe/Zurich"))
