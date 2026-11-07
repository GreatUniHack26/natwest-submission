"""Issue #3 integration: generated Sam data flowing through the modules that consume it."""
import datetime as dt
import json
import sqlite3
from pathlib import Path

import pytest

from backend import config
from backend.data.categoriser import RULES, categorise
from backend.data.generator import OPENING_BALANCE_MERCHANT, generate_persona
from contracts import schemas

FIXTURES = Path(__file__).parent.parent / "contracts" / "fixtures"


def _fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.fixture(scope="module")
def sam():
    return generate_persona("sam", seed=42)


# ---- contracts ------------------------------------------------------------------

def test_json_round_trip_preserves_everything(sam):
    """What the repository will do: serialise rows out, parse them back."""
    user, txs, pots = sam
    assert schemas.User.model_validate_json(user.model_dump_json()) == user
    assert [schemas.Transaction.model_validate_json(t.model_dump_json()) for t in txs] == txs
    assert [schemas.Pot.model_validate_json(p.model_dump_json()) for p in pots] == pots


def test_revalidates_against_contract_models(sam):
    user, txs, pots = sam
    schemas.User(**user.model_dump())
    for t in txs:
        schemas.Transaction(**t.model_dump())
    for p in pots:
        schemas.Pot(**p.model_dump())


def test_matches_mock_fixture_profile(sam):
    """MOCK_DATA=0 and =1 must tell the same story to the frontend."""
    user, txs, pots = sam
    fx_user = schemas.User(**_fixture("user"))
    assert user == fx_user
    fx_pots = {(p["name"], p["amount"], p["due_date"]) for p in _fixture("pots")}
    assert {(p.name, p.amount, p.due_date.isoformat() if p.due_date else None) for p in pots} == fx_pots
    fx_rent = next(t for t in _fixture("transactions") if t["category"] == "housing")
    assert {t.amount for t in txs if t.category == "housing"} == {fx_rent["amount"]}
    fixture_pairs = {(t["category"], t["kind"]) for t in _fixture("transactions")}
    assert fixture_pairs <= {(t.category, t.kind) for t in txs}


def test_safe_to_spend_arithmetic_matches_fixture(sam):
    """Inputs P2's compute_safe_to_spend will derive from our data equal the fixture card."""
    _, txs, pots = sam
    fx = _fixture("safe_to_spend")
    balance = sum(t.amount for t in txs)
    pots_total = sum(p.amount for p in pots)
    assert balance == pytest.approx(fx["balance"], abs=0.01)
    assert pots_total == fx["pots_total"]
    assert balance - pots_total - fx["upcoming_bills"] == pytest.approx(fx["safe_amount"], abs=0.01)


def test_no_future_transactions_and_no_pot_in_past(sam):
    _, txs, pots = sam
    assert all(t.date <= config.TODAY for t in txs)
    assert all(p.due_date is None or p.due_date > config.TODAY for p in pots)


# ---- categoriser ----------------------------------------------------------------

def test_categoriser_preserves_income_and_count(sam):
    _, txs, _ = sam
    out = categorise(txs)
    assert len(out) == len(txs)
    for before, after in zip(txs, out):
        assert (after.id, after.date, after.amount, after.merchant) == (
            before.id, before.date, before.amount, before.merchant,
        )
        if before.amount > 0:
            assert (after.category, after.kind) == ("income", "income")


def test_categoriser_agrees_with_generator_labels_where_rules_exist(sam):
    """Labels we plant must not be contradicted by the rules that already exist."""
    _, txs, _ = sam
    covered = [
        t for t in txs
        if t.amount < 0 and t.merchant != "Netflix" and any(k in t.merchant.lower() for k in RULES)
    ]
    assert covered, "expected rule-covered merchants"
    out = {t.id: t for t in categorise(covered)}
    for t in covered:
        assert (out[t.id].category, out[t.id].kind) == (t.category, t.kind), t.merchant


def test_netflix_is_not_mistaken_for_transport(sam):
    _, txs, _ = sam
    netflix = [t for t in txs if t.merchant == "Netflix"]
    assert netflix and all(t.category == "subscriptions" for t in categorise(netflix))


def test_every_generated_merchant_has_a_rule(sam):
    _, txs, _ = sam
    uncovered = {t.merchant for t in txs if t.amount < 0 and not any(k in t.merchant.lower() for k in RULES)}
    assert not uncovered, uncovered


# ---- downstream expectations ----------------------------------------------------

def test_fixed_bills_are_monthly_and_detectable(sam):
    """P2's detect_recurring needs >=3 occurrences, +-10% amount, ~monthly gaps (28-31 days)."""
    _, txs, _ = sam
    for merchant in ("Landlord (rent)", "Giffgaff", "Spotify", "Netflix"):
        mine = [t for t in txs if t.merchant == merchant]
        assert len(mine) >= 3
        gaps = [(b.date - a.date).days for a, b in zip(mine, mine[1:])]
        assert all(28 <= g <= 31 for g in gaps), (merchant, gaps)


def test_shift_income_is_not_confusable_with_a_fixed_salary(sam):
    """Irregular income must not look like a stable recurring amount."""
    _, txs, _ = sam
    amounts = [t.amount for t in txs if t.merchant == "Cafe shift pay"]
    assert max(amounts) / min(amounts) > 1.5


def test_opening_balance_stipend_and_shift_income_are_distinct(sam):
    """A fixed study stipend is separate from irregular shift receipts and savings."""
    _, txs, _ = sam
    merchants = {t.merchant for t in txs if t.kind == "income"}
    assert merchants == {OPENING_BALANCE_MERCHANT, "Cafe shift pay", "Study stipend"}
    stipend = [t for t in txs if t.merchant == "Study stipend"]
    assert {t.amount for t in stipend} == {150}
    assert {t.date.day for t in stipend} == {20}


def test_alert_window_sees_the_spike(sam):
    """Alerts module compares last 7 days vs prior 4-week weekly average (+~60%)."""
    _, txs, _ = sam
    today = config.TODAY

    def spent(a, b):
        return -sum(t.amount for t in txs if t.category == "eating out" and a <= t.date <= b)

    this_week = spent(today - dt.timedelta(days=6), today)
    avg = spent(today - dt.timedelta(days=34), today - dt.timedelta(days=7)) / 4
    assert 0.55 <= this_week / avg - 1 <= 0.65


# ---- architecture rule ----------------------------------------------------------

def test_generator_never_touches_the_database(monkeypatch, tmp_path):
    """Only repository.py may touch the DB: generating must not open sqlite or create DB_PATH."""
    def boom(*a, **k):
        raise AssertionError("generator opened a database")

    monkeypatch.setattr(sqlite3, "connect", boom)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "should_not_exist.db"))
    generate_persona("sam")
    assert not (tmp_path / "should_not_exist.db").exists()
