"""Calendar anchors and pay uncertainty: independent boundary calculations."""
import datetime as dt
import math
from copy import deepcopy
from dataclasses import asdict

import pytest

from backend.forecast.inputs import Inputs
from backend.forecast.pots import safe_from_inputs
from backend.forecast.recurring import detect_recurring, occurrences, patterns, payment_std
from contracts.schemas import Transaction


def rows(dates, amounts=None, merchant='Pay'):
    amounts = amounts if amounts is not None else [100] * len(dates)
    return [Transaction(id=f'{merchant}-{i}', user_id='sam', date=day,
                        merchant=merchant, amount=amount,
                        category='income' if amount > 0 else 'bills',
                        kind='income' if amount > 0 else 'need')
            for i, (day, amount) in enumerate(zip(dates, amounts))]


@pytest.mark.parametrize('dates,start,end,expected', [
    (['2027-01-30','2027-02-28','2027-03-30'], '2027-04-01','2027-05-31',
     ['2027-04-30','2027-05-30']),
    (['2024-01-30','2024-02-29','2024-03-30'], '2024-04-01','2024-05-31',
     ['2024-04-30','2024-05-30']),
    (['2027-01-28','2027-02-28','2027-03-28'], '2027-04-01','2027-05-31',
     ['2027-04-28','2027-05-28']),
    (['2024-01-31','2024-02-29','2024-03-31'], '2024-04-01','2024-05-31',
     ['2024-04-30','2024-05-31']),
    (['2026-12-31','2027-01-31','2027-02-28'], '2027-03-01','2027-04-30',
     ['2027-03-31','2027-04-30']),
    (['2026-08-01','2026-08-31','2026-10-01'], '2026-10-02','2026-12-01',
     ['2026-11-01','2026-12-01']),
    (['2026-07-01','2026-08-01','2026-08-31','2026-09-30'], '2026-10-01','2026-11-01',
     ['2026-11-01']),  # Sep30 already posted the October payment; no duplicate Oct1
    (['2026-06-30','2026-07-31','2026-09-01'], '2026-09-02','2026-10-31',
     ['2026-09-30','2026-10-31']),  # Sep1 is the late August31 payment
])
def test_calendar_day_is_inferred_from_clamped_history(dates,start,end,expected):
    transactions = rows(dates)
    before = deepcopy(transactions)
    item, = detect_recurring(transactions[::-1])
    assert set(asdict(item)) == {'merchant','amount','next_due','every_days'}
    assert list(occurrences(item,dt.date.fromisoformat(start),dt.date.fromisoformat(end))) == [dt.date.fromisoformat(day) for day in expected]
    assert transactions == before


@pytest.mark.parametrize('dates', [
    ['2027-01-30','2027-02-28','2027-03-30'],
    ['2024-01-31','2024-02-29','2024-03-31'],
    ['2026-09-01','2026-10-01','2026-11-01'],
])
def test_calendar_month_lengths_alone_are_not_pay_uncertainty(dates):
    item, observations = patterns(rows(dates))[0]
    assert payment_std(item,observations) == 0


def test_actual_monthly_pay_jitter_remains_uncertain():
    item, observations = patterns(rows(['2026-09-01','2026-10-03','2026-11-01']))[0]
    # Fitted day 1 has deviations [0,2,0], population variance 8/9 days².
    # The observed intervals are 32 and 29 days, averaging 30.5.
    expected = 100 * math.sqrt(8 / 9) / 30.5
    assert payment_std(item,observations) == pytest.approx(expected)
    assert item.next_due == dt.date(2026,12,1)


def test_jittery_pay_does_not_end_conservative_bill_reservation():
    bills = rows(['2026-08-10','2026-09-10','2026-10-10'],[-20]*3,'Phone')
    variable = Inputs('sam',dt.date(2026,11,7),100000,
                      rows(['2026-09-01','2026-10-03','2026-11-01']) + bills,[])
    predictable = Inputs('sam',dt.date(2026,11,7),100000,
                         rows(['2026-09-01','2026-10-01','2026-11-01']) + bills,[])
    result = safe_from_inputs(variable)
    assert result.upcoming_bills == 60  # Nov10, Dec10 and Jan10 inside 90 days
    assert result.safe_amount == 940
    assert any('No certain income' in line.label for line in result.breakdown)
    assert safe_from_inputs(predictable).upcoming_bills == 20  # only before Dec1 pay


def test_a_missing_month_is_not_a_successive_monthly_schedule():
    # The amount and end dates fit, but February's observation is absent.
    assert detect_recurring(rows(['2027-01-30','2027-03-30','2027-04-30'],[-100]*3,'Rent')) == []
