import datetime as dt
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from backend import config, forecast
from backend.data import repository
from backend.forecast.inputs import ForecastDataUnavailable
from backend.main import app
from contracts.schemas import Forecast, Pot, User
from tests.forecast.test_recurring import txs


@pytest.fixture
def family(monkeypatch):
    monkeypatch.setattr(config,'MOCK_FORECAST',False)
    monkeypatch.setattr(config,'TODAY',dt.date(2026,11,7))
    users = {uid: User(id=uid,name=uid,persona='family',region='Manchester',household_id='h1') for uid in ('adult1','adult2')}
    state = {'balances':{'adult1':100,'adult2':200},'transactions':{'adult1':[],'adult2':[]},'pots':{'adult1':[],'adult2':[]}}
    monkeypatch.setattr(repository,'get_household_members',lambda hid: list(users.values()) if hid == 'h1' else [],raising=False)
    monkeypatch.setattr(repository,'get_user',lambda uid: users[uid])
    monkeypatch.setattr(repository,'get_balance',lambda uid,as_of: state['balances'][uid],raising=False)
    monkeypatch.setattr(repository,'get_transactions',lambda uid,start=None,end=None: state['transactions'][uid])
    monkeypatch.setattr(repository,'get_pots',lambda uid: state['pots'][uid])
    return state


def test_align_sum_bands_contributions_and_recomputed_risk(family):
    family['transactions']['adult1'] = [t.model_copy(update={'user_id':'adult1'}) for t in txs(['2026-10-18','2026-10-25','2026-11-01'],[-150]*3)]
    family['transactions']['adult2'] = [t.model_copy(update={'user_id':'adult2'}) for t in txs(['2026-10-19','2026-10-26','2026-11-02'],[5,10,15],merchant='Pay')]
    before = deepcopy(family)
    a,b = [forecast.forecast(uid,10) for uid in ('adult1','adult2')]
    result = forecast.household_forecast('h1',10)
    for p,pa,pb in zip(result.points,a.points,b.points):
        assert p.date == pa.date == pb.date
        for field in ('low','expected','high'):
            assert getattr(p,field) == pytest.approx(getattr(pa,field)+getattr(pb,field),abs=0.001)
    assert any(e.severity == 'high' for e in a.risk_events)
    assert not result.risk_events  # household income covers both bill dates
    assert any('adult1' in text and '100.00' in text for text in result.assumptions)
    assert Forecast.model_validate_json(result.model_dump_json()) == result
    assert family == before


def test_household_safe_breakdown_and_shared_pot_single_owner(family):
    family['pots']['adult1'] = [Pot(id='shared',user_id='adult1',name='Shared emergency',amount=50)]
    result = forecast.household_safe_to_spend('h1')
    assert result.balance == 300 and result.pots_total == 50 and result.safe_amount == 250
    assert sum(line.amount for line in result.breakdown) == 250
    family['pots']['adult2'] = [Pot(id='shared',user_id='adult2',name='Same shared pot',amount=50)]
    with pytest.raises(ValueError,match='single balance owner'): forecast.household_forecast('h1',7)


def test_internal_transfers_do_not_predict_income_or_spending(family):
    rows = txs(['2026-10-18','2026-10-25','2026-11-01'],[-50]*3,merchant='Transfer')
    family['transactions']['adult1'] = [t.model_copy(update={'user_id':'adult1','category':'internal_transfer'}) for t in rows]
    family['transactions']['adult2'] = [t.model_copy(update={'user_id':'adult2','category':'internal_transfer','amount':50,'kind':'income'}) for t in rows]
    assert [p.expected for p in forecast.household_forecast('h1',14).points] == [300,300,300]
    assert forecast.household_safe_to_spend('h1').safe_amount == 300


def test_scope_unknown_foreign_and_missing_members(family,monkeypatch):
    with pytest.raises(LookupError): forecast.household_forecast('other',7)
    monkeypatch.setattr(repository,'get_household_members',lambda hid:[User(id='foreign',name='secret',persona='other',region='other',household_id='h2')])
    with pytest.raises(LookupError): forecast.household_forecast('h1',7)
    monkeypatch.setattr(repository,'get_household_members',lambda hid:[User(id='gone',name='gone',persona='family',region='test',household_id='h1')])
    with pytest.raises(LookupError): forecast.household_forecast('h1',7)


