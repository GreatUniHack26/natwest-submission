"""Tips and benchmarks endpoints for the "Tips and benchmarks" screen (seeded DB, no network/LLM)."""
import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.api import insight_routes
from backend.data.seed import seed
from backend.main import app

DISCLAIMER = "General information, not financial or tax advice."


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MOCK_DATA", False)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "insights.db"))
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    seed()
    return TestClient(app)


def test_tips_for_sam_are_tips_with_the_disclaimer(client):
    r = client.get("/users/sam/tips")
    assert r.status_code == 200
    tips = r.json()
    assert tips, "Sam (student, travels) should get at least one tip"
    for t in tips:
        assert t["id"] and t["title"] and t["body"]
        assert t["disclaimer"] == DISCLAIMER


def test_tips_unknown_user_is_404(client):
    assert client.get("/users/nobody/tips").status_code == 404


def test_tips_survive_a_broken_rule(client, monkeypatch):
    def boom(_uid):
        raise RuntimeError("rule crashed")

    monkeypatch.setattr("backend.rules.RULES", [boom])
    r = client.get("/users/sam/tips")
    assert r.status_code == 200 and r.json() == []


def test_benchmarks_for_sam_compare_against_his_region(client):
    r = client.get("/users/sam/benchmarks")
    assert r.status_code == 200
    b = r.json()
    assert b["region"] == "Manchester" and b["region_label"] == "North West"
    assert b["comparable"] is True and b["comparisons"]
    assert b["window_days"] == 30 and b["household_size"] == 1
    for c in b["comparisons"]:
        assert c["region_monthly_gbp"] > 0 and c["user_spend_30d"] >= 0
    assert b["sources"] and all(s["url"].startswith("https://www.ons.gov.uk") for s in b["sources"])
    assert b["framing_note"]


def test_benchmarks_household_size_override(client):
    b = client.get("/users/maya/benchmarks", params={"household_size": 4}).json()
    assert b["household_size"] == 4 and b["household_type_label"] == "Two adults with two children"


def test_benchmarks_unsupported_size_is_missing_data_not_a_guess(client):
    r = client.get("/users/sam/benchmarks", params={"household_size": 3})
    assert r.status_code == 200
    b = r.json()
    assert b["comparable"] is False and b["comparisons"] == [] and b["explanation"]


def test_benchmarks_unknown_user_is_404(client):
    assert client.get("/users/nobody/benchmarks").status_code == 404


def test_benchmarks_module_missing_is_503(client, monkeypatch):
    def unavailable(*_a, **_k):
        raise RuntimeError("Regional benchmarks module (backend.benchmarks) is not available")

    monkeypatch.setattr(insight_routes.benchmark_adapter, "run_get_benchmark", unavailable)
    assert client.get("/users/sam/benchmarks").status_code == 503
