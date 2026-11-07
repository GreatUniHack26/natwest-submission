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
      * a fixed study stipend bounds the next-income reservation; variable shifts remain uncertain
      * course-fee instalments on the 26th create the December cash-flow stress
        The forecast computes its risk dates from these transactions; no risk output is seeded.

Balance note: the Transaction contract has no balance field, so balance = sum of
transactions. A single 'Opening balance' income row on day one makes the total exact.
Consumers detecting recurring income must ignore merchant == OPENING_BALANCE_MERCHANT.

Issue #4 personas:
  'salaried' (generate_persona): fixed monthly salary on the 28th, comfortable margin; the
    contrast case for "recurring income is detectable".
  'family' (generate_household): two adults in household 'h1', each with their own
    transactions and balance. All shared pots are owned by the first adult (one record per
    pot, so household aggregation never double-counts). PLANTED risk: the second adult's
    agency hours are cut ~30 days before TODAY, so recent income no longer covers essentials,
    and December rent plus school costs are protected in pots.
"""
import calendar
import datetime as dt
import random

from backend import config
from contracts.schemas import Pot, Transaction, User

OPENING_BALANCE_MERCHANT = "Opening balance"
HOUSEHOLDS = ("family",)

HISTORY_MONTHS = 6
RENT = 950.00
PHONE_BILL = 15.00
PHONE_DAY = 12
UTILITIES_BILL = 154.01
UTILITIES_DAY = 15
STIPEND = 150.00
STIPEND_DAY = 20
COURSE_INSTALMENT = 800.00
COURSE_DAY = 26
SUBSCRIPTIONS = [("Spotify", 5.99, 3), ("Netflix", 10.99, 20)]  # (merchant, £, day of month)
UNI_WEEKDAY = 1  # Tuesday
SHIFT_GAP_DAYS = (3, 5)
SHIFT_PAY = (60, 180)

# Demo targets: safe_to_spend = balance - pots_total - upcoming_bills
POTS_TOTAL = 950.00 + 300.00
UPCOMING_BILLS = PHONE_BILL + UTILITIES_BILL + SUBSCRIPTIONS[1][1]  # before/on the stipend date
SAFE_TO_SPEND = 210.00
TARGET_BALANCE = POTS_TOTAL + UPCOMING_BILLS + SAFE_TO_SPEND  # 1640.00

SPIKE_FACTOR = 1.6  # last 7 days of eating out vs prior 4-week weekly average

# (date, merchant, amount, category, kind). Categories follow categoriser.RULES.
_Row = tuple[dt.date, str, float, str, str]


def generate_persona(name: str, seed: int = 42) -> tuple[User, list[Transaction], list[Pot]]:
    """Single-user personas. Multi-user households: see generate_household."""
    if name == "sam":
        return _sam(seed)
    if name == "salaried":
        return _salaried(seed)
    if name in HOUSEHOLDS:
        raise ValueError(f"{name!r} has several members: use generate_household({name!r}, seed)")
    raise ValueError(f"Unknown persona {name!r} (available: 'sam', 'salaried')")


def generate_household(
    name: str, seed: int = 42
) -> list[tuple[User, list[Transaction], list[Pot]]]:
    """Multi-user personas: one (User, transactions, pots) per member, same household_id."""
    if name == "family":
        return _family(seed)
    raise ValueError(f"Unknown household {name!r} (available: 'family')")


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
        if day.day == UTILITIES_DAY:
            rows.append((day, "Octopus Energy", -UTILITIES_BILL, "bills", "need"))
        if day.day == STIPEND_DAY:
            rows.append((day, "Study stipend", STIPEND, "income", "income"))
        if day.day == COURSE_DAY:
            rows.append((day, "Course fee instalment", -COURSE_INSTALMENT, "education", "need"))
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

        # One takeaway and one snack most weeks give the anomaly a stable baseline.
        # The spike week is planted below, including its usual Tuesday uni food.
        if day < spike_start and day.weekday() == 4:
            rows.append((day, "Deliveroo", -round(rng.uniform(12, 20), 2), "eating out", "want"))
        if day < spike_start and day.weekday() == 5:
            rows.append((day, "Greggs", -round(rng.uniform(3, 7), 2), "eating out", "want"))

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


# ---- shared helpers for the issue #4 personas ---------------------------------------

def _build(
    user: User, rows: list[_Row], start: dt.date, target_balance: float, seed: int
) -> list[Transaction]:
    """Prepend an opening balance so sum(transactions) == target_balance, then number the rows."""
    opening = round(target_balance - sum(r[2] for r in rows), 2)
    if opening <= 0:
        raise ValueError(f"seed {seed}: {user.id} would need a non-positive opening balance")
    rows = [(start, OPENING_BALANCE_MERCHANT, opening, "income", "income")] + rows
    rows.sort(key=lambda r: r[0])  # stable: opening first, same-day order = generation order
    return [
        Transaction(
            id=f"{user.id}-t{i:04d}", user_id=user.id, date=d, merchant=m,
            amount=round(a, 2), category=c, kind=k,
        )
        for i, (d, m, a, c, k) in enumerate(rows, start=1)
    ]


def _spend(rng: random.Random, lo: float, hi: float) -> float:
    return -round(rng.uniform(lo, hi), 2)


# ---- 'salaried': fixed monthly income -----------------------------------------------

SALARY = 2350.00
SALARY_DAY = 28
SALARIED_TARGET_BALANCE = 5200.00


def _salaried(seed: int) -> tuple[User, list[Transaction], list[Pot]]:
    rng = random.Random(seed)
    today = config.TODAY
    start = _months_ago(today, HISTORY_MONTHS)
    user = User(
        id="alex", name="Alex", persona="Salaried office worker, fixed monthly income",
        region="Bristol", household_id=None, tone="direct",
    )
    monthly = {  # day of month -> (merchant, £, category, kind)
        1: ("Bristol Lettings (rent)", 950.00, "housing", "need"),
        5: ("PureGym", 24.99, "fitness", "want"),
        8: ("Spotify", 11.99, "subscriptions", "want"),
        10: ("EE", 22.00, "bills", "need"),
        15: ("Bristol City Council", 138.00, "bills", "need"),
        18: ("Octopus Energy", 78.00, "bills", "need"),
        22: ("Zen Internet", 29.99, "bills", "need"),
    }
    rows: list[_Row] = []
    day = start
    while day <= today:
        if day.day == SALARY_DAY:
            rows.append((day, "Meridian Ltd (salary)", SALARY, "income", "income"))
        if day.day in monthly:
            m, amount, c, k = monthly[day.day]
            rows.append((day, m, -amount, c, k))
        if rng.random() < 0.30:
            rows.append((day, rng.choice(["Sainsbury's", "Waitrose"]), _spend(rng, 25, 70), "groceries", "need"))
        if day.weekday() < 5:
            if rng.random() < 0.5:
                rows.append((day, "First Bus", _spend(rng, 2.8, 5.6), "transport", "need"))
            if rng.random() < 0.25:
                rows.append((day, rng.choice(["Pret", "Nando's"]), _spend(rng, 7, 28), "eating out", "want"))
        if rng.random() < 0.03:
            rows.append((day, "Uniqlo", _spend(rng, 30, 80), "clothing", "want"))
        day += dt.timedelta(days=1)

    pots = [
        Pot(id="alex-p1", user_id=user.id, name="Holiday", amount=600.00, due_date=dt.date(2027, 5, 1)),
        Pot(id="alex-p2", user_id=user.id, name="Emergency fund", amount=1500.00, due_date=None),
    ]
    return user, _build(user, rows, start, SALARIED_TARGET_BALANCE, seed), pots


# ---- 'family': two adults, two children, household h1 -------------------------------

FAMILY_HOUSEHOLD_ID = "h1"
PAY_CUT_DAYS_AGO = 30  # the second adult's hours are cut this long before TODAY
CHILD_BENEFIT = 173.20  # 4-weekly, two children
CHILD_BENEFIT_GAP_DAYS = 28
FAMILY_TARGET_BALANCES = {"maya": 1200.00, "dan": 220.00}
FAMILY_POTS = [  # one record per shared pot, owned by the first adult
    ("December rent", 725.00, dt.date(2026, 12, 1)),
    ("School trip and uniform", 90.00, dt.date(2026, 12, 10)),
    ("Emergency fund", 60.00, None),
]


def _family(seed: int) -> list[tuple[User, list[Transaction], list[Pot]]]:
    rng = random.Random(seed)
    today = config.TODAY
    start = _months_ago(today, HISTORY_MONTHS)
    cut = today - dt.timedelta(days=PAY_CUT_DAYS_AGO)
    maya = User(
        id="maya", name="Maya", persona="Parent in a low-income household, part-time care shifts",
        region="Leeds", household_id=FAMILY_HOUSEHOLD_ID, tone="simple",
    )
    dan = User(
        id="dan", name="Dan", persona="Parent in a low-income household, agency warehouse work",
        region="Leeds", household_id=FAMILY_HOUSEHOLD_ID, tone="simple",
    )
    m: list[_Row] = []  # Maya: childcare, loan, council tax, food, school, benefit, care shifts
    d: list[_Row] = []  # Dan: rent, energy, fuel, agency pay (cut ~30 days ago)

    next_maya = start + dt.timedelta(days=rng.randint(1, 3))
    next_dan = start + dt.timedelta(days=rng.randint(1, 3))
    next_benefit = start + dt.timedelta(days=rng.randint(0, 6))
    day = start
    while day <= today:
        # Fixed monthly bills
        if day.day == 1:
            d.append((day, "Leeds Homes (rent)", -725.00, "housing", "need"))
        if day.day == 3:
            m.append((day, "Disney+", -4.99, "subscriptions", "want"))
        if day.day == 5:
            m.append((day, "Little Stars Club", -180.00, "childcare", "need"))
        if day.day == 10:
            m.append((day, "Provident Loan", -85.00, "debt", "need"))
        if day.day == 12:
            m.append((day, "Giffgaff", -12.00, "bills", "need"))
            d.append((day, "Lebara", -12.00, "bills", "need"))
        if day.day == 15:
            d.append((day, "British Gas", -95.00, "bills", "need"))
        if day.day == 20:
            m.append((day, "Leeds City Council", -112.00, "bills", "need"))

        # Variable spending
        if rng.random() < 0.26:
            m.append((day, rng.choice(["Aldi", "Tesco"]), _spend(rng, 28, 62), "groceries", "need"))
        if rng.random() < 0.10:
            d.append((day, "Lidl", _spend(rng, 9, 22), "groceries", "need"))
        if day.weekday() == 4 and rng.random() < 0.5:
            m.append((day, "Ark Primary School", _spend(rng, 8, 25), "school", "need"))
        if rng.random() < 0.12:
            d.append((day, "Shell", _spend(rng, 20, 40), "transport", "need"))
        if rng.random() < 0.06:
            m.append((day, "Dominos", _spend(rng, 14, 24), "eating out", "want"))
        if rng.random() < 0.04:
            m.append((day, "Primark", _spend(rng, 15, 45), "clothing", "want"))

        # Income
        if day == next_benefit:
            m.append((day, "Child Benefit", CHILD_BENEFIT, "income", "income"))
            next_benefit = day + dt.timedelta(days=CHILD_BENEFIT_GAP_DAYS)
        if day == next_maya:
            m.append((day, "Care home shifts", float(rng.randint(110, 210)), "income", "income"))
            next_maya = day + dt.timedelta(days=rng.randint(6, 8))
        if day == next_dan:
            if day < cut:
                d.append((day, "Agency work pay", float(rng.randint(130, 290)), "income", "income"))
                next_dan = day + dt.timedelta(days=rng.randint(5, 9))
            else:  # PLANTED: hours cut -> fewer, smaller payments
                d.append((day, "Agency work pay", float(rng.randint(70, 130)), "income", "income"))
                next_dan = day + dt.timedelta(days=rng.randint(12, 18))
        day += dt.timedelta(days=1)

    # Guarantee data reaches TODAY for both members (consumers anchor on the last transaction)
    m.append((today, "Aldi", _spend(rng, 18, 30), "groceries", "need"))
    d.append((today, "Shell", _spend(rng, 15, 25), "transport", "need"))

    pots = [
        Pot(id=f"{maya.id}-p{i}", user_id=maya.id, name=n, amount=a, due_date=due)
        for i, (n, a, due) in enumerate(FAMILY_POTS, start=1)
    ]
    return [
        (maya, _build(maya, m, start, FAMILY_TARGET_BALANCES[maya.id], seed), pots),
        (dan, _build(dan, d, start, FAMILY_TARGET_BALANCES[dan.id], seed), []),
    ]
