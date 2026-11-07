"""Issue #4 integration: generator -> seed -> SQLite -> repository -> HTTP API, per persona."""
import pytest
from fastapi.testclient import TestClient

from backend import config, data
from backend.data import repository
from backend.data.generator import generate_household, generate_persona
from backend.data.seed import seed
from backend.main import app
from contracts import schemas


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MOCK_DATA", False)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "hh.db"))
    counts = seed()
    return TestClient(app), counts


def test_seed_covers_every_persona(seeded):
    _, counts = seeded
    assert set(counts) == {"sam", "alex", "maya", "dan", "pete"}


def test_both_household_members_load_via_repository(seeded):
    members = repository.get_household_members("h1")
    assert [u.id for u in members] == ["dan", "maya"]
    assert all(u.household_id == "h1" for u in members)
    expected = {u.id: u for u, _, _ in generate_household("family", 42)}
    assert {u.id: u for u in members} == expected


def test_each_member_gets_own_transactions_and_shared_pots_once(seeded):
    for user, txs, pots in generate_household("family", 42):
        assert repository.get_transactions(user.id) == sorted(txs, key=lambda t: (t.date, t.id))
        assert repository.get_pots(user.id) == sorted(pots, key=lambda p: p.id)
    all_pot_ids = [p.id for u in repository.get_household_members("h1") for p in repository.get_pots(u.id)]
    assert len(all_pot_ids) == len(set(all_pot_ids)) == 3


def test_salaried_round_trips(seeded):
    user, txs, pots = generate_persona("salaried", 42)
    assert repository.get_user("alex") == user
    assert len(repository.get_transactions("alex")) == len(txs)


def test_api_serves_every_member(seeded):
    client, _ = seeded
    for uid in ("maya", "dan", "alex", "sam", "pete"):
        assert schemas.User(**client.get(f"/users/{uid}").json()).id == uid
        rows = [schemas.Transaction(**t) for t in client.get(f"/users/{uid}/transactions").json()]
        assert rows and all(t.user_id == uid for t in rows)
    assert len(client.get("/users/maya/pots").json()) == 3
    assert client.get("/users/dan/pots").json() == []


def test_public_interface_exports_household_functions():
    assert data.generate_household is generate_household
    assert data.get_household_members is repository.get_household_members


def test_reseeding_household_is_idempotent(seeded):
    before = {u: repository.get_transactions(u) for u in ("maya", "dan")}
    seed()
    assert {u: repository.get_transactions(u) for u in ("maya", "dan")} == before
    assert len(repository.get_pots("maya")) == 3


def test_reseeding_keeps_other_households_data(seeded):
    seed(personas=["sam"], households=[])  # partial re-seed must not touch the family
    assert len(repository.get_household_members("h1")) == 2
