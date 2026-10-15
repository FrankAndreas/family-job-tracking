import os
import sys
import tempfile
from pathlib import Path

# Point the app at a throwaway database and data folder before it is imported, so tests never touch ./data
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["DATA_DIR"] = _tmp
os.environ["SECRET_KEY"] = "test-secret"
os.environ["INITIAL_ADMIN_PIN"] = "1234"
os.environ["TZ"] = "Europe/Zurich"
# Optional integrations start switched off; tests that need them set the variables with monkeypatch
for _name in ("INBOUND_SECRET", "RESEND_API_KEY", "MAIL_FROM", "APP_URL"):
    os.environ.pop(_name, None)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import functools  # noqa: E402

import bcrypt  # noqa: E402
import pytest  # noqa: E402

# Cheap PIN hashes: bcrypt's default cost makes every login in a test take ~0.25 s
bcrypt.gensalt = functools.partial(bcrypt.gensalt, rounds=4)
from fastapi.testclient import TestClient  # noqa: E402

from app import database, models  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed_admin  # noqa: E402
from helpers import login  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Every test starts like a fresh install: user "Admin" with PIN 1234, and its own files folder."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    models.Base.metadata.drop_all(bind=database.engine)
    models.Base.metadata.create_all(bind=database.engine)
    with database.SessionLocal() as session:
        seed_admin(session)
    yield


@pytest.fixture
def db():
    with database.SessionLocal() as session:
        yield session


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def admin_headers(client):
    return login(client)
