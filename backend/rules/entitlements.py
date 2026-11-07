"""'Money you might be owed': deterministic checks for UK schemes, exemptions and reliefs.

Every item is backed by evidence from the user's own transactions (and their household's, when
they share one) and links to official GOV.UK guidance. It is information, never a promise:
"you may be eligible - check with the official checker".

Public API (JSON-serialisable, safe for the coach's tools and live context):

    find_entitlements(user_id) -> list[dict]      # items, best first
    entitlements_summary(user_id) -> dict         # {"user_id", "items", "total_est_value", "disclaimer"}

The rules run on a `Facts` snapshot built from (User, transactions) pairs, so each rule can be
unit-tested with constructed transactions (see `facts_from`). Figures are GOV.UK rates for the
2026/27 tax year, checked on LAST_CHECKED; each rate below cites its page.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Callable, Optional

from contracts.schemas import Transaction, User

DISCLAIMER = (
    "General information, not financial or tax advice. Eligibility depends on your full "
    "circumstances. Use the official checker to be sure."
)
LAST_CHECKED = "2026-11-07 (2026/27 rates)"

# ---- GOV.UK figures, 2026/27 (checked 2026-11-07) --------------------------------------
PERSONAL_ALLOWANCE = 12_570.00  # https://www.gov.uk/income-tax-rates
# Universal Credit, https://www.gov.uk/universal-credit/what-youll-get
UC_STANDARD_SINGLE_UNDER_25 = 338.58  # monthly; the lower rates are used when age is unknown
UC_STANDARD_COUPLE_UNDER_25 = 528.34
UC_CHILD = 303.94  # monthly, per child
UC_WORK_ALLOWANCE_WITH_HOUSING = 427.00  # monthly; the lower of the two work allowances
UC_TAPER = 0.55  # "for every £1 you earn ... your payment goes down by 55p"
UC_CAPITAL_LIMIT = 16_000.00
UC_CAPITAL_TARIFF_FROM = 6_000.00
# UC childcare costs, https://www.gov.uk/help-with-childcare-costs/universal-credit
UC_CHILDCARE_SHARE = 0.85
UC_CHILDCARE_CAP_ONE = 1_071.09  # monthly, one child
UC_CHILDCARE_CAP_TWO_PLUS = 1_836.16  # monthly, two or more children
# Child Benefit weekly rates, https://www.gov.uk/child-benefit/what-youll-get
CHILD_BENEFIT_ELDEST = 27.05
CHILD_BENEFIT_ADDITIONAL = 17.90
WARM_HOME_DISCOUNT = 150.00  # https://www.gov.uk/the-warm-home-discount-scheme
WARM_HOME_QUALIFYING_DATE = "23 August 2026"
SINGLE_PERSON_DISCOUNT = 0.25  # https://www.gov.uk/council-tax/who-has-to-pay
HELP_TO_SAVE_MAX_BONUS_4Y = 1_200.00  # https://www.gov.uk/get-help-savings-low-income/what-youll-get

GOV = "https://www.gov.uk"
BENEFITS_CALCULATOR = f"{GOV}/benefits-calculators"

OPENING_BALANCE = "opening balance"
BENEFIT_MARKERS = ("child benefit", "universal credit", "dwp", "hmrc", "tax credit")
NON_EARNINGS_MARKERS = BENEFIT_MARKERS + (
    OPENING_BALANCE, "stipend", "student finance", "student loan", "bursary", "refund", "transfer",
)
UC_MARKERS = ("universal credit", "dwp uc", "dwp")
ENERGY_MARKERS = (
    "octopus energy", "british gas", "edf", "e.on", "eon next", "ovo", "scottish power", "sse",
    "utility warehouse", "so energy", "shell energy",
)
FEE_MARKERS = ("course fee", "tuition")


# ---- facts: one snapshot of what the data shows ----------------------------------------

@dataclass
class Member:
    name: str
    annual_earnings: float  # net pay into the account, annualised (benefits/stipends excluded)
    recent_30d_earnings: float
    prior_monthly_earnings: float  # average month before the last 30 days


@dataclass
class Facts:
    user: User
    members: list[Member]
    months: int  # length of the history behind the figures, in whole months
    is_student: bool
    gets_uc: bool
    capital: float  # sum of member balances
    children: int  # 0 = no evidence of children
    child_benefit_weekly: Optional[float]
    rent_monthly: float
    childcare_monthly: float
    childcare_payee: Optional[str]
    school_spend: float
    school_payee: Optional[str]
    clothing_spend: float
    council_tax_total: float
    council_tax_annual: float
    council_tax_payee: Optional[str]
    energy_payee: Optional[str]
    energy_payer: Optional[str]
    fees_total: float
    uc_floor_monthly: Optional[float] = None  # cautious Universal Credit estimate, see _uc_floor
    notes: dict = field(default_factory=dict)

    @property
    def couple(self) -> bool:
        return len(self.members) >= 2

    @property
    def household_monthly_earnings(self) -> float:
        return sum(m.annual_earnings for m in self.members) / 12

    @property
    def uc_likely(self) -> bool:
        return self.uc_floor_monthly is not None and self.uc_floor_monthly > 0


def _lower(s: str) -> str:
    return s.strip().lower()


def _has(merchant: str, markers: tuple[str, ...]) -> bool:
    m = _lower(merchant)
    return any(k in m for k in markers)


def _is_earnings(t: Transaction) -> bool:
    return t.amount > 0 and _lower(t.category) == "income" and not _has(t.merchant, NON_EARNINGS_MARKERS)


def _span_days(txs: list[Transaction]) -> int:
    dated = [t.date for t in txs if _lower(t.merchant) != OPENING_BALANCE]
    if not dated:
        return 0
    return max(1, (max(dated) - min(dated)).days + 1)


def _months(days: int) -> int:
    """Whole months of history (bills are monthly, so averages use whole months)."""
    return max(1, round(days / 30.44)) if days else 0


def _monthly(total: float, months: int) -> float:
    return total / months if months else 0.0


def _top_payee(txs: list[Transaction]) -> Optional[str]:
    totals: dict[str, float] = {}
    for t in txs:
        totals[t.merchant] = totals.get(t.merchant, 0.0) + abs(t.amount)
    return max(totals, key=totals.get) if totals else None


def _children_from_child_benefit(weekly: float) -> int:
    extra = (weekly - CHILD_BENEFIT_ELDEST) / CHILD_BENEFIT_ADDITIONAL
    return max(1, 1 + round(extra))


def facts_from(user: User, household: list[tuple[User, list[Transaction]]]) -> Facts:
    """Build the snapshot from (member, transactions) pairs. `household` includes `user`."""
    all_txs = [t for _, txs in household for t in txs]
    days = max((_span_days(txs) for _, txs in household), default=0)
    last = max((t.date for t in all_txs), default=dt.date.today())
    recent_from = last - dt.timedelta(days=29)

    months = _months(days)
    members: list[Member] = []
    for u, txs in household:
        span = _span_days(txs)
        pay = [t for t in txs if _is_earnings(t)]
        recent = sum(t.amount for t in pay if t.date >= recent_from)
        before = sum(t.amount for t in pay if t.date < recent_from)
        before_days = max(0, span - 30)
        members.append(Member(
            name=u.name,
            annual_earnings=round(_monthly(sum(t.amount for t in pay), _months(span)) * 12, 2),
            recent_30d_earnings=round(recent, 2),
            prior_monthly_earnings=round(before * 30.44 / before_days, 2) if before_days else 0.0,
        ))

    spend = [t for t in all_txs if t.amount < 0]
    cb = [t for t in all_txs if t.amount > 0 and "child benefit" in _lower(t.merchant)]
    cb_weekly = round(sum(t.amount for t in cb) / len(cb) / 4, 2) if cb else None  # paid 4-weekly
    childcare = [t for t in spend if _lower(t.category) == "childcare"]
    school = [t for t in spend if _lower(t.category) == "school" or "school" in _lower(t.merchant)]
    council = [t for t in spend if "council" in _lower(t.merchant) and _lower(t.category) in ("bills", "council tax")]
    energy = [t for t in spend if _has(t.merchant, ENERGY_MARKERS)]
    fees = [t for t in spend if _lower(t.category) == "education" and _has(t.merchant, FEE_MARKERS)]
    rent = [t for t in spend if _lower(t.category) == "housing"]
    clothing = [t for t in spend if _lower(t.category) == "clothing"]

    if cb_weekly:
        children = _children_from_child_benefit(cb_weekly)
    else:
        children = 1 if (childcare or school) else 0

    energy_payer = None
    if energy:
        payer_id = max({t.user_id for t in energy}, key=lambda uid: sum(-t.amount for t in energy if t.user_id == uid))
        energy_payer = next((u.name for u, _ in household if u.id == payer_id), None)

    council_total = round(-sum(t.amount for t in council), 2)
    facts = Facts(
        user=user,
        members=members,
        months=months,
        is_student=any("student" in _lower(u.persona) for u, _ in household),
        gets_uc=any(t.amount > 0 and _has(t.merchant, UC_MARKERS) for t in all_txs),
        capital=round(sum(t.amount for t in all_txs), 2),
        children=children,
        child_benefit_weekly=cb_weekly,
        rent_monthly=round(_monthly(-sum(t.amount for t in rent), months), 2),
        childcare_monthly=round(_monthly(-sum(t.amount for t in childcare), months), 2),
        childcare_payee=_top_payee(childcare),
        school_spend=round(-sum(t.amount for t in school), 2),
        school_payee=_top_payee(school),
        clothing_spend=round(-sum(t.amount for t in clothing), 2),
        council_tax_total=council_total,
        council_tax_annual=round(_monthly(council_total, months) * 12, 2),
        council_tax_payee=_top_payee(council),
        energy_payee=_top_payee(energy),
        energy_payer=energy_payer,
        fees_total=round(-sum(t.amount for t in fees), 2),
    )
    facts.uc_floor_monthly = _uc_floor(facts)
    return facts


def _uc_floor(f: Facts) -> Optional[float]:
    """A cautious monthly Universal Credit estimate from GOV.UK rates, or None if UC doesn't fit.

    Deliberately low: under-25 standard allowance (age unknown), no housing or childcare amounts,
    the lower work allowance, and the household's 6-month average pay (not its recent, lower pay).
    """
    if f.is_student or f.gets_uc or not f.members or f.capital > UC_CAPITAL_LIMIT:
        return None
    standard = UC_STANDARD_COUPLE_UNDER_25 if f.couple else UC_STANDARD_SINGLE_UNDER_25
    max_award = standard + UC_CHILD * f.children
    work_allowance = UC_WORK_ALLOWANCE_WITH_HOUSING if (f.children and f.rent_monthly > 0) else 0.0
    taper = UC_TAPER * max(0.0, f.household_monthly_earnings - work_allowance)
    return round(max_award - taper, 2)


# ---- helpers for items -------------------------------------------------------------------

def _gbp(x: float) -> str:
    return f"£{x:,.0f}" if abs(x - round(x)) < 0.005 or abs(x) >= 1000 else f"£{x:,.2f}"


def _names(members: list[Member]) -> str:
    names = [m.name for m in members]
    return " and ".join(names) if len(names) <= 2 else ", ".join(names[:-1]) + " and " + names[-1]


def _item(id: str, title: str, why_you: str, est_value: Optional[float], confidence: str,
          how_to_claim: str, gov_url: str, checker_url: Optional[str], depends_on: Optional[str] = None) -> dict:
    return {
        "id": id,
        "title": title,
        "why_you": why_you,
        "est_value": round(est_value) if est_value else None,
        "confidence": confidence,
        "how_to_claim": how_to_claim,
        "gov_url": gov_url,
        "checker_url": checker_url,
        "depends_on": depends_on,
        "last_checked": LAST_CHECKED,
    }


def _subject(f: Facts) -> str:
    return "Your household" if f.couple else "You"


def _pay_line(f: Facts) -> str:
    who = "Your household's" if f.couple else "Your"
    line = f"{who} take-home pay averages about {_gbp(round(f.household_monthly_earnings))} a month."
    drops = [m for m in f.members if m.prior_monthly_earnings and m.recent_30d_earnings < 0.75 * m.prior_monthly_earnings]
    if drops:
        m = drops[0]
        name = "Your" if m.name == f.user.name else f"{m.name}'s"
        line += (f" {name} pay fell to {_gbp(round(m.recent_30d_earnings))} in the last 30 days, "
                 f"from about {_gbp(round(m.prior_monthly_earnings))} a month.")
    return line


# ---- rules -----------------------------------------------------------------------------
# Each rule: (Facts) -> Optional[dict]. Return None unless the data supports the item.

def universal_credit(f: Facts) -> Optional[dict]:
    if not f.uc_likely:
        return None
    kids = f" with {f.children} child{'ren' if f.children != 1 else ''}" if f.children else ""
    why = (f"{_pay_line(f)} We can't see any Universal Credit payments. Using GOV.UK rates, a "
           f"{'couple' if f.couple else 'single person'}{kids} could get at least "
           f"{_gbp(round(f.uc_floor_monthly))} a month. That's before any help with rent"
           f"{' or childcare' if f.childcare_monthly else ''}, so the real amount may be higher.")
    return _item(
        "universal_credit", "Universal Credit", why, f.uc_floor_monthly * 12, "likely",
        "Use a free benefits calculator first. Couples make one joint claim online.",
        f"{GOV}/universal-credit", BENEFITS_CALCULATOR,
    )


def uc_childcare(f: Facts) -> Optional[dict]:
    if f.childcare_monthly <= 0 or not (f.gets_uc or f.uc_likely):
        return None
    if not all(m.annual_earnings > 0 for m in f.members):
        return None  # childcare help needs every partner in work (with narrow exceptions)
    cap = UC_CHILDCARE_CAP_TWO_PLUS if f.children >= 2 else UC_CHILDCARE_CAP_ONE
    monthly = min(UC_CHILDCARE_SHARE * f.childcare_monthly, cap)
    pays = "Your household pays" if f.couple else "You pay"
    why = (f"{pays} about {_gbp(round(f.childcare_monthly))} a month to {f.childcare_payee}, and "
           f"{'you both work' if f.couple else 'you work'}. Universal Credit can pay back up to 85% of "
           f"approved childcare. That's about {_gbp(round(monthly))} a month.")
    return _item(
        "uc_childcare", "Help with childcare costs", why, monthly * 12, "worth checking",
        "Report your childcare costs in your Universal Credit account. The provider must be registered with Ofsted.",
        f"{GOV}/help-with-childcare-costs/universal-credit", BENEFITS_CALCULATOR,
        depends_on=None if f.gets_uc else "universal_credit",
    )


def council_tax_reduction(f: Facts) -> Optional[dict]:
    if f.council_tax_total <= 0 or f.is_student or not (f.gets_uc or f.uc_likely):
        return None
    why = (f"{_subject(f)} paid {_gbp(f.council_tax_total)} to {f.council_tax_payee} in the last {f.months} months. "
           "Councils can cut the bill for households on a low income, sometimes to nothing.")
    return _item(
        "council_tax_reduction", "Council Tax Reduction", why, None, "likely",
        f"Apply to {f.council_tax_payee or 'your council'}. Each council runs its own scheme.",
        f"{GOV}/apply-council-tax-reduction", f"{GOV}/apply-council-tax-reduction",
    )


def council_tax_student(f: Facts) -> Optional[dict]:
    if f.council_tax_total <= 0 or not f.is_student:
        return None
    all_students = not f.couple  # a household of one student
    share = 1.0 if all_students else SINGLE_PERSON_DISCOUNT
    why = (f"You may not need to pay council tax as a full-time student. You paid {_gbp(f.council_tax_total)} "
           f"to {f.council_tax_payee} in the last {f.months} months."
           f"{'' if all_students else ' If you live with someone who is not a student, you may get 25% off instead.'}")
    return _item(
        "council_tax_student", "Student council tax exemption", why, f.council_tax_annual * share,
        "likely" if all_students else "worth checking",
        "Ask your university for a student certificate and send it to your council.",
        f"{GOV}/council-tax/discounts-for-full-time-students", f"{GOV}/apply-for-council-tax-discount",
    )


def council_tax_single_person(f: Facts) -> Optional[dict]:
    if f.council_tax_total <= 0 or f.is_student or f.couple or f.user.household_id:
        return None
    est = f.council_tax_annual * SINGLE_PERSON_DISCOUNT
    why = (f"You seem to live alone, and you paid {_gbp(f.council_tax_total)} to {f.council_tax_payee} "
           f"in the last {f.months} months. If you're the only adult at home, you get 25% off. "
           f"That's about {_gbp(round(est))} a year, unless it's already on your bill.")
    return _item(
        "council_tax_single_person", "Single person council tax discount", why, est, "worth checking",
        "Check your bill for the discount. If it's not there, apply to your council.",
        f"{GOV}/council-tax/who-has-to-pay", f"{GOV}/apply-for-council-tax-discount",
    )


def free_school_meals(f: Facts) -> Optional[dict]:
    if f.school_spend <= 0 or not (f.gets_uc or f.uc_likely):
        return None
    why = (f"{_subject(f)} paid {_gbp(f.school_spend)} to {f.school_payee} in the last {f.months} months. "
           "From September 2026, every child in a family on Universal Credit in England can get free school meals.")
    return _item(
        "free_school_meals", "Free school meals", why, None, "likely" if f.gets_uc else "worth checking",
        "Apply through your council's website once you get Universal Credit.",
        f"{GOV}/apply-free-school-meals", f"{GOV}/apply-free-school-meals",
        depends_on=None if f.gets_uc else "universal_credit",
    )


def school_uniform(f: Facts) -> Optional[dict]:
    if f.school_spend <= 0 or not (f.gets_uc or f.uc_likely):
        return None
    clothes = f", and spent {_gbp(f.clothing_spend)} on clothes" if f.clothing_spend else ""
    has = "Your household has" if f.couple else "You have"
    why = (f"{has} school costs at {f.school_payee}{clothes}. Some councils help with school uniform "
           "on a low income. It depends where you live.")
    return _item(
        "school_uniform", "Help with school uniform costs", why, None, "worth checking",
        "Ask your council, or the school's headteacher, what help is available.",
        f"{GOV}/school-uniform", f"{GOV}/find-local-council",
    )


def warm_home_discount(f: Facts) -> Optional[dict]:
    if not f.energy_payee or not (f.gets_uc or f.uc_likely):
        return None
    other = f.couple and f.energy_payer and f.energy_payer != f.user.name
    who = f"{f.energy_payer} pays" if other else "You pay"
    why = (f"{who} {f.energy_payee} for energy. Households on Universal Credit can get £150 off the electricity "
           f"bill each winter. This winter's qualifying date was {WARM_HOME_QUALIFYING_DATE}, so a new claim "
           "would count from next winter.")
    return _item(
        "warm_home_discount", "Warm Home Discount", why, WARM_HOME_DISCOUNT, "worth checking",
        "It's usually automatic once you get a qualifying benefit. The electricity bill must be in your name or your partner's.",
        f"{GOV}/the-warm-home-discount-scheme", f"{GOV}/the-warm-home-discount-scheme",
        depends_on=None if f.gets_uc else "universal_credit",
    )


def help_to_save(f: Facts) -> Optional[dict]:
    if not (f.gets_uc or f.uc_likely) or not any(m.annual_earnings > 0 for m in f.members):
        return None
    why = ("You're working on a low income. On Universal Credit, Help to Save adds 50p for every £1 you save. "
           f"That's up to {_gbp(HELP_TO_SAVE_MAX_BONUS_4Y)} in bonuses over 4 years.")
    return _item(
        "help_to_save", "Help to Save bonus", why, None, "worth checking",
        "Open an account on GOV.UK once you get Universal Credit. You can save £1 to £50 a month.",
        f"{GOV}/get-help-savings-low-income", f"{GOV}/get-help-savings-low-income/eligibility",
        depends_on=None if f.gets_uc else "universal_credit",
    )


def tax_refund_low_pay(f: Facts) -> Optional[dict]:
    low = [m for m in f.members if 0 < m.annual_earnings < PERSONAL_ALLOWANCE]
    if not low:
        return None
    def who(m: Member) -> str:
        return "your pay" if m.name == f.user.name else f"{m.name}'s pay"
    parts = [f"{who(m)} is about {_gbp(round(m.annual_earnings))} a year" for m in low]
    lead = " and ".join(parts)
    lead = lead[0].upper() + lead[1:]
    below = "both below" if len(low) > 1 else "below"
    why = (f"{lead}, {below} the {_gbp(PERSONAL_ALLOWANCE)} tax-free Personal Allowance. If tax was taken off "
           "(for example on an emergency tax code), you may be able to get it back.")
    return _item(
        "tax_refund", "Income Tax refund", why, None, "worth checking",
        "Check your payslips for tax deducted, then use HMRC's tax refund checker.",
        f"{GOV}/income-tax-rates", f"{GOV}/claim-tax-refund",
    )


def student_finance(f: Facts) -> Optional[dict]:
    if not f.is_student or f.fees_total <= 0:
        return None
    why = (f"You paid {_gbp(f.fees_total)} in course fees yourself in the last {f.months} months. A Tuition Fee "
           "Loan can pay your fees straight to your college. You only repay it once you earn over a set amount. "
           "Some extra help for students on a low income doesn't need paying back.")
    return _item(
        "student_finance", "Student finance for your course fees", why, None, "worth checking",
        "Check what you could get with the student finance calculator, then apply to Student Finance.",
        f"{GOV}/student-finance", f"{GOV}/student-finance-calculator",
    )


RULES: list[Callable[[Facts], Optional[dict]]] = [
    universal_credit,
    uc_childcare,
    council_tax_reduction,
    council_tax_student,
    council_tax_single_person,
    free_school_meals,
    school_uniform,
    warm_home_discount,
    help_to_save,
    tax_refund_low_pay,
    student_finance,
]


def assess(facts: Facts) -> list[dict]:
    """Run every rule; a crashing rule is skipped. 'likely' first, then by value."""
    items = []
    for rule in RULES:
        try:
            item = rule(facts)
        except Exception:
            item = None
        if item:
            items.append(item)
    order = {"likely": 0, "worth checking": 1}
    return sorted(items, key=lambda i: (order.get(i["confidence"], 2), -(i["est_value"] or 0)))


def _household(user: User) -> list[tuple[User, list[Transaction]]]:
    from backend import data

    members = [user]
    if user.household_id:
        others = [m for m in data.get_household_members(user.household_id) if m.id != user.id]
        members += others
    return [(m, data.get_transactions(m.id)) for m in members]


def find_entitlements(user_id: str) -> list[dict]:
    """Items for `user_id` (household-wide when they share one). Raises KeyError for unknown users."""
    from backend import data

    user = data.get_user(user_id)
    return assess(facts_from(user, _household(user)))


def entitlements_summary(user_id: str) -> dict:
    """The API/coach payload. Raises KeyError for unknown users."""
    items = find_entitlements(user_id)
    return {
        "user_id": user_id,
        "items": items,
        "total_est_value": sum(i["est_value"] or 0 for i in items),
        "disclaimer": DISCLAIMER,
    }
