"""Month-end spending forecast per category: the twin's view of where this month is heading.

For each everyday-spending category (recurring bills and income excluded, as in
alerts.py) the weekday baseline fitted on history before the 1st gives:
  expected_so_far  = baseline summed over the 1st..today
  typical_month    = baseline summed over the whole month
  projected_month  = actual spend so far + baseline for the remaining days
Status: "over" when spend so far beats expected by >= 15% and at least £5;
"watch" when it is ahead of expected; otherwise "on_track". Deterministic.
"""
import calendar
import datetime as dt

from backend import config
from .baseline import weekday_baseline
from .inputs import load_inputs
from .money import pence, pounds
from .recurring import recurring_ids

OVER_RATIO = 1.15
OVER_MIN_PENCE = 500
MIN_TYPICAL_PENCE = 500


def _baseline_sum(baseline: dict[int, tuple[float, float]], start: dt.date, end: dt.date) -> int:
    return sum(pence(baseline[(start + dt.timedelta(days=i)).weekday()][0]) for i in range((end - start).days))


def spending_forecast(user_id: str) -> dict:
    data = load_inputs(user_id, config.TODAY)
    today = data.as_of
    month_start = today.replace(day=1)
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    month_end = month_start + dt.timedelta(days=days_in_month)
    tomorrow = today + dt.timedelta(days=1)
    past = [t for t in data.transactions if t.date <= today]
    excluded = recurring_ids(past)
    spend = [t for t in past if t.amount < 0 and t.kind != 'income' and t.id not in excluded]

    rows = []
    for category in sorted({t.category for t in spend}):
        baseline = weekday_baseline([t for t in past if t.category == category], month_start)
        expected = _baseline_sum(baseline, month_start, tomorrow)
        typical = _baseline_sum(baseline, month_start, month_end)
        actual = sum(-pence(t.amount) for t in spend if t.category == category and month_start <= t.date <= today)
        projected = actual + _baseline_sum(baseline, tomorrow, month_end)
        if typical < MIN_TYPICAL_PENCE and actual == 0:
            continue
        if actual >= expected * OVER_RATIO and actual - expected >= OVER_MIN_PENCE:
            status = 'over'
            alarm = (f'{category.capitalize()} is running ahead: £{pounds(actual):.2f} so far versus '
                     f'£{pounds(expected):.2f} usual by today. At this pace the month ends near '
                     f'£{pounds(projected):.2f} (usually £{pounds(typical):.2f}).')
        elif actual > expected:
            status, alarm = 'watch', None
        else:
            status, alarm = 'on_track', None
        rows.append({
            'category': category,
            'spent_so_far': pounds(actual),
            'expected_so_far': pounds(expected),
            'projected_month': pounds(projected),
            'typical_month': pounds(typical),
            'status': status,
            'alarm': alarm,
        })

    order = {'over': 0, 'watch': 1, 'on_track': 2}
    rows.sort(key=lambda r: (order[r['status']], -r['projected_month']))
    return {
        'user_id': user_id,
        'month': month_start.strftime('%Y-%m'),
        'days_elapsed': (today - month_start).days + 1,
        'days_in_month': days_in_month,
        'spent_so_far': round(sum(r['spent_so_far'] for r in rows), 2),
        'projected_month': round(sum(r['projected_month'] for r in rows), 2),
        'typical_month': round(sum(r['typical_month'] for r in rows), 2),
        'categories': rows,
    }
