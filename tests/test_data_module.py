"""Issue #8: data-module gap tests and cross-persona invariants.

Per-feature tests live next to each feature (test_generator*, test_repository*,
test_categoriser*, test_household*). This file covers what falls between them:
the public interface, invariants that must hold ACROSS personas (they share one DB),
mock-mode repository behaviour, new-persona guards, and the real LLM client wrapper.
"""
import datetime as dt
import inspect
import random
import sys
import types

import pytest

from backend import config, data
from backend.data import categoriser, generator, repository
from backend.data.generator import generate_household, generate_persona
from contracts import schemas
from contracts.schemas import Pot

SINGLE = ["sam", "salaried"]
HOUSEHOLDS = ["family"]


def _everyone(seed=42):
    members = [generate_persona(n, seed) for n in SINGLE]
    for h in HOUSEHOLDS:
        members += generate_household(h, seed)
    return members


# ---- public interface ("do not rename without a contracts PR") ------------------------

def test_public_interface_is_exactly_what_the_docstring_promises():
    assert set(data.__all__) == {
        "get_user", "get_household_members", "get_transactions", "get_pots", "add_pot",
        "set_override", "get_overrides", "categorise", "generate_persona", "generate_household",
    }
    assert all(callable(getattr(data, name)) for name in data.__all__)


@pytest.mark.parametrize("name,params", [
    ("get_user", ["user_id"]),
    ("get_household_members", ["household_id"]),
    ("get_transactions", ["user_id", "start", "end"]),
    ("get_pots", ["user_id"]),
    ("add_pot", ["pot"]),
    ("set_override", ["user_id", "transaction_id", "category", "kind"]),
    ("get_overrides", ["user_id"]),
    ("categorise", ["transactions", "overrides"]),
    ("generate_persona", ["name", "seed"]),
    ("generate_household", ["name", "seed"]),
])
def test_public_signatures_are_stable(name, params):
    assert list(inspect.signature(getattr(data, name)).parameters) == params


# ---- cross-persona invariants (one SQLite table, so ids must be globally unique) --------

def test_user_ids_are_globally_unique():
    ids = [u.id for u, _, _ in _everyone()]
    assert len(ids) == len(set(ids)) == 4


def test_transaction_ids_are_globally_unique():
    ids = [t.id for _, txs, _ in _everyone() for t in txs]
    assert len(ids) == len(set(ids))


def test_pot_ids_are_globally_unique():
    ids = [p.id for _, _, pots in _everyone() for p in pots]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("seed", [1, 42, 2026])
def test_everyone_validates_against_contracts_for_any_seed(seed):
    for user, txs, pots in _everyone(seed):
        schemas.User(**user.model_dump())
        assert all(schemas.Transaction(**t.model_dump()) for t in txs)
        assert all(schemas.Pot(**p.model_dump()) for p in pots)


def test_everyone_ends_today_and_has_a_positive_balance():
    for user, txs, _ in _everyone():
        assert max(t.date for t in txs) == config.TODAY, user.id
        assert sum(t.amount for t in txs) > 0, user.id


def test_exactly_one_opening_balance_row_per_user_and_it_is_first():
    for user, txs, _ in _everyone():
        opening = [t for t in txs if t.merchant == generator.OPENING_BALANCE_MERCHANT]
        assert len(opening) == 1 and txs[0] is opening[0] and opening[0].amount > 0, user.id


def test_ids_embed_the_owner():
    for user, txs, pots in _everyone():
        assert all(t.id.startswith(f"{user.id}-t") for t in txs)
        assert all(p.id.startswith(f"{user.id}-p") for p in pots)


# ---- new personas: determinism, config anchoring, guards ---------------------------------

@pytest.mark.parametrize("fn,arg", [(generate_persona, "salaried"), (generate_household, "family")])
def test_new_personas_are_deterministic_per_seed(fn, arg):
    assert fn(arg, 5) == fn(arg, 5)
    assert fn(arg, 5) != fn(arg, 6)


@pytest.mark.parametrize("fn,arg", [(generate_persona, "salaried"), (generate_household, "family")])
def test_new_personas_leave_global_random_state_alone(fn, arg):
    random.seed(123)
    expected = random.random()
    random.seed(123)
    fn(arg, 1)
    assert random.random() == expected


def test_new_personas_follow_config_today(monkeypatch):
    monkeypatch.setattr(config, "TODAY", dt.date(2026, 8, 31))
    for user, txs, _ in [generate_persona("salaried"), *generate_household("family")]:
        assert max(t.date for t in txs) == dt.date(2026, 8, 31), user.id
        assert min(t.date for t in txs) == dt.date(2026, 2, 28), user.id


def test_new_personas_amounts_have_at_most_two_decimals():
    for _, txs, _ in _everyone():
        assert all(round(t.amount, 2) == t.amount for t in txs)


@pytest.mark.parametrize("fn,arg", [(generate_persona, "salaried"), (generate_household, "family")])
def test_opening_balance_guard_raises_for_new_personas(monkeypatch, fn, arg):
    monkeypatch.setattr(generator, "SALARIED_TARGET_BALANCE", -10_000.0)
    monkeypatch.setattr(generator, "FAMILY_TARGET_BALANCES", {"maya": -10_000.0, "dan": -10_000.0})
    with pytest.raises(ValueError, match="opening balance"):
        fn(arg)


