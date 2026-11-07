"""Issue #4 unit tests: 'salaried' persona and the 'family' household."""
import datetime as dt
import sqlite3

import pytest

from backend import config
from backend.data.generator import (
    HOUSEHOLDS, OPENING_BALANCE_MERCHANT, generate_household, generate_persona,
)
from contracts.schemas import Pot, Transaction, User


@pytest.fixture(scope="module")
def family():
    return generate_household("family", seed=42)


@pytest.fixture(scope="module")
def salaried():
    return generate_persona("salaried", seed=42)


def _by_id(family):
    return {u.id: (u, t, p) for u, t, p in family}


def _window(txs, days):
    start = config.TODAY - dt.timedelta(days=days - 1)
    return [t for t in txs if start <= t.date <= config.TODAY and t.merchant != OPENING_BALANCE_MERCHANT]


# ---- API shape -------------------------------------------------------------------

def test_family_through_generate_persona_points_to_generate_household():
    with pytest.raises(ValueError, match="generate_household"):
        generate_persona("family")


def test_unknown_household_raises():
    with pytest.raises(ValueError):
        generate_household("nobody")


def test_all_households_are_generatable():
    for name in HOUSEHOLDS:
        assert generate_household(name)


def test_sam_is_unchanged_by_new_personas():
    user, txs, pots = generate_persona("sam", 42)
    assert (user.id, len(txs), len(pots)) == ("sam", 235, 2)


# ---- family: structure -------------------------------------------------------------

def test_family_deterministic_and_seed_sensitive(family):
    assert generate_household("family", seed=42) == family
    assert generate_household("family", seed=7) != family


def test_two_adults_share_one_household(family):
    users = [u for u, _, _ in family]
    assert len(users) == 2 and all(isinstance(u, User) for u in users)
    assert {u.household_id for u in users} == {"h1"}
    assert len({u.id for u in users}) == 2
    assert {u.region for u in users} == {"Leeds"}


def test_each_member_has_own_transactions(family):
    for user, txs, _ in family:
        assert txs and all(isinstance(t, Transaction) and t.user_id == user.id for t in txs)
        assert len({t.id for t in txs}) == len(txs)
        assert [t.date for t in txs] == sorted(t.date for t in txs)
    all_ids = [t.id for _, txs, _ in family for t in txs]
    assert len(all_ids) == len(set(all_ids))  # unique across the household


def test_shared_pots_have_exactly_one_owner(family):
    """Household aggregation rejects duplicate pot ids; pots live on the first adult only."""
    (u1, _, p1), (u2, _, p2) = family
    assert p1 and all(isinstance(p, Pot) and p.user_id == u1.id for p in p1)
    assert p2 == []
    ids = [p.id for _, _, pots in family for p in pots]
    assert len(ids) == len(set(ids))


def test_pots_are_in_the_future(family):
    for _, _, pots in family:
        assert all(p.due_date is None or p.due_date > config.TODAY for p in pots)


def test_balances_hit_targets_and_are_tight(family):
    totals = {u.id: sum(t.amount for t in txs) for u, txs, _ in family}
    assert totals["maya"] == pytest.approx(1200.00, abs=0.01)
    assert totals["dan"] == pytest.approx(220.00, abs=0.01)
    pots_total = sum(p.amount for _, _, pots in family for p in pots)
    assert 0 < sum(totals.values()) - pots_total < 600  # tight margin


def test_six_months_ending_today_with_one_opening_row_each(family):
    for _, txs, _ in family:
        assert max(t.date for t in txs) == config.TODAY
        assert min(t.date for t in txs) == dt.date(2026, 5, 7)
        assert sum(1 for t in txs if t.merchant == OPENING_BALANCE_MERCHANT) == 1


def test_amount_signs_and_kinds(family):
    for _, txs, _ in family:
        for t in txs:
            if t.kind == "income":
                assert t.amount > 0 and t.category == "income"
            else:
                assert t.amount < 0 and t.kind in ("need", "want")


# ---- family: content --------------------------------------------------------------

def test_family_has_school_childcare_and_a_recurring_debt(family):
    txs = [t for _, ts, _ in family for t in ts]
    categories = {t.category for t in txs}
    assert {"childcare", "school", "debt"} <= categories
    loan = [t for t in txs if t.merchant == "Provident Loan"]
    assert len(loan) >= 5 and {t.amount for t in loan} == {-85.00}
    gaps = [(b.date - a.date).days for a, b in zip(loan, loan[1:])]
    assert all(28 <= g <= 31 for g in gaps)  # detectable as monthly recurring


