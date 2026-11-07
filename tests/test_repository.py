"""Issue #5 unit tests: SQLite repository in real mode, against a throwaway DB per test."""
import datetime as dt
import sqlite3
from pathlib import Path

import pytest

from backend import config
from backend.data import repository
from backend.data.seed import seed
from contracts.schemas import Pot, Transaction, User


@pytest.fixture(autouse=True)
def real_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MOCK_DATA", False)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    return tmp_path / "test.db"


def _user(uid="u1"):
    return User(id=uid, name="Test", persona="p", region="Leeds", household_id="h1", tone="direct")


def _tx(tid, uid="u1", date="2026-01-10", amount=-5.0):
    return Transaction(id=tid, user_id=uid, date=date, merchant="Shop", amount=amount,
                       category="groceries", kind="need")


def test_user_round_trip():
    u = _user()
    repository.save_persona(u, [], [])
    assert repository.get_user("u1") == u


def test_user_optional_household_none():
    u = User(id="u2", name="N", persona="p", region="r")
    repository.save_persona(u, [], [])
    got = repository.get_user("u2")
    assert got.household_id is None and got.tone == "friendly"


def test_unknown_user_raises_keyerror():
    with pytest.raises(KeyError):
        repository.get_user("nobody")


def test_unknown_user_lists_are_empty():
    assert repository.get_transactions("nobody") == []
    assert repository.get_pots("nobody") == []


def test_transactions_round_trip_and_sorted():
    txs = [_tx("b", date="2026-01-12"), _tx("a", date="2026-01-10"), _tx("c", date="2026-01-11")]
    repository.save_persona(_user(), txs, [])
    got = repository.get_transactions("u1")
    assert [t.id for t in got] == ["a", "c", "b"]
    assert all(isinstance(t.date, dt.date) for t in got)
    assert got[0] == _tx("a", date="2026-01-10")


@pytest.mark.parametrize(
    "start,end,expected",
    [
        (None, None, ["a", "b", "c"]),
        (dt.date(2026, 1, 11), None, ["b", "c"]),
        (None, dt.date(2026, 1, 11), ["a", "b"]),
        (dt.date(2026, 1, 11), dt.date(2026, 1, 11), ["b"]),  # inclusive both ends
        (dt.date(2026, 2, 1), None, []),
    ],
)
def test_transaction_date_filters(start, end, expected):
    txs = [_tx("a", date="2026-01-10"), _tx("b", date="2026-01-11"), _tx("c", date="2026-01-12")]
    repository.save_persona(_user(), txs, [])
    assert [t.id for t in repository.get_transactions("u1", start, end)] == expected


def test_transactions_scoped_to_user():
    repository.save_persona(_user("u1"), [_tx("a", "u1")], [])
    repository.save_persona(_user("u2"), [_tx("b", "u2")], [])
    assert [t.id for t in repository.get_transactions("u1")] == ["a"]


def test_get_pots_and_open_ended_due_date():
    pots = [Pot(id="p1", user_id="u1", name="Rent", amount=950, due_date="2026-12-01"),
            Pot(id="p2", user_id="u1", name="Emergency", amount=300)]
    repository.save_persona(_user(), [], pots)
    got = repository.get_pots("u1")
    assert got == pots and got[1].due_date is None


def test_add_pot_persists():
    repository.save_persona(_user(), [], [])
    pot = Pot(id="p9", user_id="u1", name="Holiday", amount=100, due_date="2027-06-01")
    assert repository.add_pot(pot) == pot
    assert repository.get_pots("u1") == [pot]


def test_add_pot_rejects_duplicate_id():
    repository.save_persona(_user(), [], [])
    pot = Pot(id="p9", user_id="u1", name="Holiday", amount=100)
    repository.add_pot(pot)
    with pytest.raises(ValueError, match="already exists"):
        repository.add_pot(pot.model_copy(update={"amount": 1}))
    assert repository.get_pots("u1")[0].amount == 100  # untouched


def test_add_pot_rejects_unknown_user():
    with pytest.raises(ValueError, match="unknown user"):
        repository.add_pot(Pot(id="p1", user_id="ghost", name="x", amount=1))
    assert repository.get_pots("ghost") == []


def test_save_persona_replaces_previous_rows():
    repository.save_persona(_user(), [_tx("a"), _tx("b")], [Pot(id="p1", user_id="u1", name="x", amount=1)])
    repository.save_persona(_user(), [_tx("c")], [])
    assert [t.id for t in repository.get_transactions("u1")] == ["c"]
    assert repository.get_pots("u1") == []


def test_save_persona_leaves_other_users_alone():
    repository.save_persona(_user("u1"), [_tx("a", "u1")], [])
    repository.save_persona(_user("u2"), [_tx("b", "u2")], [])
    repository.save_persona(_user("u1"), [], [])
    assert [t.id for t in repository.get_transactions("u2")] == ["b"]


def test_save_persona_is_atomic(real_db):
    repository.save_persona(_user(), [_tx("a")], [])
    with pytest.raises(sqlite3.IntegrityError):  # duplicate tx id inside the batch
        repository.save_persona(_user(), [_tx("x"), _tx("x")], [])
    assert [t.id for t in repository.get_transactions("u1")] == ["a"]  # rolled back


def test_foreign_keys_enforced():
    with pytest.raises(sqlite3.IntegrityError):
        with repository._connect() as conn:
            conn.execute("INSERT INTO pots (id, user_id, name, amount) VALUES ('p', 'ghost', 'x', 1)")


def test_schema_created_lazily_and_persists_across_connections(real_db):
    assert not real_db.exists()
    repository.save_persona(_user(), [_tx("a")], [])
    assert real_db.exists()
    assert len(repository.get_transactions("u1")) == 1  # fresh connection sees it


def test_seed_is_idempotent():
    first = seed()
    snapshot = repository.get_transactions("sam")
    pots = repository.get_pots("sam")
    assert seed() == first
    assert repository.get_transactions("sam") == snapshot
    assert repository.get_pots("sam") == pots


def test_mock_mode_untouched(monkeypatch, real_db):
    monkeypatch.setattr(config, "MOCK_DATA", True)
    assert repository.get_user("anyone").id  # fixture
    assert not real_db.exists()  # mock mode never opens the DB


def test_only_repository_touches_sqlite():
    root = Path(__file__).parent.parent / "backend"
    offenders = [
        str(p.relative_to(root)) for p in root.rglob("*.py")
        if p.name != "repository.py" and "sqlite3" in p.read_text()
    ]
    assert offenders == []


def test_get_household_members():
    for uid, hid in [("a", "h1"), ("b", "h1"), ("c", "h2"), ("d", None)]:
        repository.save_persona(User(id=uid, name=uid, persona="p", region="r", household_id=hid), [], [])
    assert [u.id for u in repository.get_household_members("h1")] == ["a", "b"]
    assert [u.id for u in repository.get_household_members("h2")] == ["c"]
    assert repository.get_household_members("nope") == []


def test_get_household_members_mock_mode(monkeypatch, real_db):
    monkeypatch.setattr(config, "MOCK_DATA", True)
    assert repository.get_household_members("h1") == []
    assert not real_db.exists()
