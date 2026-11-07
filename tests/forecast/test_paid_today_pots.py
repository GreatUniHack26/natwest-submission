"""Closing balances already include posted bills; funded pots must consume once."""
import datetime as dt
from copy import deepcopy

from backend.forecast.engine import project, response
from backend.forecast.inputs import Inputs
from backend.forecast.pots import safe_from_inputs
from backend.forecast.reservations import remaining_pots
from backend.forecast.simulate import risk_onsets
from contracts.schemas import Pot, Transaction

AS_OF = dt.date(2026, 11, 7)


def settled_data(actual_amounts=(), balance=20, reserve=180):
    rows = [Transaction(id=f'rent-{i}', user_id='sam', date=day, merchant='Rent', amount=-180,
                        category='housing', kind='need')
            for i, day in enumerate(['2026-08-07','2026-09-07','2026-10-07'])]
    rows += [Transaction(id=f'pay-{i}', user_id='sam', date=day, merchant='Pay', amount=100,
                         category='income', kind='income')
             for i, day in enumerate(['2026-08-09','2026-09-09','2026-10-09'])]
    rows += [Transaction(id=f'actual-{i}', user_id='sam', date=AS_OF, merchant='Rent', amount=amount,
                         category='housing', kind='need' if amount < 0 else 'want')
             for i, amount in enumerate(actual_amounts)]
    return Inputs('sam', AS_OF, round(balance * 100), rows,
                  [Pot(id='rent', user_id='sam', name='Rent', amount=reserve, due_date=AS_OF)])


def test_paid_today_consumes_reserve_without_replaying_cashflow_or_mutating_inputs():
    data = settled_data([-180])  # £200 before payment; £20 at close.
    before = deepcopy(data)
    safe = safe_from_inputs(data)
    assert (safe.balance, safe.pots_total, safe.upcoming_bills, safe.safe_amount) == (20, 0, 0, 20)
    assert sum(line.amount for line in safe.breakdown) == 20
    daily = project(data, 7)
    assert daily[0].expected == 20
    assert daily[-1].expected == 120  # next £100 income, no second rent debit.
    assert response(data, daily, 7).risk_events == []
    assert risk_onsets(data, daily) == {}
    assert data == before


def test_unpaid_due_today_and_refunds_keep_reserve_protected():
    unpaid = safe_from_inputs(settled_data())
    assert (unpaid.pots_total, unpaid.safe_amount) == (180, -160)
    refunded = safe_from_inputs(settled_data([180], balance=200))
    assert (refunded.pots_total, refunded.safe_amount) == (180, 20)


def test_partial_and_split_debits_consume_only_paid_amount_capped_at_reserve():
    partial = safe_from_inputs(settled_data([-100], balance=100))
    assert (partial.pots_total, partial.safe_amount) == (80, 20)
    split = safe_from_inputs(settled_data([-100, -80]))
    assert (split.pots_total, split.safe_amount) == (0, 20)
    overpaid = safe_from_inputs(settled_data([-200], balance=0))
    assert (overpaid.pots_total, overpaid.safe_amount) == (0, 0)


def test_future_or_historical_debits_do_not_consume_today_and_open_pots_stay_protected():
    data = settled_data([-180])
    before = deepcopy(data)
    actual = data.transactions[-1]
    for other_date in [AS_OF-dt.timedelta(days=1), AS_OF+dt.timedelta(days=1)]:
        transactions = [actual.model_copy(update={'date': other_date})]
        assert remaining_pots(data.pots, transactions, AS_OF)[0].amount == 180
    open_pot = data.pots[0].model_copy(update={'due_date': None})
    assert remaining_pots([open_pot], [actual], AS_OF)[0].amount == 180
    transfer = actual.model_copy(update={'category': 'internal_transfer'})
    assert remaining_pots(data.pots, [transfer], AS_OF)[0].amount == 180
    assert data == before
