"""Explainable rolling-week changes and matching month-to-date overspending.

The seven-day evaluation period includes as_of. Historical periods end before
that week or month starts, so a spike never raises its own threshold. At least
four weeks of history are required for comparisons; absent history is unknown.
Refunds do not count as spend. IDs and severity ordering are deterministic.
"""
import datetime as dt
from collections import defaultdict

from backend import config
from contracts.schemas import Alert
from .baseline import category_weekly_mean, weekday_baseline
from .engine import project, response
from .inputs import load_inputs
from .money import pence, pounds
from .recurring import recurring_ids


def find_alerts(user_id: str) -> list[Alert]:
    data = load_inputs(user_id, config.TODAY)
    today = data.as_of
    week_start = today - dt.timedelta(days=6)
    month_start = today.replace(day=1)
    end = today + dt.timedelta(days=1)
    all_past = [t for t in data.transactions if t.date <= today]
    excluded = recurring_ids(all_past)
    spend = [t for t in all_past if t.amount < 0 and t.kind != 'income' and t.id not in excluded]
    alerts = []
    if all_past and min(t.date for t in all_past) <= week_start - dt.timedelta(days=28):
        historical = category_weekly_mean(all_past, week_start)
        current = defaultdict(int)
        for tx in spend:
            if week_start <= tx.date < end:
                current[tx.category] += -pence(tx.amount)
        for category, amount in sorted(current.items()):
            average, std = historical.get(category, (0, 0))
            if amount > pence(average + 2 * std):
                message = f'{category}: £{pounds(amount):.2f} in the last seven days; historical weekly average £{average:.2f}.'
                if average > 0:
                    message += f' That is {(pounds(amount) / average - 1) * 100:.0f}% above the average.'
                else:
                    message += ' No spending in this category was recorded in the historical comparison period.'
                alerts.append(Alert(id=f'sudden_change:{category}:{week_start}',type='sudden_change',category=category,
                                    message=message,suggested_action=f'Review recent {category} purchases and choose a spending limit for the coming week.',severity='medium'))
    if all_past and min(t.date for t in all_past) <= month_start - dt.timedelta(days=28):
        categories = sorted({t.category for t in spend if month_start <= t.date < end})
        for category in categories:
            # Retain original dates and recurring observations when fitting each category.
            baseline = weekday_baseline([t for t in all_past if t.category == category], month_start)
            expected = sum(pence(baseline[(month_start + dt.timedelta(days=i)).weekday()][0])
                           for i in range((end - month_start).days))
            actual = sum(-pence(t.amount) for t in spend if t.category == category and month_start <= t.date < end)
            if actual > expected:
                alerts.append(Alert(id=f'overspend:{category}:{month_start}',type='overspend',category=category,
                                    message=f'{category}: £{pounds(actual):.2f} spent month-to-date versus £{pounds(expected):.2f} expected for the same dates.',
                                    suggested_action=f'Review remaining {category} spending this month against upcoming bills and protected pots.',severity='medium'))
    forecast = response(data, project(data, 90), 90)
    for event in forecast.risk_events:
        if event.severity == 'high':
            alerts.append(Alert(id=f'risk:{event.date}',type='risk',message=f'{event.date}: {event.reason}',
                                suggested_action='Review bills due before that date and consider postponing optional spending.',severity='high'))
    ranks = {'high': 0, 'medium': 1, 'low': 2}
    unique = {a.id: a for a in alerts}
    return sorted(unique.values(),key=lambda a: (ranks[a.severity], a.type, a.category or '', a.id))[:5]
