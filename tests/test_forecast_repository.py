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


def test_real_sqlite_forecast_integration_discloses_generated_demo_gap(monkeypatch):
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
    # Generated income is irregular, not promised; the disclosed conservative
    # policy reserves 3*(950 rent + 15 phone + 5.99 Spotify + 10.99 Netflix).
    assert safe.upcoming_bills == 2945.94
    assert safe.safe_amount == -2555.94
    assert sum(round(line.amount*100) for line in safe.breakdown) == -255594
    purchase = forecast.simulate_purchase('sam',30,config.TODAY)
    assert purchase.affordable is False and purchase.safe_after == -2585.94
    client = TestClient(app)
    response = client.get('/users/sam/safe-to-spend')
    assert response.status_code == 200 and response.json()['safe_amount'] == -2555.94
