import csv
import io
import os
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from . import config, models
from .timeutil import iso

TABLES = [
    ("users", models.User),
    ("applications", models.Application),
    ("events", models.Event),
    ("emails", models.Email),
    ("attachments", models.Attachment),
]
# Login secrets stay out of the export
EXCLUDED_COLUMNS = {"pin_hash", "failed_logins", "locked_until"}


def _cell(value):
    if isinstance(value, datetime):
        return iso(value)
    return "" if value is None else value


def build_zip(db: Session) -> Path:
    """All tables as CSV plus the files folder, in a temporary ZIP the caller deletes."""
    fd, name = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    with zipfile.ZipFile(name, "w", zipfile.ZIP_DEFLATED) as archive:
        for table, model in TABLES:
            columns = [c.name for c in model.__table__.columns if c.name not in EXCLUDED_COLUMNS]
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(columns)
            for row in db.query(model).order_by(model.id):
                writer.writerow([_cell(getattr(row, column)) for column in columns])
            archive.writestr(f"{table}.csv", buffer.getvalue())
        root = config.files_dir()
        if root.exists():
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    archive.write(path, f"files/{path.relative_to(root).as_posix()}")
    return Path(name)
