"""Issue #3: Sam persona generator. One assertion group per planted feature."""
import datetime as dt

import pytest

from backend import config
from backend.data.generator import OPENING_BALANCE_MERCHANT, generate_persona
from contracts.schemas import Pot, Transaction, User


@pytest.fixture(scope="module")
def sam():
    return generate_persona("sam", seed=42)


def _eating_out(txs, start, end):
    return -sum(t.amount for t in txs if t.category == "eating out" and start <= t.date <= end)


def test_deterministic_for_same_seed(sam):
    assert generate_persona("sam", seed=42) == sam


def test_different_seed_differs(sam):
    assert generate_persona("sam", seed=7)[1] != sam[1]


def test_unknown_persona_raises():
    with pytest.raises(ValueError):
        generate_persona("nobody")


def test_output_types_and_ids(sam):
    user, txs, pots = sam
    assert isinstance(user, User) and user.id == "sam"
    assert all(isinstance(t, Transaction) and t.user_id == "sam" for t in txs)
    assert all(isinstance(p, Pot) and p.user_id == "sam" for p in pots)
    assert len({t.id for t in txs}) == len(txs)  # unique ids
    assert [t.date for t in txs] == sorted(t.date for t in txs)


def test_date_range_is_six_months_ending_today(sam):
    _, txs, _ = sam
    assert max(t.date for t in txs) == config.TODAY
    assert min(t.date for t in txs) == dt.date(2026, 5, 7)


def test_amount_signs_and_kinds(sam):
    _, txs, _ = sam
    for t in txs:
        if t.kind == "income":
            assert t.amount > 0 and t.category == "income"
        else:
            assert t.amount < 0 and t.kind in ("need", "want")


def test_rent_on_first_of_each_month(sam):
    _, txs, _ = sam
    rent = [t for t in txs if t.category == "housing"]
    assert [t.date for t in rent] == [dt.date(2026, m, 1) for m in range(6, 12)]
    assert all(t.amount == -475.00 for t in rent)


def test_recurring_phone_and_subscriptions(sam):
    _, txs, _ = sam
    for merchant in ("Giffgaff", "Spotify", "Netflix"):
        mine = [t for t in txs if t.merchant == merchant]
        assert len(mine) >= 5
        assert len({t.amount for t in mine}) == 1  # fixed amount
        assert len({t.date.day for t in mine}) == 1  # fixed day


def test_uni_day_food_is_10_to_15_on_tuesdays(sam):
    _, txs, _ = sam
    food = [t for t in txs if t.merchant == "Greggs (Uni)"]
    assert food and all(t.date.weekday() == 1 for t in food)
    assert all(10 <= -t.amount <= 15 for t in food)


def test_irregular_shift_income(sam):
    _, txs, _ = sam
    shifts = [t for t in txs if t.merchant == "Cafe shift pay"]
    assert len({t.amount for t in shifts}) > 10  # varying amounts
    gaps = {(b.date - a.date).days for a, b in zip(shifts, shifts[1:])}
    assert len(gaps) > 1  # varying timing


def test_eating_out_spike_in_last_7_days(sam):
    _, txs, _ = sam
    spike_start = config.TODAY - dt.timedelta(days=6)
    last_week = _eating_out(txs, spike_start, config.TODAY)
    avg = _eating_out(txs, spike_start - dt.timedelta(days=28), spike_start - dt.timedelta(days=1)) / 4
    assert last_week / avg == pytest.approx(1.6, abs=0.02)


def test_pots(sam):
    _, _, pots = sam
    by_name = {p.name: p for p in pots}
    assert by_name["December rent"].amount == 950.00
    assert by_name["December rent"].due_date == dt.date(2026, 12, 1)
    assert by_name["Emergency fund"].amount == 300.00
    assert by_name["Emergency fund"].due_date is None


