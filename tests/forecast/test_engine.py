import datetime as dt
from copy import deepcopy

import pytest

from backend import forecast
from backend.data import repository
from backend.forecast.engine import build_forecast, project
from backend.forecast.inputs import ForecastDataUnavailable, load_inputs
from contracts.schemas import Forecast, Pot
from tests.forecast.test_recurring import txs


def test_daily_cashflow_and_endpoint(ledger):
    ledger['balance'] = 100
    ledger['transactions'] = txs(['2026-10-18','2026-10-25','2026-11-01'], [-20]*3)
    data = load_inputs('sam', dt.date(2026,11,7))
    daily = project(data, 10)
    assert daily[0].expected == 100
    assert daily[1].expected == 80
    assert daily[8].expected == 60
    result = forecast.forecast('sam', 10)
    assert [p.date for p in result.points] == [dt.date(2026,11,7),dt.date(2026,11,14),dt.date(2026,11,17)]
    assert result.points[-1].expected == 60
    assert Forecast.model_validate(result.model_dump()) == result


def test_risks_between_weekly_points_deduplicated(ledger):
    ledger['balance'] = 10
    ledger['transactions'] = txs(['2026-10-18','2026-10-25','2026-11-01'], [-20]*3)
    result = forecast.forecast('sam', 14)
    assert next(e.date for e in result.risk_events if e.severity == 'high') == dt.date(2026,11,8)
    assert len(result.risk_events) == 2


def test_bands_determinism_and_no_mutation(ledger):
    ledger['transactions'] = txs(['2026-10-18','2026-10-25','2026-11-01'], [10,20,30])
    before = deepcopy(ledger)
    a = forecast.forecast('sam', 60, {'unrecognised': 42})
    assert a == forecast.forecast('sam', 60)
    assert ledger == before
    assert all(p.low <= p.expected <= p.high for p in a.points)
    assert a.points[1].low < a.points[1].expected < a.points[1].high


def test_pot_risk_and_empty_history(ledger):
    ledger['pots'] = [Pot(id='p',user_id='sam',name='Emergency',amount=1700)]
    result = forecast.forecast('sam', 7)
    assert result.risk_events[0].severity == 'medium'
    assert result.risk_events[0].date == dt.date(2026,11,7)
    assert any('No historical' in a for a in result.assumptions)


@pytest.mark.parametrize('horizon', [0,6,366,True,7.5])
def test_invalid_horizon(ledger, horizon):
    with pytest.raises(ValueError): forecast.forecast('sam', horizon)


def test_authoritative_balance_is_required(ledger, monkeypatch):
    monkeypatch.delattr(repository, 'get_balance')
    with pytest.raises(ForecastDataUnavailable, match='authoritative balance'):
        forecast.forecast('sam')


def test_foreign_financial_data_rejected(ledger):
    ledger['transactions'] = txs(['2026-11-01'], user='other')
    with pytest.raises(ValueError, match='another user'): forecast.forecast('sam')


def test_controlled_december_risk_without_persona_or_date_logic(ledger):
    # £1,640 opening, £250 weekly bills: first negative after seven Fridays.
    ledger['transactions'] = txs(['2026-10-16','2026-10-23','2026-10-30'], [-250]*3)
    result = build_forecast('sam', 60, {})
    assert next(e.date for e in result.risk_events if e.severity == 'high') == dt.date(2026,12,25)