def test_income_is_irregular_and_low(family):
    for uid in ("maya", "dan"):
        pay = [t.amount for t in _by_id(family)[uid][1] if "shifts" in t.merchant or "Agency" in t.merchant]
        assert pay and max(pay) / min(pay) > 1.5  # not mistakable for a fixed salary
    txs = [t for _, ts, _ in family for t in ts]
    monthly = sum(t.amount for t in txs if t.kind == "income" and t.merchant != OPENING_BALANCE_MERCHANT) / 6
    assert monthly < 2300


def test_rent_paid_on_the_first_each_month(family):
    rent = [t for _, ts, _ in family for t in ts if t.category == "housing"]
    assert [t.date for t in rent] == [dt.date(2026, m, 1) for m in range(6, 12)]


# ---- family: planted risk ------------------------------------------------------------

def test_second_adults_hours_were_cut(family):
    dan = _by_id(family)["dan"][1]
    pay = lambda a, b: sum(t.amount for t in dan if t.merchant == "Agency work pay" and a <= t.date <= b)
    before = pay(dt.date(2026, 6, 1), dt.date(2026, 9, 30)) / 4
    after = pay(config.TODAY - dt.timedelta(days=29), config.TODAY)
    assert after < 0.5 * before


def test_recent_essentials_exceed_recent_income(family):
    """Planted risk: in the last 30 days essentials outrun income by a clear margin."""
    recent = _window([t for _, ts, _ in family for t in ts], 30)
    income = sum(t.amount for t in recent if t.kind == "income")
    needs = -sum(t.amount for t in recent if t.kind == "need")
    assert needs - income > 300


def test_earlier_months_were_roughly_sustainable(family):
    """The shortfall is a change, not the baseline: Jul-Sep income covers >=90% of essentials."""
    txs = [t for _, ts, _ in family for t in ts
           if dt.date(2026, 7, 1) <= t.date <= dt.date(2026, 9, 30) and t.merchant != OPENING_BALANCE_MERCHANT]
    income = sum(t.amount for t in txs if t.kind == "income")
    needs = -sum(t.amount for t in txs if t.kind == "need")
    assert income >= 0.9 * needs


@pytest.mark.parametrize("seed", [1, 7, 42, 99, 2026])
def test_family_generates_for_many_seeds(seed):
    members = generate_household("family", seed)
    assert all(sum(t.amount for t in txs) > 0 for _, txs, _ in members)


# ---- salaried -------------------------------------------------------------------------

def test_salaried_identity(salaried):
    user, txs, pots = salaried
    assert (user.id, user.household_id, user.region) == ("alex", None, "Bristol")
    assert all(t.user_id == "alex" for t in txs) and all(p.user_id == "alex" for p in pots)
    assert len({t.id for t in txs}) == len(txs)


def test_salaried_deterministic(salaried):
    assert generate_persona("salaried", 42) == salaried
    assert generate_persona("salaried", 7)[1] != salaried[1]


def test_salary_is_fixed_and_monthly(salaried):
    _, txs, _ = salaried
    salary = [t for t in txs if t.merchant == "Meridian Ltd (salary)"]
    assert [t.date for t in salary] == [dt.date(2026, m, 28) for m in range(5, 11)]
    assert {t.amount for t in salary} == {2350.00}


def test_salaried_income_merchants_are_only_salary_and_opening(salaried):
    _, txs, _ = salaried
    assert {t.merchant for t in txs if t.kind == "income"} == {OPENING_BALANCE_MERCHANT, "Meridian Ltd (salary)"}


def test_salaried_is_comfortable(salaried):
    _, txs, pots = salaried
    balance = sum(t.amount for t in txs)
    assert balance == pytest.approx(5200.00, abs=0.01)
    assert balance - sum(p.amount for p in pots) > 1500
    recent = _window(txs, 30)
    assert sum(t.amount for t in recent if t.kind == "income") > -sum(t.amount for t in recent if t.kind != "income")


def test_salaried_fixed_bills_monthly(salaried):
    _, txs, _ = salaried
    for merchant in ("Bristol Lettings (rent)", "EE", "Octopus Energy", "Spotify"):
        mine = [t for t in txs if t.merchant == merchant]
        assert len(mine) >= 5
        gaps = [(b.date - a.date).days for a, b in zip(mine, mine[1:])]
        assert all(28 <= g <= 31 for g in gaps), (merchant, gaps)


# ---- architecture rule ---------------------------------------------------------------

def test_new_generators_never_touch_the_database(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise AssertionError("generator opened a database")

    monkeypatch.setattr(sqlite3, "connect", boom)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "nope.db"))
    generate_persona("salaried")
    generate_household("family")
    assert not (tmp_path / "nope.db").exists()