def test_endpoint_numbers_schema_limits_and_errors(family):
    client = TestClient(app)
    response = client.get('/households/h1/forecast?days=10')
    assert response.status_code == 200
    result = Forecast.model_validate(response.json())
    assert result.user_id == 'h1'
    assert result.points[-1].date == config.TODAY+dt.timedelta(days=10)
    assert result.points[-1].expected == 300
    assert client.get('/households/h1/safe-to-spend').json()['safe_amount'] == 300
    assert client.get('/households/unknown/forecast').status_code == 404
    assert client.get('/households/h1/forecast?days=6').status_code == 422
    assert client.get('/households/h1/forecast?days=366').status_code == 422


def test_missing_interface_mock_mode_and_duplicate_member_errors(family,monkeypatch):
    client = TestClient(app)
    monkeypatch.delattr(repository,'get_household_members')
    assert client.get('/households/h1/forecast').status_code == 503
    monkeypatch.setattr(config,'MOCK_FORECAST',True)
    assert client.get('/households/h1/safe-to-spend').status_code == 503
    monkeypatch.setattr(config,'MOCK_FORECAST',False)
    user = repository.get_user('adult1')
    monkeypatch.setattr(repository,'get_household_members',lambda hid:[user,user],raising=False)
    assert client.get('/households/h1/forecast').status_code == 422


def test_aggregate_protected_funds_risk(family):
    family['pots']['adult1'] = [Pot(id='goal',user_id='adult1',name='Goal',amount=400)]
    result = forecast.household_forecast('h1',7)
    assert len(result.risk_events) == 1
    assert result.risk_events[0].severity == 'medium'
    assert 'protected' in result.risk_events[0].reason


def test_membership_is_rechecked_against_real_user(family,monkeypatch):
    monkeypatch.setattr(repository,'get_user',lambda uid: User(id=uid,name=uid,persona='other',region='test',household_id='other-household'))
    client = TestClient(app)
    response = client.get('/households/h1/forecast')
    assert response.status_code == 404
    assert 'other-household' not in response.text


def test_shared_pot_funds_another_members_bill_once(family):
    family['balances'] = {'adult1':150,'adult2':50}
    # The first adult owns the shared reserve; the second pays the bill.
    family['pots']['adult1'] = [Pot(id='rent',user_id='adult1',name='Rent',amount=180,due_date='2026-11-10')]
    family['transactions']['adult2'] = [t.model_copy(update={'user_id':'adult2'}) for t in txs(['2026-08-10','2026-09-10','2026-10-10'],[-180]*3)]
    result = forecast.household_safe_to_spend('h1')
    assert result.pots_total == 180
    assert result.upcoming_bills == 360  # December/January, not funded November again
    assert result.safe_amount == -340
    assert sum(line.amount for line in result.breakdown) == -340
    assert not forecast.household_forecast('h1',7).risk_events  # funded reserve consumed; £20 remains


def test_two_bills_same_merchant_date_do_not_reuse_credit(family):
    for uid in ('adult1','adult2'):
        family['transactions'][uid] = [t.model_copy(update={'user_id':uid}) for t in txs(['2026-08-10','2026-09-10','2026-10-10'],[-50]*3)]
    family['pots']['adult1'] = [Pot(id='shared',user_id='adult1',name='Rent',amount=60,due_date='2026-11-10')]
    result = forecast.household_safe_to_spend('h1')
    assert result.upcoming_bills == 240  # six £50 bills, minus one £60 allocation
    assert result.pots_total == 60 and result.safe_amount == 0
    assert sum(line.amount for line in result.breakdown) == 0


