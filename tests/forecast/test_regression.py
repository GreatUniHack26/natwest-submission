"""Independent regression/metamorphic checks; no financial engine stubs.

Monotonicity only covers deterministic extra costs with all other inputs fixed.
It does not assert that volatility, alert count or safe-to-spend is monotonic.
"""
import ast
import datetime as dt
import sys
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import config, forecast
from backend.data import repository
from backend.forecast.engine import project
from backend.forecast.inputs import load_inputs
from backend.forecast.money import pence, pounds
from backend.forecast.recurring import detect_recurring, occurrences
from backend.main import app
from contracts.schemas import Alert, Forecast, Pot, PurchaseVerdict, SafeToSpend, User
from tests.forecast.test_pots import demo_pots, demo_transactions
from tests.forecast.test_recurring import txs


@pytest.mark.parametrize('amount,expected',[(1.005,101),(0.1,10),(2.675,268),(-1.005,-101)])
def test_money_rounds_half_up(amount,expected):
    assert pence(amount) == expected
    assert pence(pounds(expected)) == expected


@pytest.mark.parametrize('amount',[True,False,float('nan'),float('inf'),'10',None])
def test_money_rejects_invalid_numbers(amount):
    with pytest.raises(ValueError): pence(amount)


def test_short_month_does_not_change_day_30_to_month_end():
    item, = detect_recurring(txs(['2026-08-30','2026-09-30','2026-10-30']))
    assert set(asdict(item)) == {'merchant','amount','next_due','every_days'}
    assert list(occurrences(item,dt.date(2026,11,1),dt.date(2026,12,31))) == [dt.date(2026,11,30),dt.date(2026,12,30)]
    # A stable 28th must survive February without drifting to March 31.
    item, = detect_recurring(txs(['2026-11-28','2026-12-28','2027-01-28']))
    assert list(occurrences(item,dt.date(2027,2,1),dt.date(2027,3,31))) == [dt.date(2027,2,28),dt.date(2027,3,28)]


def test_irregular_shift_income_and_refunds():
    data = txs(['2026-10-01','2026-10-04','2026-10-09','2026-10-12'],[60,180,90,150],merchant='Shifts')
    item, = detect_recurring(data)
    assert item.amount == 120
    assert item.every_days == 4
    assert item.next_due == dt.date(2026,10,16)
    refunds = [t.model_copy(update={'kind':'want'}) for t in data]
    assert detect_recurring(refunds) == []


@pytest.mark.parametrize('cost',[0,1,30,1000])
def test_extra_costs_only_lower_balances_from_their_date(ledger,cost):
    ledger['transactions'] = demo_transactions()
    data = load_inputs('sam',config.TODAY)
    before = deepcopy(data)
    baseline = project(data,60)
    when = config.TODAY + dt.timedelta(days=11)
    scenario = project(data,60,one_off={when:pence(cost)})
    for a,b in zip(baseline,scenario):
        for field in ('low','expected','high'):
            assert pence(getattr(a,field)) - pence(getattr(b,field)) == (pence(cost) if a.date >= when else 0)
    assert data == before


def test_all_real_facades_validate_computed_contracts(ledger):
    ledger['pots'] = demo_pots()
    ledger['transactions'] = demo_transactions()
    for result,model in [(forecast.forecast('sam',56),Forecast),
                         (forecast.safe_to_spend('sam',config.TODAY),SafeToSpend),
                         (forecast.simulate_purchase('sam',30,config.TODAY),PurchaseVerdict)]:
        assert model.model_validate_json(result.model_dump_json()) == result
    for alert in forecast.detect_alerts('sam'):
        assert Alert.model_validate_json(alert.model_dump_json()) == alert


def test_mock_facades_preserve_fixture_mode(monkeypatch):
    monkeypatch.setattr(config,'MOCK_FORECAST',True)
    assert forecast.forecast('sam').user_id == 'sam'
    assert forecast.safe_to_spend('sam',config.TODAY).safe_amount == 210
    assert forecast.simulate_purchase('sam',30,config.TODAY).safe_after == 180
    assert all(isinstance(a,Alert) for a in forecast.detect_alerts('sam'))


def test_real_api_has_exact_numbers_and_query_validation(ledger):
    ledger['pots'] = demo_pots()
    ledger['transactions'] = demo_transactions()
    client = TestClient(app)
    assert client.get('/users/sam/safe-to-spend').json()['safe_amount'] == 210
    result = client.post('/users/sam/simulate',json={'amount':30}).json()
    assert result['safe_after'] == 180 and result['better_date'] == '2026-11-27'
    result = client.get('/users/sam/forecast?days=10')
    assert result.status_code == 200
    assert result.json()['points'][-1]['date'] == '2026-11-17'
    assert client.get('/users/sam/forecast?days=366').status_code == 422


def test_missing_user_and_invalid_pots_fail_closed(ledger,monkeypatch):
    monkeypatch.setattr(repository,'get_user',lambda uid: User(id='other',name='other',persona='test',region='test'))
    with pytest.raises(LookupError): forecast.forecast('sam')
    monkeypatch.setattr(repository,'get_user',lambda uid: User(id=uid,name=uid,persona='test',region='test'))
    ledger['pots'] = [Pot(id='p',user_id='sam',name='bad',amount=-1)]
    with pytest.raises(ValueError,match='nonnegative'): forecast.forecast('sam')


