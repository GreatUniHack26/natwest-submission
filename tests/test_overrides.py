"""Issue #7 unit tests: user overrides in the repository, categoriser, contract and PATCH route."""
import datetime as dt

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend import config
from backend.data import categoriser, repository
from backend.data.categoriser import categorise
from backend.data.seed import seed
from backend.main import app
from contracts.schemas import CategoryOverride, Transaction, User


@pytest.fixture(autouse=True)
def real_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MOCK_DATA", False)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "ov.db"))
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    monkeypatch.setattr(categoriser, "CACHE_PATH", tmp_path / "cache.json")
    return tmp_path / "ov.db"


def _tx(tid, uid="u1", amount=-5.0, category="groceries", kind="need", merchant="Shop"):
    return Transaction(id=tid, user_id=uid, date=dt.date(2026, 1, 10), merchant=merchant,
                       amount=amount, category=category, kind=kind)


def _user(uid="u1"):
    return User(id=uid, name=uid, persona="p", region="r")


@pytest.fixture
def one_user():
    repository.save_persona(_user(), [_tx("a"), _tx("b", amount=-9.0)], [])


# ---- contract ---------------------------------------------------------------------

def test_contract_accepts_valid_and_rejects_invalid():
    assert CategoryOverride(category="eating out", kind="want").kind == "want"
    for bad in ({"category": "", "kind": "want"}, {"category": "x", "kind": "maybe"}, {"kind": "need"}):
        with pytest.raises(ValidationError):
            CategoryOverride(**bad)


# ---- repository ---------------------------------------------------------------------

def test_set_override_returns_the_transaction_as_the_user_now_sees_it(one_user):
    got = repository.set_override("u1", "a", "Eating Out", "want")
    assert (got.id, got.category, got.kind, got.amount) == ("a", "eating out", "want", -5.0)


def test_override_is_applied_when_reading_transactions(one_user):
    repository.set_override("u1", "a", "eating out", "want")
    by_id = {t.id: t for t in repository.get_transactions("u1")}
    assert (by_id["a"].category, by_id["a"].kind) == ("eating out", "want")
    assert (by_id["b"].category, by_id["b"].kind) == ("groceries", "need")  # others untouched


def test_override_applies_with_date_filters(one_user):
    repository.set_override("u1", "a", "x", "want")
    got = repository.get_transactions("u1", start=dt.date(2026, 1, 10), end=dt.date(2026, 1, 10))
    assert {t.id: t.kind for t in got} == {"a": "want", "b": "need"}


def test_original_labels_stay_intact_underneath(one_user, real_db):
    import sqlite3

    repository.set_override("u1", "a", "x", "want")
    raw = sqlite3.connect(real_db).execute("SELECT category, kind FROM transactions WHERE id='a'").fetchone()
    assert raw == ("groceries", "need")


def test_override_can_be_replaced(one_user):
    repository.set_override("u1", "a", "x", "want")
    repository.set_override("u1", "a", "y", "need")
    assert repository.get_overrides("u1") == {"a": ("y", "need")}


def test_any_kind_including_income_is_allowed(one_user):
    for kind in ("need", "want", "income"):
        assert repository.set_override("u1", "a", "x", kind).kind == kind


def test_category_is_stripped_and_lowercased(one_user):
    assert repository.set_override("u1", "a", "  Eating   Out ", "want").category == "eating   out"


@pytest.mark.parametrize("category,kind", [("", "want"), ("   ", "want"), ("x", "maybe"), ("x", "")])
def test_invalid_overrides_are_rejected_and_not_stored(one_user, category, kind):
    with pytest.raises(ValueError):
        repository.set_override("u1", "a", category, kind)
    assert repository.get_overrides("u1") == {}


def test_unknown_transaction_raises_keyerror(one_user):
    with pytest.raises(KeyError):
        repository.set_override("u1", "nope", "x", "want")


def test_cannot_override_another_users_transaction(one_user):
    repository.save_persona(_user("u2"), [_tx("c", "u2")], [])
    with pytest.raises(KeyError):
        repository.set_override("u1", "c", "x", "want")
    assert repository.get_transactions("u2")[0].kind == "need"


def test_override_survives_a_new_connection_and_a_reseed(one_user):
    repository.set_override("u1", "a", "x", "want")
    assert repository.get_overrides("u1") == {"a": ("x", "want")}
    repository.save_persona(_user(), [_tx("a"), _tx("b", amount=-9.0)], [])  # what `make seed` does
    assert {t.id: t.kind for t in repository.get_transactions("u1")}["a"] == "want"


