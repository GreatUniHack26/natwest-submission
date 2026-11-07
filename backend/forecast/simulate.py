"""Rerun the same daily projection with one dated purchase in integer pence.

Use today's safe budget even for future purchases; do not promise future income
as spendable now. Worsening means a new or earlier expected/low/pot crossing,
not a different explanation string or just an already-existing baseline risk.
"""
import datetime as dt

from backend import config
from contracts.schemas import PurchaseVerdict
from .engine import project
from .inputs import load_inputs
from .money import pence, pounds
from .pots import safe_from_inputs
from .recurring import patterns
from .reservations import bill_schedule, protected_on
from .sales import CalendarUnavailable, upcoming_sales


def risk_onsets(data, daily):
    bills = bill_schedule([item for item, _ in patterns(data.transactions)], data.as_of + dt.timedelta(days=1), daily[-1].date)
    onsets = {}
    for point in daily:
        protected = protected_on(data.pots, bills, point.date)
        for kind, condition in [('expected', point.expected < 0), ('low', point.low < 0),
                                ('pots', protected > 0 and pence(point.expected) < protected)]:
            if condition:
                onsets.setdefault(kind, point.date)
    return onsets


def simulate(user_id: str, amount: float, on_date: dt.date) -> PurchaseVerdict:
    cost = pence(amount)
    if amount < 0:
        raise ValueError('Purchase amount must be nonnegative')
    if type(on_date) is not dt.date:
        raise ValueError('Purchase date must be a date')
    days = (on_date - config.TODAY).days
    if not 0 <= days <= 365:
        raise ValueError('Purchase date must be today or within the next 365 days')
    data = load_inputs(user_id, config.TODAY)
    safe = pence(safe_from_inputs(data).safe_amount)
    safe_after = safe - cost
    horizon = max(90, days)
    baseline = risk_onsets(data, project(data, horizon))
    scenario = risk_onsets(data, project(data, horizon, one_off={on_date: cost}))
    worsened = any(kind not in baseline or date < baseline[kind] for kind, date in scenario.items())
    affordable = safe_after >= 0 and not worsened
    reason = f'A £{pounds(cost):.2f} purchase leaves £{pounds(safe_after):.2f} from today\'s £{pounds(safe):.2f} safe budget.'
    if safe_after < 0:
        reason += ' This exceeds the amount available after protected pots and bills.'
    if worsened:
        reason += ' It introduces a new risk or brings a risk forward in the daily forecast.'
    elif affordable:
        reason += ' It creates no new or earlier forecast risk; existing forecast risks still apply.'
    better_date = None
    try:
        sales = upcoming_sales(42)
        candidates = [s for s in sales if dt.date.fromisoformat(s['date']) >= on_date and 'general' in s['categories']]
        if candidates:
            better_date = dt.date.fromisoformat(candidates[0]['date'])
            reason += f' A general sale is scheduled for {better_date}; lower prices are not guaranteed.'
    except CalendarUnavailable:
        reason += ' Sale timing is unavailable because the calendar is missing or malformed.'
    return PurchaseVerdict(affordable=affordable, safe_after=pounds(safe_after), better_date=better_date, reason=reason,
                           numbers_used={'price': pounds(cost), 'safe_to_spend': pounds(safe), 'safe_after': pounds(safe_after)})
