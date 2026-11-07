"""Generated Sam -> real SQLite -> real forecast math -> real HTTP responses.

These are seeded-data integration assertions, not fixture or mocked-engine tests.
"""
import datetime as dt
from copy import deepcopy
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend import config, forecast
from backend.data import repository
from backend.data.generator import generate_persona
from backend.data.seed import seed
from backend.forecast.engine import project
from backend.forecast.inputs import load_inputs
from backend.forecast.simulate import risk_onsets
from backend.main import app

TODAY = dt.date(2026, 11, 7)


@pytest.fixture
def real_sam(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'MOCK_DATA', False)
    monkeypatch.setattr(config, 'MOCK_FORECAST', False)
    monkeypatch.setattr(config, 'TODAY', TODAY)
    monkeypatch.setattr(config, 'DB_PATH', str(tmp_path / 'sam-demo.db'))
    # Every generated merchant has a rule; seeding needs no LLM/key/network.
    monkeypatch.setattr(config, 'LLM_API_KEY', '')
    seed()
    return TestClient(app)


def test_actual_seeded_demo_has_independently_reconciled_safe_budget(real_sam):
    safe = forecast.safe_to_spend('sam', TODAY)
    # Three bills before/on the fixed stipend date, independent of forecast code.
    expected_bills = Decimal('15') + Decimal('154.01') + Decimal('10.99')
    assert expected_bills == 180
    assert (safe.balance, safe.pots_total, safe.upcoming_bills, safe.safe_amount) == (1640, 1250, 180, 210)
    assert sum(round(line.amount * 100) for line in safe.breakdown) == 21000
    response = real_sam.get('/users/sam/safe-to-spend')
    assert response.status_code == 200 and response.json()['safe_amount'] == 210


def test_actual_seeded_demo_purchase_and_december_risk(real_sam):
    verdict = forecast.simulate_purchase('sam', 30, TODAY)
    assert verdict.affordable is True
    assert verdict.safe_after == 180
    assert verdict.better_date == dt.date(2026, 11, 27)
    assert verdict.numbers_used == {'price': 30, 'safe_to_spend': 210, 'safe_after': 180}
    data = load_inputs('sam', TODAY)
    before = deepcopy(data)
    baseline = project(data, 90)
    with_shirt = project(data, 90, one_off={TODAY: 3000})
    assert risk_onsets(data, baseline) == risk_onsets(data, with_shirt)
    assert data == before
    result = forecast.forecast('sam', 90)
    assert next(event.date for event in result.risk_events if event.severity == 'high') == dt.date(2026, 12, 26)
    assert next(p.expected for p in baseline if p.date == dt.date(2026, 12, 25)) > 0
    assert next(p.expected for p in baseline if p.date == dt.date(2026, 12, 26)) < 0
    response = real_sam.post('/users/sam/simulate', json={'amount': 30})
    assert response.status_code == 200
    assert response.json()['affordable'] is True and response.json()['safe_after'] == 180


def test_actual_seeded_spike_crosses_alert_threshold(real_sam):
    rows = repository.get_transactions('sam')
    start = TODAY - dt.timedelta(days=6)
    def spend(begin, end):
        return -sum(Decimal(str(t.amount)) for t in rows if t.category == 'eating out' and begin <= t.date <= end)
    actual = spend(start, TODAY)
    previous_mean = spend(start-dt.timedelta(days=28), start-dt.timedelta(days=1)) / 4
    assert float(actual / previous_mean) == pytest.approx(1.6, abs=.02)
    alerts = forecast.detect_alerts('sam')
    assert any(a.type == 'sudden_change' and a.category == 'eating out' for a in alerts)
    response = real_sam.get('/users/sam/alerts')
    assert response.status_code == 200
    assert any(a['type'] == 'sudden_change' and a['category'] == 'eating out' for a in response.json())


def test_planted_calendar_transactions_explain_reservation_and_stress(real_sam):
    rows = repository.get_transactions('sam')
    for merchant, amount, day in [('Study stipend',150,20), ('Octopus Energy',-154.01,15), ('Course fee instalment',-800,26)]:
        matching = [t for t in rows if t.merchant == merchant]
        assert len(matching) >= 5
        assert {t.amount for t in matching} == {amount}
        assert {t.date.day for t in matching} == {day}
    assert generate_persona('sam',42) == generate_persona('sam',42)