def test_balance_gives_safe_to_spend_about_210(sam):
    _, txs, pots = sam
    balance = sum(t.amount for t in txs)
    assert balance == pytest.approx(1640.00, abs=0.01)
    assert balance - sum(p.amount for p in pots) - 180.00 == pytest.approx(210.00, abs=0.01)


def test_opening_balance_is_single_positive_first_row(sam):
    _, txs, _ = sam
    opening = [t for t in txs if t.merchant == OPENING_BALANCE_MERCHANT]
    assert len(opening) == 1 and opening[0].amount > 0 and opening[0] == txs[0]


@pytest.mark.parametrize("seed", range(1, 30))
def test_many_seeds_stay_valid(seed):
    """Spike and opening balance must be plantable for any seed, not just 42."""
    _, txs, _ = generate_persona("sam", seed=seed)
    assert sum(t.amount for t in txs) == pytest.approx(1640.00, abs=0.01)


# ---- helpers & edge cases -------------------------------------------------------

from backend.data import generator  # noqa: E402


@pytest.mark.parametrize(
    "d,months,expected",
    [
        (dt.date(2026, 11, 7), 6, dt.date(2026, 5, 7)),
        (dt.date(2026, 3, 31), 1, dt.date(2026, 2, 28)),  # day clamped to month end
        (dt.date(2024, 3, 31), 1, dt.date(2024, 2, 29)),  # leap year
        (dt.date(2026, 2, 15), 3, dt.date(2025, 11, 15)),  # crosses a year boundary
        (dt.date(2026, 1, 1), 12, dt.date(2025, 1, 1)),
    ],
)
def test_months_ago(d, months, expected):
    assert generator._months_ago(d, months) == expected


def test_eating_out_helper_is_inclusive_and_positive():
    d = dt.date(2026, 1, 10)
    rows = [
        (d, "A", -5.0, "eating out", "want"),
        (d + dt.timedelta(days=1), "B", -7.0, "eating out", "want"),
        (d + dt.timedelta(days=2), "C", -9.0, "groceries", "need"),
        (d + dt.timedelta(days=3), "D", -1.0, "eating out", "want"),
    ]
    assert generator._eating_out(rows, d, d + dt.timedelta(days=1)) == 12.0
    assert generator._eating_out(rows, d + dt.timedelta(days=9), d + dt.timedelta(days=10)) == 0


def test_generator_follows_config_today(monkeypatch):
    """Anchored to config.TODAY at call time (DEMO_TODAY override), incl. month-end clamping."""
    monkeypatch.setattr(config, "TODAY", dt.date(2026, 8, 31))
    _, txs, _ = generate_persona("sam")
    assert max(t.date for t in txs) == dt.date(2026, 8, 31)
    assert min(t.date for t in txs) == dt.date(2026, 2, 28)
    assert sum(t.amount for t in txs) == pytest.approx(1640.00, abs=0.01)


def test_does_not_mutate_global_random_state():
    import random

    random.seed(123)
    expected = random.random()
    random.seed(123)
    generate_persona("sam", seed=1)
    assert random.random() == expected


def test_seed_default_is_42():
    assert generate_persona("sam") == generate_persona("sam", seed=42)


def test_spike_guard_raises_when_not_plantable(monkeypatch):
    monkeypatch.setattr(generator, "SPIKE_FACTOR", 0)
    with pytest.raises(ValueError, match="spike"):
        generate_persona("sam")


def test_opening_balance_guard_raises_when_non_positive(monkeypatch):
    monkeypatch.setattr(generator, "TARGET_BALANCE", -10_000.0)
    with pytest.raises(ValueError, match="opening balance"):
        generate_persona("sam")


def test_amounts_have_at_most_two_decimals(sam):
    _, txs, _ = sam
    assert all(round(t.amount, 2) == t.amount for t in txs)


def test_user_matches_expected_profile(sam):
    user, _, _ = sam
    assert (user.id, user.name, user.region, user.household_id, user.tone) == (
        "sam", "Sam", "Manchester", None, "friendly",
    )
