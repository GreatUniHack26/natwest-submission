"""P1: synthetic persona generator. Highest priority: everything depends on this data.

Pure and deterministic: no DB access (persisting is repository.py / `make seed`).
Same (name, seed) -> identical output. Dates are anchored to config.TODAY.

Persona 'sam' (student, irregular income): 6 months of history ending at TODAY with
  - recurring: rent (1st), phone bill, 2 subscriptions
  - weekday pattern: £10-15 food on uni days (Tuesday)
  - irregular part-time shift pay
  - PLANTED for the demo:
      * eating-out spike in the last 7 days (~60% above the prior 4-week average)
      * December rent pot (£950, due 1 Dec) and emergency pot (£300)
      * closing balance £1,640 -> safe-to-spend £210 (1640 - 1250 pots - 180 bills)
        The December dip near 26 Dec is the forecast engine's job; it emerges from
        this income pattern + the pots, it is not generated here.

Balance note: the Transaction contract has no balance field, so balance = sum of
transactions. A single 'Opening balance' income row on day one makes the total exact.
Consumers detecting recurring income must ignore merchant == OPENING_BALANCE_MERCHANT.

Personas still to add (issue #4): 'family' (household_id='h1'), optional 'salaried'.
"""
import calendar
import datetime as dt
import random

from backend import config
from contracts.schemas import Pot, Transaction, User

OPENING_BALANCE_MERCHANT = "Opening balance"

HISTORY_MONTHS = 6
RENT = 475.00
PHONE_BILL = 15.00
PHONE_DAY = 12
SUBSCRIPTIONS = [("Spotify", 5.99, 3), ("Netflix", 10.99, 20)]  # (merchant, £, day of month)
UNI_WEEKDAY = 1  # Tuesday
SHIFT_GAP_DAYS = (3, 5)
SHIFT_PAY = (60, 180)

# Demo targets: safe_to_spend = balance - pots_total - upcoming_bills
POTS_TOTAL = 950.00 + 300.00
UPCOMING_BILLS = 180.00
SAFE_TO_SPEND = 210.00
TARGET_BALANCE = POTS_TOTAL + UPCOMING_BILLS + SAFE_TO_SPEND  # 1640.00

SPIKE_FACTOR = 1.6  # last 7 days of eating out vs prior 4-week weekly average

# (date, merchant, amount, category, kind). Categories follow categoriser.RULES.
_Row = tuple[dt.date, str, float, str, str]


def generate_persona(name: str, seed: int = 42) -> tuple[User, list[Transaction], list[Pot]]:
    if name == "sam":
        return _sam(seed)
    raise ValueError(f"Unknown persona {name!r} (available: 'sam')")


def _months_ago(d: dt.date, months: int) -> dt.date:
    year, month0 = divmod(d.year * 12 + d.month - 1 - months, 12)
    month = month0 + 1
    return dt.date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _eating_out(rows: list[_Row], start: dt.date, end: dt.date) -> float:
    """Total spent on 'eating out' for start <= date <= end (positive number)."""
    return -sum(r[2] for r in rows if r[3] == "eating out" and start <= r[0] <= end)


def _sam(seed: int) -> tuple[User, list[Transaction], list[Pot]]:
    rng = random.Random(seed)  # local RNG: never touch global state
    today = config.TODAY
    start = _months_ago(today, HISTORY_MONTHS)
    spike_start = today - dt.timedelta(days=6)  # the "last 7 days" window
    rows: list[_Row] = []

    next_shift = start + dt.timedelta(days=rng.randint(*SHIFT_GAP_DAYS))
    day = start
    while day <= today:
        # Recurring bills (fixed dates, fixed amounts)
        if day.day == 1:
            rows.append((day, "Landlord (rent)", -RENT, "housing", "need"))
        if day.day == PHONE_DAY:
            rows.append((day, "Giffgaff", -PHONE_BILL, "bills", "need"))
        for merchant, amount, sub_day in SUBSCRIPTIONS:
            if day.day == sub_day:
                rows.append((day, merchant, -amount, "subscriptions", "want"))

        # Uni day: food + travel
        if day.weekday() == UNI_WEEKDAY:
            rows.append((day, "Greggs (Uni)", -round(rng.uniform(10, 15), 2), "eating out", "want"))
            rows.append((day, "Metrolink", -round(rng.uniform(3, 9), 2), "transport", "need"))

        # Groceries every few days
        if rng.random() < 0.28:
            shop = rng.choice(["Tesco", "Lidl"])
            rows.append((day, shop, -round(rng.uniform(12, 35), 2), "groceries", "need"))

        # Everyday eating out. The spike week gets none here; it is planted below.
        if day < spike_start and day.weekday() != UNI_WEEKDAY and rng.random() < 0.35:
            if rng.random() < 0.6:
                rows.append((day, "Greggs", -round(rng.uniform(3, 7), 2), "eating out", "want"))
            else:
                rows.append((day, "Deliveroo", -round(rng.uniform(12, 20), 2), "eating out", "want"))

        # Irregular shift pay
        if day == next_shift:
            pay = float(rng.randint(*SHIFT_PAY))
            rows.append((day, "Cafe shift pay", pay, "income", "income"))
            next_shift = day + dt.timedelta(days=rng.randint(*SHIFT_GAP_DAYS))

        day += dt.timedelta(days=1)

    # PLANTED: eating-out spike in the last 7 days, exactly SPIKE_FACTOR x prior weekly average
    weekly_avg = _eating_out(rows, spike_start - dt.timedelta(days=28), spike_start - dt.timedelta(days=1)) / 4
    extra = round(weekly_avg * SPIKE_FACTOR - _eating_out(rows, spike_start, today), 2)
    if extra <= 0:
        raise ValueError(f"seed {seed}: baseline too low to plant the eating-out spike")
    first = round(extra * 0.55, 2)
    rows.append((today, "Deliveroo", -first, "eating out", "want"))  # also guarantees data reaches TODAY
    rows.append((today - dt.timedelta(days=5), "Deliveroo", -round(extra - first, 2), "eating out", "want"))

    # Opening balance so that sum(transactions) == TARGET_BALANCE
    opening = round(TARGET_BALANCE - sum(r[2] for r in rows), 2)
    if opening <= 0:
        raise ValueError(f"seed {seed}: income/spend mix gives a non-positive opening balance")
    rows.insert(0, (start, OPENING_BALANCE_MERCHANT, opening, "income", "income"))

    rows.sort(key=lambda r: r[0])  # stable: same-day order is generation order
    user = User(
        id="sam",
        name="Sam",
        persona="Student with irregular part-time income",
        region="Manchester",
        household_id=None,
        tone="friendly",
    )
    transactions = [
        Transaction(
            id=f"sam-t{i:04d}", user_id=user.id, date=d, merchant=m,
            amount=round(a, 2), category=c, kind=k,
        )
        for i, (d, m, a, c, k) in enumerate(rows, start=1)
    ]
    pots = [
        Pot(id="sam-p1", user_id=user.id, name="December rent", amount=950.00, due_date=dt.date(2026, 12, 1)),
        Pot(id="sam-p2", user_id=user.id, name="Emergency fund", amount=300.00, due_date=None),
    ]
    return user, transactions, pots
