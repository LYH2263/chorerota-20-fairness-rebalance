import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient backed by an isolated seeded sqlite DB in tmp_path."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        yield c
