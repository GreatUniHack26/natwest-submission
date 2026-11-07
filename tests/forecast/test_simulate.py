import datetime as dt
import json
from copy import deepcopy

import pytest

from backend import forecast
from backend.forecast import sales
from backend.forecast.engine import project
from backend.forecast.inputs import load_inputs
from tests.forecast.test_pots import demo_pots, demo_transactions
from tests.forecast.test_recurring import txs

TODAY = dt.date(2026,11,7)


@pytest.fixture
def calendar(monkeypatch, tmp_path):
    path = tmp_path/'calendar.json'
    path.write_text(json.dumps([
        {'name':'Later','date':'2026-11-30','categories':['general']},
        {'name':'Black Friday','date':'2026-11-27','categories':['clothing','general']},
    ]))
    monkeypatch.setattr(sales,'CALENDAR_PATH',path)
    return path


def test_sam_shirt_demo_real_engine(ledger, calendar):
    ledger['pots'] = demo_pots()
    ledger['transactions'] = demo_transactions()
    before = deepcopy(ledger)
    result = forecast.simulate_purchase('sam',30,TODAY)
    assert result.affordable is True
    assert result.safe_after == 180
    assert result.better_date == dt.date(2026,11,27)
    assert result.numbers_used == {'price':30,'safe_to_spend':210,'safe_after':180}
    assert ledger == before


def test_applied_exactly_once_on_purchase_date(ledger):
    data = load_inputs('sam',TODAY)
    baseline = project(data,90)
    on = TODAY + dt.timedelta(days=10)
    scenario = project(data,90,one_off={on:3000})
    for a,b in zip(baseline,scenario):
        assert a.expected - b.expected == (30 if a.date >= on else 0)
    assert project(data,7,one_off={TODAY:3000})[0].expected == 1610


def test_new_risk_rejected_but_existing_risk_not_automatically_rejected(ledger,calendar):
    ledger['balance'] = 1640
    ledger['transactions'] = demo_transactions()
    assert not forecast.simulate_purchase('sam',1640,TODAY).affordable
    ledger['transactions'] += txs(['2026-08-25','2026-09-25','2026-10-25'],[-1600]*3,merchant='Later bill')
    # The baseline already has a monthly high risk; a small cost leaves onset unchanged.
    result = forecast.simulate_purchase('sam',30,TODAY)
    assert result.affordable


def test_earlier_crossing_rejects_even_with_positive_safe_amount(ledger,calendar):
    ledger['balance'] = 100
    ledger['transactions'] = txs(['2026-10-18','2026-10-25','2026-11-01'],[-60]*3)
    ledger['transactions'] += txs(['2026-10-19','2026-10-26','2026-11-02'],[1]*3,merchant='Pay')
    ledger['transactions'] += [txs([TODAY-dt.timedelta(days=i)],[-1],merchant=f'Daily {i}')[0] for i in range(1,85)]
    result = forecast.simulate_purchase('sam',35,TODAY)
    assert result.safe_after == 5
    assert not result.affordable
    assert 'brings a risk forward' in result.reason


@pytest.mark.parametrize('amount',[-1,float('inf'),float('nan'),True,'30'])
def test_invalid_amount(ledger,amount):
    with pytest.raises(ValueError): forecast.simulate_purchase('sam',amount,TODAY)


@pytest.mark.parametrize('on',[TODAY-dt.timedelta(days=1),TODAY+dt.timedelta(days=366),'2026-11-07'])
def test_invalid_date(ledger,on):
    with pytest.raises(ValueError): forecast.simulate_purchase('sam',30,on)


def test_zero_and_long_horizon(ledger,calendar):
    assert forecast.simulate_purchase('sam',0,TODAY).safe_after == 1640
    assert forecast.simulate_purchase('sam',30,TODAY+dt.timedelta(days=365)).safe_after == 1610


def test_missing_malformed_outside_sales_and_cwd(ledger,calendar,monkeypatch,tmp_path):
    monkeypatch.chdir(tmp_path)
    assert forecast.simulate_purchase('sam',30,TODAY).better_date == dt.date(2026,11,27)
    calendar.write_text('not json')
    result = forecast.simulate_purchase('sam',30,TODAY)
    assert result.better_date is None and 'unavailable' in result.reason
    calendar.unlink()
    assert forecast.simulate_purchase('sam',30,TODAY).better_date is None


def test_sales_window_inclusive_and_categories(ledger,calendar):
    calendar.write_text(json.dumps([
        {'name':'Outside','date':str(TODAY+dt.timedelta(days=43)),'categories':['general']},
        {'name':'Boundary','date':str(TODAY+dt.timedelta(days=42)),'categories':['general']},
        {'name':'Specific','date':str(TODAY),'categories':['electronics']},
    ]))
    assert forecast.simulate_purchase('sam',30,TODAY).better_date == TODAY+dt.timedelta(days=42)
    assert forecast.simulate_purchase('sam',30,TODAY+dt.timedelta(days=43)).better_date is None
