import datetime as dt
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from backend import config, forecast
from backend.data import repository
from backend.forecast.engine import build_forecast
from backend.main import app
from contracts.schemas import Forecast
from tests.forecast.test_recurring import txs

TODAY = dt.date(2026,11,7)


def cashflows(ledger):
    ledger['balance'] = 100
    ledger['transactions'] = txs(['2026-10-18','2026-10-25','2026-11-01'],[-30]*3)
    ledger['transactions'] += txs(['2026-10-19','2026-10-26','2026-11-02'],[20]*3,merchant='Pay')


def test_independent_outcomes_and_composition(ledger):
    cashflows(ledger)
    before = deepcopy(ledger)
    baseline = forecast.forecast('sam',35)
    assert baseline.points[-1].expected == 50  # 100 + 5*20 - 5*30
    reduced = forecast.forecast('sam',35,{'income_multiplier':.5})
    assert reduced.points[-1].expected == 0  # 100 + 5*10 - 5*30
    monthly = forecast.forecast('sam',35,{'extra_monthly_cost':15})
    assert monthly.points[-1].expected == 35  # first charge Dec7 only
    oneoff = forecast.forecast('sam',35,{'extra_one_off':{'amount':7,'date':'2026-11-15'}})
    assert oneoff.points[-1].expected == 43
    combined = forecast.forecast('sam',35,{'income_multiplier':.5,'extra_monthly_cost':15,'extra_one_off':{'amount':7,'date':'2026-11-15'}})
    assert combined.points[-1].expected == -22
    assert any('Scenario:' in a for a in combined.assumptions)
    assert ledger == before


def test_job_loss_advances_risk(ledger):
    cashflows(ledger)
    base = forecast.forecast('sam',90)
    lost = forecast.forecast('sam',90,{'income_multiplier':0})
    baseline_date = next(e.date for e in base.risk_events if e.severity == 'high')
    lost_date = next(e.date for e in lost.risk_events if e.severity == 'high')
    assert baseline_date == dt.date(2027,1,3)
    assert lost_date == dt.date(2026,11,29)
    assert lost_date < baseline_date


def test_zero_defaults_unknown_keys_and_no_mutation(ledger):
    cashflows(ledger)
    before = deepcopy(ledger)
    baseline = forecast.forecast('sam',35)
    assert forecast.forecast('sam',35,{'income_multiplier':1,'extra_monthly_cost':0,'extra_one_off':0,'unknown':99}) == baseline
    assert forecast.forecast('sam',35,{'extra_one_off':[]}) == baseline
    assert ledger == before


def test_dated_costs_apply_once_compose_and_cover_boundaries(ledger):
    result = forecast.forecast('sam',7,{'extra_one_off':[{'amount':10,'date':str(TODAY)},{'amount':20,'date':'2026-11-14'},{'amount':3,'date':'2026-11-14'}]})
    assert result.points[0].expected == 1630
    assert result.points[-1].expected == 1607
    assert forecast.forecast('sam',7,{'extra_one_off':10}).points[0].expected == 1630


def test_monthly_anniversaries_do_not_drift_after_february(ledger):
    result = build_forecast('sam',90,{'extra_monthly_cost':10},as_of=dt.date(2027,1,30))
    # Feb28, Mar30 and Apr30 fall within the 90-day horizon.
    assert result.points[-1].date == dt.date(2027,4,30)
    assert result.points[-1].expected == 1610


@pytest.mark.parametrize('overrides',[
    {'income_multiplier':True},{'income_multiplier':-1},{'income_multiplier':11},{'income_multiplier':float('inf')},
    {'income_multiplier':'1'},{'extra_monthly_cost':False},{'extra_monthly_cost':-1},{'extra_monthly_cost':float('nan')},
    {'extra_monthly_cost':1e10},{'extra_one_off':True},{'extra_one_off':-1},{'extra_one_off':float('inf')},
    {'extra_one_off':{'amount':10}},{'extra_one_off':{'amount':True,'date':'2026-11-08'}},
    {'extra_one_off':{'amount':10,'date':'bad'}},{'extra_one_off':{'amount':10,'date':'2026-11-06'}},
    {'extra_one_off':{'amount':10,'date':'2027-01-01'}},{'extra_one_off':['bad']},
])
def test_invalid_recognized_values(ledger,overrides):
    with pytest.raises(ValueError): forecast.forecast('sam',35,overrides)


def test_what_if_endpoint_numbers_schema_and_comparison(ledger):
    cashflows(ledger)
    client = TestClient(app)
    normal = client.get('/users/sam/forecast?days=35')
    scenario = client.post('/users/sam/forecast/what-if',json={'days':35,'overrides':{'income_multiplier':.5,'extra_monthly_cost':15}})
    assert normal.status_code == scenario.status_code == 200
    assert normal.json()['points'][-1]['expected'] == 50
    assert scenario.json()['points'][-1]['expected'] == -15
    assert Forecast.model_validate(scenario.json()).risk_events
    assert client.post('/users/sam/simulate',json={'amount':0}).status_code == 200


def test_endpoint_validation_and_errors(ledger,monkeypatch):
    client = TestClient(app)
    for body in [{'days':6},{'days':366},{'days':True},{'overrides':[]},{'overrides':{'income_multiplier':True}}, {'overrides':{'extra_one_off':{'amount':2,'date':'bad'}}}]:
        assert client.post('/users/sam/forecast/what-if',json=body).status_code == 422
    monkeypatch.setattr(config,'MOCK_FORECAST',True)
    assert client.post('/users/sam/forecast/what-if',json={}).status_code == 503
    monkeypatch.setattr(config,'MOCK_FORECAST',False)
    monkeypatch.delattr(repository,'get_balance')
    assert client.post('/users/sam/forecast/what-if',json={}).status_code == 503
