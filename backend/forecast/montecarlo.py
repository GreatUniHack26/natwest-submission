"""Monte Carlo digital twin: many possible futures instead of one expected line.

Each simulated future replays the user's own life with realistic noise:
- Everyday spending: each future day draws a real past day with the same weekday
  from the last 84 days (bootstrap), so habits like "£12 on uni Tuesdays" carry over.
- Recurring bills and income: on each scheduled date, amount ~ Normal(mean, observed
  std) (income std includes timing variation), never flipping sign. Irregular income
  (std > 0) can also arrive 1-3 days late with 25% probability.
- Unexpected expenses: a Poisson shock process (on average one every 45 days) with
  amounts drawn log-normally around 4x a typical day's spend (median), capped at
  £600: the boiler, the phone screen, the school trip nobody mentioned.

Deterministic: the RNG is seeded from (user_id, as_of, sims), so the demo and tests
always see the same odds. Pure Python; no LLM. Results are scenarios, not promises.
"""
import datetime as dt
import hashlib
import math
import random
from collections import defaultdict
from statistics import mean

from backend import config
from .baseline import LOOKBACK_DAYS, everyday
from .inputs import Inputs, load_inputs
from .money import pence, pounds
from .recurring import occurrences, patterns, payment_std
from .reservations import bill_schedule, protected_on, remaining_pots

DEFAULT_SIMS = 1000
SHOCK_EVERY_DAYS = 45
SHOCK_CAP_PENCE = 60_000
LATE_PAY_PROB = 0.25


def _seed(user_id: str, as_of: dt.date, sims: int, tag: str) -> int:
    return int(hashlib.sha256(f'{user_id}|{as_of}|{sims}|{tag}'.encode()).hexdigest()[:16], 16)


def _weekday_days(data: Inputs) -> dict[int, list[int]]:
    """Real past daily spend totals (pence) grouped by weekday, zeros included."""
    totals: dict[dt.date, int] = defaultdict(int)
    for tx in everyday(data.transactions, data.as_of):
        totals[tx.date] += -pence(tx.amount)
    by_weekday: dict[int, list[int]] = defaultdict(list)
    for offset in range(1, LOOKBACK_DAYS + 1):
        day = data.as_of - dt.timedelta(days=offset)
        by_weekday[day.weekday()].append(totals[day])
    return by_weekday


def _schedule(data: Inputs, end: dt.date, income_on: bool):
    items = []
    for item, observations in patterns(data.transactions):
        if item.amount > 0 and not income_on:
            continue
        std = payment_std(item, observations) * 100
        for day in occurrences(item, data.as_of + dt.timedelta(days=1), end):
            items.append((day, pence(item.amount), std, item.amount > 0))
    return items


def _shock_median(days_by_weekday: dict[int, list[int]]) -> float:
    typical_day = mean([v for values in days_by_weekday.values() for v in values] or [0]) or 1500
    return max(2_000, 4 * typical_day)


def _run(data: Inputs, horizon: int, sims: int, *, income_on: bool, tag: str):
    rng = random.Random(_seed(data.user_id, data.as_of, sims, tag))
    end = data.as_of + dt.timedelta(days=horizon)
    days_by_weekday = _weekday_days(data)
    shock_median = _shock_median(days_by_weekday)
    schedule = _schedule(data, end, income_on)

    paths = []
    for _ in range(sims):
        flows = defaultdict(int)
        for day, amount, std, is_income in schedule:
            draw = rng.gauss(amount, std) if std > 0 else amount
            draw = max(0, draw) if is_income else min(0, draw)
            if is_income and std > 0 and rng.random() < LATE_PAY_PROB:
                day = day + dt.timedelta(days=rng.randint(1, 3))
            flows[day] += round(draw)
        balance = data.balance
        path = [balance]
        for offset in range(1, horizon + 1):
            day = data.as_of + dt.timedelta(days=offset)
            pool = days_by_weekday.get(day.weekday()) or [0]
            balance += flows[day] - rng.choice(pool)
            if rng.random() < 1 / SHOCK_EVERY_DAYS:
                balance -= min(SHOCK_CAP_PENCE, round(rng.lognormvariate(math.log(shock_median), 0.6)))
            path.append(balance)
        paths.append(path)
    return paths