def test_every_planted_event_exists():
    """One place that lists the demo's planted events; each must be in the generated data."""
    sam_user, sam, sam_pots = generate_persona("sam")
    week = config.TODAY - dt.timedelta(days=6)
    assert any(t.category == "eating out" and t.date >= week for t in sam)  # sam: spike week
    assert {p.name for p in sam_pots} == {"December rent", "Emergency fund"}  # sam: dec pots

    (_, maya, maya_pots), (_, dan, _) = generate_household("family")
    assert {p.name for p in maya_pots} >= {"December rent", "School trip and uniform"}  # family pots
    assert any(t.merchant == "Provident Loan" for t in maya)  # family: recurring debt
    cut = config.TODAY - dt.timedelta(days=30)
    before = [t.amount for t in dan if t.merchant == "Agency work pay" and t.date < cut]
    after = [t.amount for t in dan if t.merchant == "Agency work pay" and t.date >= cut]
    assert before and after
    assert sum(after) < 0.5 * (sum(before) / 4)  # family: Dan's pay was cut

    _, alex, _ = generate_persona("salaried")
    assert len([t for t in alex if t.merchant == "Meridian Ltd (salary)"]) == 6  # salaried: fixed pay


# ---- repository in mock mode (the default for every other module) ----------------------

@pytest.fixture
def mock_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MOCK_DATA", True)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "never.db"))
    yield tmp_path / "never.db"
    assert not (tmp_path / "never.db").exists()  # mock mode must never open the DB


def test_mock_mode_serves_fixtures_for_any_user_id(mock_mode):
    assert repository.get_user("anyone").id == "sam"
    assert repository.get_transactions("anyone")
    assert repository.get_pots("anyone")


def test_mock_mode_transaction_filters(mock_mode):
    all_txs = repository.get_transactions("sam")
    assert all_txs
    mid = sorted(t.date for t in all_txs)[len(all_txs) // 2]
    after = repository.get_transactions("sam", start=mid)
    before = repository.get_transactions("sam", end=mid)
    assert after and before
    assert all(t.date >= mid for t in after) and all(t.date <= mid for t in before)
    assert repository.get_transactions("sam", start=mid, end=mid) == [t for t in all_txs if t.date == mid]
    assert repository.get_transactions("sam", start=dt.date(2100, 1, 1)) == []


def test_mock_mode_add_pot_echoes_and_does_not_persist(mock_mode):
    pot = Pot(id="p-new", user_id="sam", name="Holiday", amount=50)
    assert repository.add_pot(pot) == pot
    assert "p-new" not in [p.id for p in repository.get_pots("sam")]


def test_mock_mode_has_no_households(mock_mode):
    assert repository.get_household_members("h1") == []


def test_start_after_end_returns_nothing_in_real_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MOCK_DATA", False)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "r.db"))
    from backend.data.seed import seed

    seed()
    assert repository.get_transactions("sam", start=dt.date(2026, 11, 7), end=dt.date(2026, 11, 1)) == []


# ---- the real LLM client wrapper (_call_llm) ---------------------------------------------

def test_call_llm_uses_configured_model_and_key_and_returns_text(monkeypatch):
    """Verified against a fake SDK: right constructor args, right request shape, text out."""
    seen = {}

    class FakeMessages:
        def create(self, **kwargs):
            seen["create"] = kwargs
            return types.SimpleNamespace(content=[types.SimpleNamespace(text='{"ok": true}')])

    class FakeClient:
        def __init__(self, **kwargs):
            seen["init"] = kwargs
            self.messages = FakeMessages()

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=FakeClient))
    monkeypatch.setattr(config, "LLM_API_KEY", "k-123")
    monkeypatch.setattr(config, "LLM_MODEL", "some-model")

    assert categoriser._call_llm("hello") == '{"ok": true}'
    assert seen["init"] == {"api_key": "k-123"}
    assert seen["create"]["model"] == "some-model"
    assert seen["create"]["messages"] == [{"role": "user", "content": "hello"}]
    assert isinstance(seen["create"]["max_tokens"], int) and seen["create"]["max_tokens"] > 0


def test_call_llm_request_matches_the_installed_sdk_signature():
    """If the real SDK is installed, the keyword args we pass must still exist (no network)."""
    anthropic = pytest.importorskip("anthropic")
    params = inspect.signature(anthropic.Anthropic(api_key="x").messages.create).parameters
    assert {"model", "max_tokens", "messages"} <= set(params)


def test_missing_sdk_is_handled_as_a_llm_failure(monkeypatch):
    """No SDK installed + a key set must degrade to the fallback, not crash seeding."""
    monkeypatch.setitem(sys.modules, "anthropic", None)  # makes `import anthropic` raise ImportError
    monkeypatch.setattr(config, "LLM_API_KEY", "k")
    assert categoriser.llm_label(["Boots"]) == {}
