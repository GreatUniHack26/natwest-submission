"""Proposed P1 interfaces, tested through actual temporary SQLite storage."""
import datetime as dt

import pytest

from backend import config
from backend.data import repository
from backend.data.generator import generate_persona
from contracts.schemas import Transaction, User


@pytest.fixture(autouse=True)
def database(monkeypatch,tmp_path):
    monkeypatch.setattr(config,'MOCK_DATA',False)
    monkeypatch.setattr(config,'DB_PATH',str(tmp_path/'forecast.db'))
    monkeypatch.setattr(config,'TODAY',dt.date(2026,11,7))


def user(uid='u1',household='h1'):
    return User(id=uid,name=uid,persona='test',region='Manchester',household_id=household)


def transaction(tid,day,amount,merchant='Shop'):
    return Transaction(id=tid,user_id='u1',date=day,merchant=merchant,amount=amount,category='income' if amount > 0 else 'food',kind='income' if amount > 0 else 'need')


def test_balance_is_anchored_close_of_day_not_unanchored_history():
    rows = [transaction('opening','2026-01-01',1000,'Opening balance'),
            transaction('spend','2026-01-01',-10),transaction('pay','2026-01-02',5),
            transaction('future','2026-01-03',999)]
    repository.save_persona(user(),rows,[])
    assert repository.get_balance('u1',dt.date(2026,1,1)) == 990
    assert repository.get_balance('u1',dt.date(2026,1,2)) == 995
    with pytest.raises(ValueError,match='authoritative'): repository.get_balance('u1',dt.date(2025,12,31))


def test_missing_duplicate_anchor_unknown_user_and_fixture_fail_explicitly(monkeypatch):
    repository.save_persona(user(),[transaction('spend','2026-01-01',-10)],[])
    with pytest.raises(ValueError,match='authoritative'): repository.get_balance('u1',config.TODAY)
    with pytest.raises(KeyError): repository.get_balance('other',config.TODAY)
    repository.save_persona(user(),[transaction('a','2026-01-01',100,'Opening balance'),transaction('b','2026-01-02',100,'Opening balance')],[])
    with pytest.raises(ValueError,match='Exactly one'): repository.get_balance('u1',config.TODAY)
    monkeypatch.setattr(config,'MOCK_DATA',True)
    with pytest.raises(ValueError,match='authoritative'): repository.get_balance('sam',config.TODAY)
    assert repository.get_household_members('h1') == []


def test_penny_arithmetic_and_user_scoping():
    repository.save_persona(user(),[transaction('opening','2026-01-01',.1,'Opening balance'),transaction('pay','2026-01-02',.2)],[])
    repository.save_persona(user('other','h2'),[],[])
    assert repository.get_balance('u1',config.TODAY) == .3
    assert [u.id for u in repository.get_household_members('h1')] == ['u1']
    assert [u.id for u in repository.get_household_members('h2')] == ['other']
    assert repository.get_household_members('unknown') == []
    assert repository.get_household_members("h1' OR 1=1 --") == []


def test_generated_sam_authoritative_closing_balance_and_historical_lookup():
    generated,rows,pots = generate_persona('sam',42)
    repository.save_persona(generated,rows,pots)
    assert repository.get_balance('sam',config.TODAY) == 1640
    opening = next(t for t in rows if t.merchant == 'Opening balance')
    # Historical balance includes same-day actuals, never future transactions.
    from decimal import Decimal
    expected = sum(Decimal(str(t.amount)) for t in rows if t.date == opening.date)
    assert repository.get_balance('sam',opening.date) == float(expected.quantize(Decimal('.01')))


def test_real_sqlite_forecast_integration_reproduces_generated_demo(monkeypatch):
    from backend import forecast
    from backend.main import app
    from fastapi.testclient import TestClient
    monkeypatch.setattr(config,'MOCK_FORECAST',False)
    generated,rows,pots = generate_persona('sam',42)
    repository.save_persona(generated,rows,pots)
    result = forecast.forecast('sam',90)
    assert result.points[0].expected == 1640
    assert all(p.low <= p.expected <= p.high for p in result.points)
    assert result == forecast.forecast('sam',90)
    safe = forecast.safe_to_spend('sam',config.TODAY)
    # A fixed stipend arrives on the 20th; reserve phone15, utilities154.01,
    # and Netflix10.99 (bills first on the income date), not uncertain shift pay.
    assert safe.upcoming_bills == 180
    assert safe.safe_amount == 210
    assert sum(round(line.amount*100) for line in safe.breakdown) == 21000
    purchase = forecast.simulate_purchase('sam',30,config.TODAY)
    assert purchase.affordable is True and purchase.safe_after == 180
    client = TestClient(app)
    response = client.get('/users/sam/safe-to-spend')
    assert response.status_code == 200 and response.json()['safe_amount'] == 210


def test_balance_source_is_independent_of_user_category_overrides():
    repository.save_persona(user(),[transaction('opening','2026-01-01',100,'Opening balance'),transaction('spend','2026-01-02',-10)],[])
    repository.set_override('u1','opening','other','want')
    assert repository.get_balance('u1',config.TODAY) == 90


def test_nonfinite_ledger_amount_cannot_become_a_balance():
    repository.save_persona(user(),[transaction('opening','2026-01-01',100,'Opening balance'),transaction('invalid','2026-01-02',float('inf'))],[])
    with pytest.raises(ValueError,match='finite'): repository.get_balance('u1',config.TODAY)
