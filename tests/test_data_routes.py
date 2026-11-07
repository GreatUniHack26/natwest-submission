"""Data API error handling: unknown users and pot conflicts are 4xx, never 500."""
import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.data.seed import seed
from backend.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MOCK_DATA", False)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "routes.db"))
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    seed()
    return TestClient(app)


POT = {"id": "p-new", "user_id": "sam", "name": "Holiday", "amount": 120.0}


def test_unknown_user_is_404_with_a_helpful_message(client):
    r = client.get("/users/nobody")
    assert r.status_code == 404 and "nobody" in r.json()["detail"] and "make seed" in r.json()["detail"]


def test_known_user_still_200(client):
    assert client.get("/users/sam").status_code == 200


def test_add_pot_then_duplicate_is_409(client):
    assert client.post("/users/sam/pots", json=POT).status_code == 200
    r = client.post("/users/sam/pots", json=POT)
    assert r.status_code == 409 and "already exists" in r.json()["detail"]
    assert [p["id"] for p in client.get("/users/sam/pots").json()].count("p-new") == 1


def test_add_pot_for_unknown_user_is_404(client):
    r = client.post("/users/ghost/pots", json={**POT, "user_id": "ghost"})
    assert r.status_code == 404 and "ghost" in r.json()["detail"]


def test_invalid_pot_body_is_422(client):
    assert client.post("/users/sam/pots", json={"id": "x"}).status_code == 422


def test_lists_for_unknown_user_are_empty_not_errors(client):
    assert client.get("/users/nobody/transactions").json() == []
    assert client.get("/users/nobody/pots").json() == []


def test_mock_mode_is_unaffected(monkeypatch):
    monkeypatch.setattr(config, "MOCK_DATA", True)
    c = TestClient(app)
    assert c.get("/users/anyone").status_code == 200
    assert c.post("/users/sam/pots", json=POT).status_code == 200
    assert c.post("/users/sam/pots", json=POT).status_code == 200  # mock mode never conflicts
