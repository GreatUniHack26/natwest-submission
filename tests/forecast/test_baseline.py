import datetime as dt
from copy import deepcopy

import pytest

from backend.forecast.baseline import category_weekly_mean, weekday_baseline
from tests.forecast.test_recurring import txs

AS_OF = dt.date(2026, 11, 7)


def tuesdays():
    return [t for i in range(12) for t in txs([AS_OF - dt.timedelta(days=4 + 7*i)], [-12], merchant=f'Cafe-{i}')]


def test_tuesday_pattern_and_zero_days():
    data = tuesdays()
    before = deepcopy(data)
    result = weekday_baseline(data, AS_OF)
    assert result[1] == (12, 0)
    assert all(result[day] == (0, 0) for day in range(7) if day != 1)
    assert category_weekly_mean(data, AS_OF) == {'bills': (12, 0)}
    assert data == before


def test_population_std_and_zero_week_denominators():
    data = txs([AS_OF - dt.timedelta(days=1)], [-120])
    assert category_weekly_mean(data, AS_OF)['bills'] == pytest.approx((10, 33.1662479))
    assert weekday_baseline([], AS_OF) == {i: (0, 0) for i in range(7)}
    assert weekday_baseline(data, AS_OF)[0][0] == pytest.approx(120 / 84)


def test_recurring_income_refunds_future_and_outside_history_excluded():
    data = tuesdays() + txs(['2026-08-15','2026-09-15','2026-10-15'])
    data += txs(['2026-11-07', '2026-12-01', '2026-01-01'], [-999]*3, merchant='Future')
    data += txs(['2026-11-06'], [999], merchant='Refund')
    assert weekday_baseline(data, AS_OF)[1] == (12, 0)
    assert category_weekly_mean(data, AS_OF) == {'bills': (12, 0)}


def test_unrelated_purchase_at_recurring_merchant_stays():
    data = txs(['2026-08-15','2026-09-15','2026-10-15','2026-10-20'], [-100,-100,-100,-12])
    assert category_weekly_mean(data, AS_OF)['bills'][0] == 1


def test_categories_and_user_isolation():
    data = tuesdays()
    data[0].category = 'food'
    assert category_weekly_mean(data, AS_OF)['food'][0] == 1
    other = txs(['2026-10-20'], user='other')
    assert weekday_baseline(other, AS_OF)[1][0] == pytest.approx(100 / 12)
    with pytest.raises(ValueError, match='single user'):
        weekday_baseline(data + other, AS_OF)
