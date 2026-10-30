"""Bring an existing database to the current schema on start: `create_all` only makes missing tables, never new
columns. Since 2026-10-30 the people come from the family hub: `users` gets `hub_id` and `is_active`, and the PIN
columns go. Each step checks first, so every start may run it."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def upgrade(engine: Engine) -> None:
    with engine.begin() as conn:
        if not inspect(conn).has_table("users"):
            return
        columns = {c["name"] for c in inspect(conn).get_columns("users")}
        if "hub_id" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN hub_id INTEGER"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_hub_id ON users (hub_id)"))
        if "is_active" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"))
        # SQLite 3.35+ drops a column in place (none of these is in an index or constraint)
        for gone in ("pin_hash", "failed_logins", "locked_until"):
            if gone in columns:
                conn.execute(text(f"ALTER TABLE users DROP COLUMN {gone}"))
