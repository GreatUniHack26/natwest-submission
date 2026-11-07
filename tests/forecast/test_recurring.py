import datetime as dt
from copy import deepcopy

import pytest

from backend.forecast.recurring import Recurring, amount_std, detect_recurring, occurrences, patterns, recurring_ids
from contracts.schemas import Transaction


def txs(dates, amounts=None, merchant='Rent', user='sam'):
    amounts = amounts or [-100] * len(dates)
    return [Transaction(id=f'{user}-{merchant}-{i}', user_id=user, date=d, merchant=merchant,
                        amount=a, category='bills', kind='income' if a > 0 else 'need')
            for i, (d, a) in enumerate(zip(dates, amounts))]


@pytest.mark.parametrize('dates,every,due', [
    (['2026-10-01', '2026-10-08', '2026-10-15'], 7, '2026-10-22'),
    (['2026-09-01', '2026-10-02', '2026-11-01'], 30, '2026-12-01'),
    (['2023-12-31', '2024-01-31', '2024-02-29'], 30, '2024-03-31'),
    (['2026-10-31', '2026-11-30', '2026-12-31'], 30, '2027-01-31'),
])
def test_schedule(dates, every, due):
    data = txs(dates)
    before = deepcopy(data)
    item, = detect_recurring(data[::-1])
    assert item == Recurring('Rent', -100, dt.date.fromisoformat(due), every)
    assert data == before


def test_later_projection_keeps_month_end_and_leap_year():
    item = Recurring('Rent', -100, dt.date(2023, 12, 31), 30)
    assert list(occurrences(item, dt.date(2024, 2, 1), dt.date(2024, 4, 30))) == [dt.date(2024, 2, 29), dt.date(2024, 3, 31), dt.date(2024, 4, 30)]


def test_income_uncertainty_signs_and_users_are_separate():
    dates = ['2026-09-01', '2026-10-01', '2026-11-01']
    data = txs(dates, [100, 200, 300]) + txs(dates) + txs(dates[:2], user='other')
    detected = patterns(data)
    assert [p.amount for p, _ in detected] == [-100, 200]
    assert amount_std(detected[1][1]) == pytest.approx(81.649658)


@pytest.mark.parametrize('data', [[], txs(['2026-01-01']), txs(['2026-01-01','2026-01-08']),
    txs(['2026-01-01','2026-02-15','2026-03-29']),
    txs(['2026-01-01','2026-02-01','2026-03-01'], [-100,-200,-300])])
def test_rejects_sparse_and_unstable(data):
    assert detect_recurring(data) == []


def test_outlier_merchant_purchase_not_excluded():
    data = txs(['2026-08-01','2026-09-01','2026-10-01','2026-10-02'], [-90,-100,-110,-350])
    assert detect_recurring(data)[0].amount == -100
    assert data[-1].id not in recurring_ids(data)
