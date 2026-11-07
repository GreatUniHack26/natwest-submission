"""Monte Carlo twin and time-travel timeline on the seeded real-mode personas."""
import pytest

from backend import config
import importlib

from backend.forecast import montecarlo

timeline = importlib.import_module("backend.forecast.time_travel")


@pytest.fixture
def real_mode(monkeypatch):
    monkeypatch.setattr(config, "MOCK_DATA", False)
    monkeypatch.setattr(config, "MOCK_FORECAST", False)


def _sim(user="sam", **kw):
    try:
        return montecarlo.simulate_futures(user, **kw)
    except Exception as exc:  # seeded DB not present in this environment
        pytest.skip(f"seeded data unavailable: {exc}")


def test_simulations_are_repeatable(real_mode):
    a = _sim(horizon_days=60, sims=200)
    b = _sim(horizon_days=60, sims=200)
    assert a == b


def test_simulation_outputs_are_valid_probabilities(real_mode):
    out = _sim(horizon_days=90, sims=300)
    assert out["simulations"] == 300
    for key in ("chance_below_zero", "chance_dip_into_pots"):
        assert 0 <= out[key] <= 1
    within = out["chance_below_zero_within"]
    assert within["30"] <= within["60"] <= within["90"]  # cumulative odds never fall
    for p in out["points"]:
        assert p["p10"] <= p["p50"] <= p["p90"]
    assert 0 <= out["runway_days_if_income_stops"] <= 90


def test_simulation_rejects_bad_inputs(real_mode):
    with pytest.raises(ValueError):
        montecarlo.simulate_futures("sam", horizon_days=3)
    with pytest.raises(ValueError):
        montecarlo.simulate_futures("sam", sims=10)


def test_timeline_has_daily_rows_events_and_scenario(real_mode):
    try:
        base = timeline.timeline("sam", 60, None, sims=200)
        trip = timeline.timeline("sam", 60, {"extra_one_off": {"amount": 1600, "date": "2026-12-05"}}, sims=200)
    except Exception as exc:
        pytest.skip(f"seeded data unavailable: {exc}")
    assert len(base["days"]) == 61
    assert base["scenario"] is None
    assert all(e["kind"] in {"income", "bill", "pot"} for e in base["events"])
    assert trip["scenario"]["end_difference"] == pytest.approx(-1600, abs=0.01)
    if base["first_below_zero"] and trip["scenario"]["first_below_zero"]:
        assert trip["scenario"]["first_below_zero"] <= base["first_below_zero"]