def _quantile(sorted_values: list[int], q: float) -> int:
    index = min(len(sorted_values) - 1, max(0, round(q * (len(sorted_values) - 1))))
    return sorted_values[index]


def simulate_futures(user_id: str, horizon_days: int = 90, sims: int = DEFAULT_SIMS) -> dict:
    if not 7 <= horizon_days <= 180:
        raise ValueError('horizon_days must be between 7 and 180')
    if not 100 <= sims <= 5000:
        raise ValueError('sims must be between 100 and 5000')
    data = load_inputs(user_id, config.TODAY)
    shock_median = _shock_median(_weekday_days(data))
    days = [data.as_of + dt.timedelta(days=i) for i in range(horizon_days + 1)]
    paths = _run(data, horizon_days, sims, income_on=True, tag='base')

    items = [item for item, _ in patterns(data.transactions)]
    bills = bill_schedule(items, data.as_of + dt.timedelta(days=1), days[-1])
    pots = remaining_pots(data.pots, data.transactions, data.as_of)
    protected = [protected_on(pots, bills, day) for day in days]

    below_zero_by = [0] * len(days)
    first_negative = []
    dipped_pots = 0
    for path in paths:
        first = next((i for i, b in enumerate(path) if b < 0), None)
        if first is not None:
            first_negative.append(first)
            for i in range(first, len(days)):
                below_zero_by[i] += 1
        if any(protected[i] > 0 and b < protected[i] for i, b in enumerate(path)):
            dipped_pots += 1

    points = []
    for i, day in enumerate(days):
        if i % 7 and i != horizon_days:
            continue
        column = sorted(path[i] for path in paths)
        points.append({
            'date': day.isoformat(),
            'p10': pounds(_quantile(column, 0.10)),
            'p50': pounds(_quantile(column, 0.50)),
            'p90': pounds(_quantile(column, 0.90)),
            'chance_below_zero': round(below_zero_by[i] / sims, 3),
        })

    coin_flip = next((days[i].isoformat() for i, n in enumerate(below_zero_by) if n / sims >= 0.5), None)
    first_negative.sort()
    typical_first = days[_quantile(first_negative, 0.5)].isoformat() if first_negative else None

    # Runway: if income stopped today, how long until the money (excluding pots) runs out?
    no_income = _run(data, horizon_days, sims, income_on=False, tag='runway')
    runway_days = []
    for path in no_income:
        hit = next((i for i, b in enumerate(path) if b < protected[i]), None)
        runway_days.append(hit if hit is not None else horizon_days)
    runway_days.sort()

    return {
        'user_id': user_id,
        'simulations': sims,
        'horizon_days': horizon_days,
        'chance_below_zero': round(below_zero_by[-1] / sims, 3),
        'chance_below_zero_within': {
            str(d): round(below_zero_by[d] / sims, 3) for d in (30, 60, 90) if d <= horizon_days
        },
        'chance_dip_into_pots': round(dipped_pots / sims, 3),
        'coin_flip_date': coin_flip,
        'typical_first_negative_date': typical_first,
        'runway_days_if_income_stops': _quantile(runway_days, 0.5),
        'runway_capped': _quantile(runway_days, 0.5) >= horizon_days,
        'points': points,
        'assumptions': [
            f'{sims} simulated futures over {horizon_days} days, seeded so results are repeatable.',
            'Everyday spending replays your own past days (same weekday, last 84 days).',
            'Bills and income vary by their observed spread; irregular pay can arrive 1-3 days late.',
            f'Unexpected costs occur about once every {SHOCK_EVERY_DAYS} days, typically around '
            f'£{pounds(round(shock_median)):.0f}, capped at £{pounds(SHOCK_CAP_PENCE):.0f}.',
            'Runway assumes all income stops today and pots stay untouched; it is the median across futures.',
        ],
    }
