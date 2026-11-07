"""Validated what-if inputs; amounts convert to pence once at this boundary.

income_multiplier: 0..10, effective for all future scheduled income.
extra_monthly_cost: GBP 0..1e9, first due on next calendar anniversary of as_of.
extra_one_off: nonnegative GBP today, {amount, date}, or a list of dated items.
Dated costs must be within the requested horizon, inclusive. Unknown keys ignore.
Zero/default changes produce the exact baseline, including its assumptions.
"""
import datetime as dt
import math
from dataclasses import dataclass
from decimal import Decimal

from .money import pence, pounds
from .recurring import add_month


@dataclass
class Scenario:
    income_multiplier: Decimal
    monthly_cost: int
    one_off: dict[dt.date, int]
    assumptions: list[str]


def number(value, name: str, maximum: float):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not 0 <= value <= maximum or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number between 0 and {maximum:g}')
    return value


def parse_overrides(overrides: dict, as_of: dt.date, horizon: int) -> Scenario:
    if not isinstance(overrides,dict):
        raise ValueError('overrides must be an object')
    multiplier = Decimal(str(number(overrides.get('income_multiplier',1),'income_multiplier',10)))
    monthly = pence(number(overrides.get('extra_monthly_cost',0),'extra_monthly_cost',1e9))
    one_off = {}
    raw = overrides.get('extra_one_off',0)
    if isinstance(raw,(int,float)) and not isinstance(raw,bool):
        entries = [{'amount':raw,'date':as_of}]
    elif isinstance(raw,dict):
        entries = [raw]
    elif isinstance(raw,list):
        entries = raw
    else:
        raise ValueError('extra_one_off must be an amount, a dated amount object, or a list of dated objects')
    end = as_of + dt.timedelta(days=horizon)
    for entry in entries:
        if not isinstance(entry,dict) or set(entry) != {'amount','date'}:
            raise ValueError('Each extra_one_off item must contain exactly amount and date')
        amount = pence(number(entry['amount'],'extra_one_off.amount',1e9))
        raw_date = entry['date']
        try:
            day = dt.date.fromisoformat(raw_date) if isinstance(raw_date,str) else raw_date
        except ValueError as exc:
            raise ValueError('extra_one_off.date must be an ISO date') from exc
        if type(day) is not dt.date or not as_of <= day <= end:
            raise ValueError('extra_one_off.date must be within the forecast horizon')
        if amount:
            one_off[day] = one_off.get(day,0) + amount
    assumptions = []
    if multiplier != 1:
        assumptions.append(f'Scenario: future scheduled income is multiplied by {multiplier}; historical transactions are unchanged.')
    if monthly:
        assumptions.append(f'Scenario: an additional £{pounds(monthly):.2f} is paid monthly from {add_month(as_of,as_of.day)}, on day {as_of.day} clamped to short month ends.')
    assumptions += [f'Scenario: a one-off £{pounds(amount):.2f} is paid on {day}.' for day,amount in sorted(one_off.items())]
    return Scenario(multiplier,monthly,one_off,assumptions)
