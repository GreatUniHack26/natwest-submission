import datetime as dt

import pytest

from backend import forecast
from backend.forecast.engine import project, response
from backend.forecast.inputs import load_inputs
from contracts.schemas import Pot
from tests.forecast.test_recurring import txs

AS_OF = dt.date(2026,11,7)


def demo_pots():
    return [Pot(id='rent',user_id='sam',name='December rent',amount=950,due_date='2026-12-01'),
            Pot(id='emergency',user_id='sam',name='Emergency',amount=300)]


def demo_transactions():
    return txs(['2026-08-10','2026-09-10','2026-10-10'], [-180]*3, merchant='Bills') + txs(['2026-08-20','2026-09-20','2026-10-20'], [100]*3, merchant='Pay')


def test_demo_and_reconciliation(ledger):
    ledger['pots'] = demo_pots()
    ledger['transactions'] = demo_transactions()
    result = forecast.safe_to_spend('sam', AS_OF)
    assert (result.balance,result.pots_total,result.upcoming_bills,result.safe_amount) == (1640,1250,180,210)
    assert sum(x.amount for x in result.breakdown) == result.safe_amount


def test_negative_and_absent_income_reserve_multiple_recurrences(ledger):
    ledger['balance'] = 100
    ledger['transactions'] = txs(['2026-08-10','2026-09-10','2026-10-10'], [-180]*3)
    result = forecast.safe_to_spend('sam', AS_OF)
    assert result.upcoming_bills == 540
    assert result.safe_amount == -440
    assert any('negative' in x.label for x in result.breakdown)
    assert sum(x.amount for x in result.breakdown) == -440


def test_same_day_income_bills_and_dated_pot_boundaries(ledger):
    ledger['transactions'] = txs(['2026-08-10','2026-09-10','2026-10-10'], [-180]*3) + txs(['2026-08-10','2026-09-10','2026-10-10'], [100]*3, merchant='Pay')
    ledger['pots'] = [Pot(id='today',user_id='sam',name='Goal',amount=10,due_date=AS_OF),
                      Pot(id='expired',user_id='sam',name='Expired',amount=999,due_date='2026-11-06')]
    result = forecast.safe_to_spend('sam', AS_OF)
    assert result.upcoming_bills == 180
    assert result.pots_total == 10
    assert forecast.safe_to_spend('sam', dt.date(2026,11,8)).pots_total == 0


def test_pot_funding_not_counted_twice_or_after_payment(ledger):
    ledger['balance'] = 200
    ledger['transactions'] = txs(['2026-08-10','2026-09-10','2026-10-10'], [-180]*3)
    ledger['pots'] = [Pot(id='p',user_id='sam',name='Rent',amount=180,due_date='2026-11-10')]
    result = forecast.safe_to_spend('sam', AS_OF)
    assert result.pots_total == 180
    assert result.upcoming_bills == 360  # Dec/Jan remain unfunded
    data = load_inputs('sam', AS_OF)
    projected = response(data, project(data, 7), 7)
    assert not projected.risk_events  # £20 remaining; funded pot consumed


def test_uncertain_income_is_not_promised(ledger):
    ledger['transactions'] = demo_transactions()
    ledger['transactions'][-1].amount = 150
    assert forecast.safe_to_spend('sam', AS_OF).upcoming_bills == 540


def test_no_commitments(ledger):
    result = forecast.safe_to_spend('sam', AS_OF)
    assert result.safe_amount == 1640
    assert result.upcoming_bills == result.pots_total == 0
