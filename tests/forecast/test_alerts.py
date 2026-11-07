import datetime as dt
from copy import deepcopy

from backend import forecast
from tests.forecast.test_recurring import txs

TODAY = dt.date(2026,11,7)


def weekly_history(amount=20, spike=None, category='eating out'):
    rows = []
    for i in range(13):
        row = txs([TODAY - dt.timedelta(days=7*i)], [-(spike if i == 0 and spike is not None else amount)], merchant=f'Cafe {i}')[0]
        row.category = category
        rows.append(row)
    return rows


def test_planted_spike_excludes_its_own_threshold(ledger):
    ledger['transactions'] = weekly_history(spike=32)
    before = deepcopy(ledger)
    alerts = forecast.detect_alerts('sam')
    sudden = [a for a in alerts if a.type == 'sudden_change']
    assert len(sudden) == 1
    assert '£32.00' in sudden[0].message
    assert '£20.00' in sudden[0].message
    assert '60%' in sudden[0].message
    assert ledger == before
    assert alerts == forecast.detect_alerts('sam')
    assert all(a.message and a.suggested_action for a in alerts)


def test_quiet_period_has_no_alerts(ledger):
    ledger['transactions'] = weekly_history()
    assert forecast.detect_alerts('sam') == []


def test_zero_mean_and_sparse_history(ledger):
    assert forecast.detect_alerts('sam') == []
    ledger['transactions'] = weekly_history()
    ledger['transactions'][0].category = 'new category'
    assert any(a.type == 'sudden_change' and a.category == 'new category' for a in forecast.detect_alerts('sam'))
    ledger['transactions'] = weekly_history(spike=100)[:2]
    assert not [a for a in forecast.detect_alerts('sam') if a.type != 'risk']


def test_month_actual_matches_period_not_whole_month(ledger):
    ledger['transactions'] = weekly_history(spike=40)
    alert = next(a for a in forecast.detect_alerts('sam') if a.type == 'overspend')
    assert '£40.00 spent month-to-date versus £20.00' in alert.message


def test_severity_order_cap_and_deduplication(ledger):
    ledger['balance'] = -1
    ledger['transactions'] = [row for cat in range(5) for row in weekly_history(spike=40, category=f'category-{cat}')]
    alerts = forecast.detect_alerts('sam')
    assert len(alerts) == 5
    assert alerts[0].type == 'risk' and alerts[0].severity == 'high'
    assert len({a.id for a in alerts}) == 5
