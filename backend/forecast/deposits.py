"""Short-term deposit ideas for ring-fenced pots ("put idle money to work").

A pot is money the user has promised to a future bill (e.g. March rent). Until
its due date it sits idle. The twin estimates what it could earn in an
instant-access saver and checks the forecast for dates where the plan already
relies on protected money, so the suggestion never strands cash the user needs.

The rate is an illustrative assumption (SAVER_AER env, default 4.0% AER), not a
product offer. Interest = amount x ((1 + AER)^(days/365) - 1), rounded to pence.
"""
import datetime as dt
import os
from decimal import Decimal, ROUND_HALF_UP

from backend import config
from backend.data import repository

MIN_DAYS = 14
MIN_AMOUNT = 100.0
OPEN_ENDED_DAYS = 365


def illustrative_aer() -> float:
    try:
        return max(0.0, min(15.0, float(os.getenv('SAVER_AER', '4.0'))))
    except ValueError:
        return 4.0


def _interest(amount: float, aer_pct: float, days: int) -> float:
    growth = (1 + aer_pct / 100) ** (days / 365) - 1
    return float((Decimal(str(amount)) * Decimal(str(growth))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def deposit_ideas(user_id: str) -> dict:
    from . import forecast as run_forecast

    today = config.TODAY
    aer = illustrative_aer()
    pots = repository.get_pots(user_id)
    try:
        risks = run_forecast(user_id, 90).risk_events
    except Exception:
        risks = []
    pot_dips = sorted(r.date for r in risks if 'protected by pots' in r.reason.lower())

    ideas = []
    for pot in pots:
        if pot.amount < MIN_AMOUNT:
            continue
        open_ended = pot.due_date is None
        days = OPEN_ENDED_DAYS if open_ended else (pot.due_date - today).days
        if not open_ended and days < MIN_DAYS:
            continue
        dip_before_due = next((d for d in pot_dips if open_ended or d < pot.due_date), None)
        caution = None
        if dip_before_due:
            caution = (f'Your forecast already leans on protected money around {dip_before_due.day} {dip_before_due:%b}, '
                       'so keep pot money instant-access rather than fixed-term.')
        ideas.append({
            'pot': pot.name,
            'amount': pot.amount,
            'due_date': pot.due_date.isoformat() if pot.due_date else None,
            'idle_days': days,
            'account_type': 'instant-access saver',
            'aer': aer,
            'est_interest': _interest(pot.amount, aer, days),
            'interest_period': 'per year' if open_ended else 'until due date',
            'withdraw_by': None if open_ended else (pot.due_date - dt.timedelta(days=2)).isoformat(),
            'caution': caution,
        })
    ideas.sort(key=lambda i: -i['est_interest'])
    return {
        'user_id': user_id,
        'aer_assumption': aer,
        'total_est_interest': round(sum(i['est_interest'] for i in ideas), 2),
        'ideas': ideas,
        'disclaimer': f'Illustrative {aer:.1f}% AER, not a product offer. Instant access keeps the money available '
                      'if plans change. General information, not financial advice.',
    }
