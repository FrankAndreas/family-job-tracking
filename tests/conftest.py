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

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import database, models  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Every test starts with an empty database and its own files folder."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    models.Base.metadata.drop_all(bind=database.engine)
    models.Base.metadata.create_all(bind=database.engine)
    yield


@pytest.fixture
def db():
    with database.SessionLocal() as session:
        yield session


@pytest.fixture
def client():
    return TestClient(app)