def test_forecast_architecture_has_no_llm_network_or_database_dependencies():
    blocked = {'openai','anthropic','langchain','langgraph','litellm','ollama','google','requests','httpx','urllib','sqlite3','sqlalchemy','psycopg','importlib'}
    root = Path(__file__).parents[2]/'backend'/'forecast'
    for path in root.glob('*.py'):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node,ast.ImportFrom):
                modules = [node.module or '']
                if not node.level and node.module == 'backend':
                    assert all(alias.name == 'config' for alias in node.names), path
                if node.module == 'backend.data':
                    assert [alias.name for alias in node.names] == ['repository'], path
            else:
                modules = []
            for module in modules:
                assert module.split('.')[0] not in blocked, (path,module)
                if module and not (isinstance(node,ast.ImportFrom) and node.level):
                    assert module.split('.')[0] in sys.stdlib_module_names | {'backend','contracts'}, (path,module)
                if module.startswith('backend.data'):
                    assert module == 'backend.data' and isinstance(node,ast.ImportFrom), (path,module)
                assert not module.startswith(('backend.agent','backend.api','web','backend.data.generator')), (path,module)
            if isinstance(node,ast.Attribute) and isinstance(node.value,ast.Name) and node.value.id == 'repository':
                assert not node.attr.startswith('_'), (path,node.attr)
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):
                assert node.func.id not in {'__import__','eval','exec','open'}, (path,node.lineno)


def test_variable_income_timing_is_uncertain_even_with_fixed_amount(ledger):
    from backend.forecast.recurring import payment_std, patterns
    ledger['transactions'] = txs(['2026-10-01','2026-10-04','2026-10-09','2026-10-12'],[100]*4,merchant='Shifts')
    item, observations = patterns(ledger['transactions'])[0]
    assert item.every_days == 4
    assert payment_std(item,observations) > 0
    result = forecast.safe_to_spend('sam',config.TODAY)
    assert any('No certain income' in x.label for x in result.breakdown)


def test_uncertain_monthly_interval_and_amount_cluster_rejection():
    # Mean thirty-day irregular intervals are not silently treated as calendar months.
    item, = detect_recurring(txs(['2026-01-01','2026-01-21','2026-03-02'],[100]*3))
    assert item.every_days == 30 and item._monthly is False
    assert list(occurrences(item,dt.date(2026,4,1),dt.date(2026,5,31))) == [dt.date(2026,4,1),dt.date(2026,5,1),dt.date(2026,5,31)]
    # Candidates inside a pivot's tolerance still need to fit their own median.
    assert detect_recurring(txs(['2026-08-01','2026-09-01','2026-10-01','2026-11-01'],[-90,-90,-100,-110])) == []


def test_sale_category_validation_and_no_new_risk_when_already_unsafe(ledger,monkeypatch,tmp_path):
    from backend.forecast import sales
    path = tmp_path/'calendar.json'
    path.write_text('[{"name":"Sale","date":"2026-11-27","categories":42}]')
    monkeypatch.setattr(sales,'CALENDAR_PATH',path)
    with pytest.raises(sales.CalendarUnavailable): forecast.upcoming_sales()
    ledger['pots'] = [Pot(id='p',user_id='sam',name='Emergency',amount=2000)]
    assert not forecast.simulate_purchase('sam',0,config.TODAY).affordable


def test_six_month_sam_demo_reconciles_safe_purchase_and_december_risk(ledger):
    # A controlled student funded partly by existing savings: daily incidental
    # spending £1 (£12 on Tuesdays), monthly rent950, essentials180, debt220,
    # and a £100 monthly stipend. Hand calculation at Dec25:
    # 1640 + 200 stipend - 950 rent - 360 essentials - 220 debt - 125 everyday
    # = 185. Dec26's £220 debt payment and £1 spend take it to -36.
    from contracts.schemas import Transaction
    today = config.TODAY
    rows = []
    for offset in range(184):
        day = today - dt.timedelta(days=offset)
        amount = -(10 + 2 * ((offset // 7) % 3)) if day.weekday() == 1 else -1
        rows.append(Transaction(id=f'food-{day}',user_id='sam',date=day,merchant='Everyday food',amount=amount,category='food',kind='need'))
        for number,merchant,amount in [(1,'Landlord',-950),(10,'Essentials',-180),(20,'Stipend',100),(26,'Debt',-220)]:
            if day.day == number:
                rows.append(Transaction(id=f'{merchant}-{day}',user_id='sam',date=day,merchant=merchant,amount=amount,category='income' if amount > 0 else 'bills',kind='income' if amount > 0 else 'need'))
    ledger['transactions'] = rows
    ledger['pots'] = demo_pots()
    safe = forecast.safe_to_spend('sam',today)
    assert safe.safe_amount == 210
    data = load_inputs('sam',today)
    daily = project(data,60)
    assert next(p.expected for p in daily if p.date == dt.date(2026,12,25)) == 185
    assert next(p.expected for p in daily if p.date == dt.date(2026,12,26)) == -36
    result = forecast.forecast('sam',60)
    assert next(e.date for e in result.risk_events if e.severity == 'high') == dt.date(2026,12,26)
    purchase = forecast.simulate_purchase('sam',30,today)
    assert purchase.affordable and purchase.safe_after == 180
    assert purchase.better_date == dt.date(2026,11,27)


def test_four_weekly_benefit_is_not_monthly_income():
    item, = detect_recurring(txs(['2026-08-01','2026-08-29','2026-09-26','2026-10-24'],[173.2]*4,merchant='Child Benefit'))
    assert item.every_days == 28
    assert list(occurrences(item,dt.date(2026,11,1),dt.date(2026,12,31))) == [dt.date(2026,11,21),dt.date(2026,12,19)]
