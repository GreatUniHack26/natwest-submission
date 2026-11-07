"""Issue #42 integration: goal planner through the public data/forecast interfaces."""
import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

import pytest

from backend import config, data
from backend.data import categoriser, repository
from backend.data.seed import seed
from backend.planner import GoalPlan, plan_emergency_fund, plan_goal
from contracts.schemas import Pot

TARGET_DATE = dt.date(2027, 11, 7)


# ---- (a) mock mode: default flags, fixtures through the public interfaces ----------------
def test_mock_mode_fixture_forecast_is_infeasible_with_explanation():
    # Fixture forecast: expected balance falls 1640 -> 60 over 56 days, so nothing is spare.
    p = plan_goal("sam", 1200, TARGET_DATE)
    assert isinstance(p, GoalPlan)
    assert not p.feasible and p.reason == "exceeds_surplus"
    assert p.required_monthly == 100.0 and p.available_monthly == 0.0 and p.shortfall == 100.0
    assert "100.00" in p.explanation and "short" in p.explanation
    assert p.suggested_pot is None  # only suggested for an affordable goal


def test_mock_mode_existing_named_pot_is_credited():
    # Fixture pot "Emergency fund" holds 300; a 300 goal of that name is already funded.
    p = plan_goal("sam", 300, TARGET_DATE, goal_name="Emergency fund")
    assert p.feasible and p.reason == "already_funded" and p.required_monthly == 0
    assert p.suggested_pot is None


def test_mock_mode_validation_and_no_persistence():
    with pytest.raises(ValueError):
        plan_goal("sam", 0, TARGET_DATE)
    with pytest.raises(ValueError):
        plan_goal("sam", 100, config.TODAY)
    before = data.get_pots("sam")
    plan_goal("sam", 1200, TARGET_DATE)
    assert data.get_pots("sam") == before


def test_mock_mode_emergency_fund_without_complete_months_is_infeasible_not_a_crash():
    # Fixture transactions are 6 days of November only: no complete month of history.
    r = plan_emergency_fund("sam")
    assert not r.feasible and r.reason == "no_history" and r.explanation


# ---- (b) real data in a tmp DB -------------------------------------------------------------
@pytest.fixture
def real(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MOCK_DATA", False)
    monkeypatch.setattr(config, "MOCK_FORECAST", False)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "goal.db"))
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    monkeypatch.setattr(categoriser, "CACHE_PATH", tmp_path / "cache.json")
    monkeypatch.setattr(repository, "get_balance", lambda uid, as_of: 1000.0, raising=False)
    seed()


def _independent_target(uid):
    """3 x average need-spend over the complete months Jun..Oct 2026 (history starts May 7)."""
    needs = [t for t in repository.get_transactions(uid) if t.kind == "need" and t.amount < 0]
    in_window = [-Decimal(str(t.amount)) for t in needs if dt.date(2026, 6, 1) <= t.date <= dt.date(2026, 10, 31)]
    avg = (sum(in_window, Decimal(0)) / 5).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return avg, float(avg * 3)


@pytest.mark.parametrize("uid", ["maya", "sam"])
def test_emergency_target_matches_independent_need_average(real, uid):
    avg, target = _independent_target(uid)
    assert avg > 0
    r = plan_emergency_fund(uid)
    assert r.window_months == 5
    assert r.monthly_essentials == float(avg)
    assert r.target_amount == pytest.approx(target, abs=0.011)
    assert r.explanation and r.plan is not None
    # existing "Emergency fund" pot is credited
    pot = next(p for p in repository.get_pots(uid) if p.name == "Emergency fund")
    assert r.plan.already_saved == pot.amount
    assert r.plan.remaining == pytest.approx(r.target_amount - pot.amount, abs=0.011)
    assert r.plan.suggested_pot is None  # pot already exists: top it up instead


def test_emergency_target_for_a_user_without_a_pot_suggests_one(real):
    r = plan_emergency_fund("dan")
    assert r.target_amount > 0 and r.plan.already_saved == 0
    if r.feasible:
        pot = r.plan.suggested_pot
        assert pot.due_date is None and pot.id == "dan-emergency-fund" and pot.name == "Emergency fund"
        assert pot.amount == r.plan.required_monthly
    else:
        assert r.plan.suggested_pot is None and r.explanation


def test_real_forecast_goal_plan_is_consistent(real):
    p = plan_goal("sam", 600, TARGET_DATE)
    assert p.required_monthly == 50.0 and p.months == 12 and p.explanation
    if p.feasible:
        assert p.required_monthly <= p.available_monthly and p.low_band_gap == 0
    else:
        assert p.reason in ("exceeds_surplus", "breaches_low_band") and p.explanation


def test_suggested_pot_validates_and_persists_via_add_pot(real, monkeypatch):
    # Make the forecast clearly affordable so a pot is suggested.
    from backend import forecast as fc
    from contracts.schemas import Forecast, ForecastPoint

    pts = [ForecastPoint(date=config.TODAY, low=1000, expected=1000, high=1000),
           ForecastPoint(date=config.TODAY + dt.timedelta(days=90), low=1000, expected=2000, high=2000)]
    monkeypatch.setattr(fc, "forecast", lambda uid, h, overrides=None: Forecast(
        user_id=uid, horizon_days=h, points=pts, risk_events=[]))
    p = plan_goal("sam", 1200, TARGET_DATE, goal_name="Holiday")
    assert p.feasible and p.suggested_pot is not None
    pot = Pot.model_validate(p.suggested_pot.model_dump())
    assert pot.id == "sam-goal-holiday" and pot.user_id == "sam"
    assert pot.due_date == TARGET_DATE and pot.amount == 100.0

    assert pot not in data.get_pots("sam")  # planning persisted nothing
    data.add_pot(pot)
    assert pot in data.get_pots("sam")
    with pytest.raises(ValueError):
        data.add_pot(pot)  # second add of the same id is rejected

    # Now the pot exists (amount 100): it is credited and no new pot is suggested.
    again = plan_goal("sam", 1200, TARGET_DATE, goal_name="Holiday")
    assert again.already_saved == 100.0 and again.suggested_pot is None


def test_forecast_failure_is_reported_not_raised(real, monkeypatch):
    from backend import forecast as fc

    def boom(*a, **k):
        raise RuntimeError("no balance source")

    monkeypatch.setattr(fc, "forecast", boom)
    p = plan_goal("sam", 1200, TARGET_DATE)
    assert not p.feasible and p.reason == "no_forecast" and "no usable forecast" in p.explanation