@pytest.mark.skipif(not hasattr(repository,'get_balance'),reason='Real balance interface awaits P1 approval in #55')
def test_actual_generated_family_sqlite_and_endpoint_integration(monkeypatch,tmp_path):
    from backend.data.seed import seed
    monkeypatch.setattr(config,'MOCK_DATA',False)
    monkeypatch.setattr(config,'MOCK_FORECAST',False)
    monkeypatch.setattr(config,'DB_PATH',str(tmp_path/'real-family.db'))
    monkeypatch.setattr(config,'TODAY',dt.date(2026,11,7))
    seed()
    members = repository.get_household_members('h1')
    assert [u.id for u in members] == ['dan','maya']
    individual = [forecast.forecast(u.id,90) for u in members]
    result = forecast.household_forecast('h1',90)
    assert result.points[0].expected == 1420  # Dan £220 + Maya £1200, real anchored balances
    assert all(p.expected == pytest.approx(sum(member.points[i].expected for member in individual),abs=.001) for i,p in enumerate(result.points))
    assert all(p.low <= p.expected <= p.high for p in result.points)
    safe = forecast.household_safe_to_spend('h1')
    assert safe.balance == 1420 and safe.pots_total == 875
    assert sum(round(line.amount*100) for line in safe.breakdown) == round(safe.safe_amount*100)
    assert 'sam' not in str(result.assumptions) and 'alex' not in str(result.assumptions)
    response = TestClient(app).get('/households/h1/forecast?days=90')
    assert response.status_code == 200
    assert Forecast.model_validate(response.json()) == result


def test_misaligned_projection_dates_fail_before_aggregation(family,monkeypatch):
    # Boundary guard only: real financial maths runs, then corrupt one date.
    from backend.forecast import household
    real_project = household.project
    def misaligned(data,horizon):
        points = real_project(data,horizon)
        if data.user_id == 'adult2':
            points[-1] = points[-1].model_copy(update={'date':points[-1].date+dt.timedelta(days=1)})
        return points
    monkeypatch.setattr(household,'project',misaligned)
    with pytest.raises(ValueError,match='dates must align'):
        forecast.household_forecast('h1',10)


def test_shared_pot_consumes_bill_already_paid_today_by_another_member(family):
    family['balances'] = {'adult1': 20, 'adult2': 0}  # closing balances after payment
    family['pots']['adult1'] = [Pot(id='rent',user_id='adult1',name='Rent',amount=180,due_date=config.TODAY)]
    rows = txs(['2026-08-07','2026-09-07','2026-10-07','2026-11-07'],[-180]*4)
    rows += txs(['2026-08-09','2026-09-09','2026-10-09'],[100]*3,merchant='Pay')
    family['transactions']['adult2'] = [t.model_copy(update={'user_id':'adult2'}) for t in rows]
    before = deepcopy(family)
    safe = forecast.household_safe_to_spend('h1')
    assert (safe.balance,safe.pots_total,safe.upcoming_bills,safe.safe_amount) == (20,0,0,20)
    assert sum(line.amount for line in safe.breakdown) == 20
    result = forecast.household_forecast('h1',7)
    assert result.points[0].expected == 20 and result.points[-1].expected == 120
    assert result.risk_events == []
    assert family == before
    # Without today's actual debit, the due-today obligation remains reserved.
    family['transactions']['adult2'] = [t for t in family['transactions']['adult2'] if t.date != config.TODAY]
    assert forecast.household_safe_to_spend('h1').pots_total == 180


def test_same_member_partial_payment_is_not_consumed_twice_in_household(family):
    family['balances'] = {'adult1': 100, 'adult2': 0}
    family['pots']['adult1'] = [Pot(id='rent',user_id='adult1',name='Rent',amount=180,due_date=config.TODAY)]
    rows = txs(['2026-08-07','2026-09-07','2026-10-07'],[-180]*3)
    rows += txs(['2026-11-07'],[-100],merchant='Rent paid today')
    rows[-1].merchant = 'Rent'
    rows += txs(['2026-08-09','2026-09-09','2026-10-09'],[100]*3,merchant='Pay')
    family['transactions']['adult1'] = [t.model_copy(update={'user_id':'adult1'}) for t in rows]
    safe = forecast.household_safe_to_spend('h1')
    assert (safe.pots_total,safe.upcoming_bills,safe.safe_amount) == (80,0,20)
    assert sum(line.amount for line in safe.breakdown) == 20