def test_get_overrides_empty_for_unknown_user():
    assert repository.get_overrides("nobody") == {}


def test_mock_mode_returns_override_without_persisting(monkeypatch, real_db):
    monkeypatch.setattr(config, "MOCK_DATA", True)
    got = repository.set_override("sam", "t1", "Treats", "want")
    assert (got.id, got.category, got.kind) == ("t1", "treats", "want")
    assert repository.get_overrides("sam") == {}
    assert next(t for t in repository.get_transactions("sam") if t.id == "t1").kind == "need"
    with pytest.raises(KeyError):
        repository.set_override("sam", "missing", "x", "want")
    assert not real_db.exists()


# ---- categorise(overrides=...) ---------------------------------------------------------

def test_override_beats_rules():
    t = _tx("a", merchant="Tesco")
    assert categorise([t], {"a": ("treats", "want")})[0].kind == "want"


def test_override_beats_income_by_sign():
    t = _tx("a", amount=50.0, merchant="Mystery")
    out = categorise([t], {"a": ("refund", "need")})[0]
    assert (out.category, out.kind) == ("refund", "need")


def test_overridden_transactions_are_never_sent_to_the_llm(monkeypatch):
    monkeypatch.setattr(config, "LLM_API_KEY", "k")
    monkeypatch.setattr(categoriser, "_call_llm", lambda p: pytest.fail("LLM called"))
    out = categorise([_tx("a", merchant="Unheard Of Ltd")], {"a": ("gifts", "want")})
    assert (out[0].category, out[0].kind) == ("gifts", "want")


def test_non_overridden_transactions_unaffected_by_overrides():
    txs = [_tx("a", merchant="Tesco"), _tx("b", merchant="Netflix")]
    out = categorise(txs, {"a": ("treats", "want")})
    assert (out[1].category, out[1].kind) == ("subscriptions", "want")


def test_no_overrides_behaves_as_before():
    txs = [_tx("a", merchant="Tesco")]
    assert categorise(txs) == categorise(txs, None) == categorise(txs, {})


# ---- PATCH route ------------------------------------------------------------------------

@pytest.fixture
def client():
    seed()
    return TestClient(app)


def _first_tx(client, uid="sam"):
    return client.get(f"/users/{uid}/transactions").json()[0]


def test_patch_returns_the_overridden_transaction(client):
    tx = _first_tx(client)
    r = client.patch(f"/users/sam/transactions/{tx['id']}", json={"category": "Gifts", "kind": "want"})
    assert r.status_code == 200
    assert (r.json()["id"], r.json()["category"], r.json()["kind"]) == (tx["id"], "gifts", "want")
    assert r.json()["amount"] == tx["amount"] and r.json()["merchant"] == tx["merchant"]


def test_patch_then_get_shows_override(client):
    tx = _first_tx(client)
    client.patch(f"/users/sam/transactions/{tx['id']}", json={"category": "gifts", "kind": "want"})
    again = {t["id"]: t for t in client.get("/users/sam/transactions").json()}[tx["id"]]
    assert (again["category"], again["kind"]) == ("gifts", "want")


def test_patch_unknown_transaction_is_404(client):
    r = client.patch("/users/sam/transactions/nope", json={"category": "x", "kind": "want"})
    assert r.status_code == 404 and "nope" in r.json()["detail"]


def test_patch_other_users_transaction_is_404(client):
    other = _first_tx(client, "alex")
    r = client.patch(f"/users/sam/transactions/{other['id']}", json={"category": "x", "kind": "want"})
    assert r.status_code == 404


@pytest.mark.parametrize("body", [
    {"category": "x", "kind": "maybe"}, {"category": "", "kind": "want"},
    {"category": "x"}, {"kind": "want"}, {},
])
def test_patch_invalid_body_is_422(client, body):
    tx = _first_tx(client)
    assert client.patch(f"/users/sam/transactions/{tx['id']}", json=body).status_code == 422


def test_patch_whitespace_category_is_422_not_500(client):
    tx = _first_tx(client)
    r = client.patch(f"/users/sam/transactions/{tx['id']}", json={"category": "   ", "kind": "want"})
    assert r.status_code == 422


def test_patch_in_mock_mode_echoes_without_persisting(monkeypatch, real_db):
    monkeypatch.setattr(config, "MOCK_DATA", True)
    r = TestClient(app).patch("/users/sam/transactions/t1", json={"category": "treats", "kind": "want"})
    assert r.status_code == 200 and r.json()["kind"] == "want"
    assert not real_db.exists()
