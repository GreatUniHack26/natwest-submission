"""'Money you might be owed' (backend.rules.entitlements): one test per rule with constructed
transactions, plus the endpoint against the seeded personas (no network/LLM)."""
import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.data.seed import seed
from backend.main import app
from backend.rules import entitlements as ent
from contracts.schemas import Transaction, User

START = dt.date(2026, 5, 7)
MONTHS = 6


def _user(uid="u1", name="Uma", persona="Office worker", household_id=None) -> User:
    return User(id=uid, name=name, persona=persona, region="Leeds", household_id=household_id)


class Ledger:
    """Builds six months of transactions for one user."""

    def __init__(self, uid="u1", opening=500.0):
        self.uid, self.rows = uid, []
        self.add(START, "Opening balance", opening, "income")

    def add(self, date, merchant, amount, category, kind=None):
        kind = kind or ("income" if amount > 0 else "need")
        self.rows.append(Transaction(id=f"{self.uid}-{len(self.rows)}", user_id=self.uid, date=date,
                                     merchant=merchant, amount=amount, category=category, kind=kind))
        return self

    def monthly(self, merchant, amount, category, day=5):
        for m in range(MONTHS):
            y, mo = divmod(START.month - 1 + m + (1 if day < START.day else 0), 12)
            self.add(dt.date(START.year + y, mo + 1, day), merchant, amount, category)
        return self

    def every(self, days, merchant, amount, category, start=START, end=dt.date(2026, 11, 7)):
        d = start
        while d <= end:
            self.add(d, merchant, amount, category)
            d += dt.timedelta(days=days)
        return self

    def done(self):
        if max(t.date for t in self.rows) < dt.date(2026, 11, 7):
            self.add(dt.date(2026, 11, 7), "Tesco", -10.0, "groceries")
        return self.rows


def _facts(*members):
    """members: (User, Ledger) pairs; the first is the viewer."""
    pairs = [(u, led.done()) for u, led in members]
    return ent.facts_from(pairs[0][0], pairs)


def _family(with_childcare=True, energy=True, school=True, cb=True):
    maya = _user("m", "Maya", "Parent, care shifts", "h1")
    dan = _user("d", "Dan", "Parent, agency work", "h1")
    lm = Ledger("m").every(7, "Care home shifts", 160.0, "income")
    ld = Ledger("d").every(7, "Agency work pay", 200.0, "income").monthly("Leeds Homes (rent)", -725.0, "housing", 1)
    if cb:
        lm.every(28, "Child Benefit", 173.20, "income")
    if with_childcare:
        lm.monthly("Little Stars Club", -180.0, "childcare")
    if school:
        lm.every(14, "Ark Primary School", -15.0, "school")
        lm.add(dt.date(2026, 9, 1), "Primark", -40.0, "clothing")
    if energy:
        ld.monthly("British Gas", -95.0, "bills", 15)
    lm.monthly("Leeds City Council", -112.0, "bills", 20)
    return _facts((maya, lm), (dan, ld))


def _ids(facts):
    return [i["id"] for i in ent.assess(facts)]


# ---- facts ---------------------------------------------------------------------------------

def test_children_counted_from_child_benefit_rates():
    assert ent._children_from_child_benefit(27.05) == 1
    assert ent._children_from_child_benefit(43.30) == 2  # 2025/26 amounts still map to 2 children
    assert ent._children_from_child_benefit(27.05 + 2 * 17.90) == 3


def test_facts_exclude_benefits_and_opening_balance_from_earnings():
    f = _family()
    maya = f.members[0]
    assert maya.name == "Maya"
    assert 160 * 52 * 0.9 < maya.annual_earnings < 160 * 52 * 1.1  # weekly shifts, not Child Benefit
    assert f.children == 2 and f.couple and f.rent_monthly == 725.0
    assert f.childcare_monthly == 180.0 and f.council_tax_annual == 112.0 * 12


# ---- one test per rule ---------------------------------------------------------------------

def test_universal_credit_cautious_floor_for_low_income_family():
    f = _family()
    item = ent.universal_credit(f)
    assert item and item["confidence"] == "likely"
    expected = 528.34 + 2 * 303.94 - 0.55 * (f.household_monthly_earnings - 427)
    assert item["est_value"] == round(expected * 12)
    assert "can't see any Universal Credit payments" in item["why_you"]
    assert item["checker_url"] == "https://www.gov.uk/benefits-calculators"


def test_universal_credit_not_for_high_earners_students_or_existing_claims():
    alex = _user()
    rich = Ledger().monthly("Meridian Ltd (salary)", 2350.0, "income", 28)
    assert ent.universal_credit(_facts((alex, rich))) is None
    student = _user(persona="Student with part-time income")
    assert ent.universal_credit(_facts((student, Ledger().every(7, "Cafe shift pay", 60.0, "income")))) is None
    family_on_uc = _user("m", "Maya", "Parent", "h1")
    led = Ledger("m").every(7, "Care home shifts", 160.0, "income").monthly("Universal Credit", 400.0, "income", 9)
    assert ent.universal_credit(_facts((family_on_uc, led.every(28, "Child Benefit", 27.05 * 4, "income")))) is None


def test_universal_credit_respects_capital_limit():
    u = _user("m", "Maya", "Parent", "h1")
    led = Ledger("m", opening=20_000).every(7, "Care home shifts", 160.0, "income").every(28, "Child Benefit", 108.2, "income")
    assert ent.universal_credit(_facts((u, led))) is None


def test_pay_drop_is_named_in_evidence():
    maya = _user("m", "Maya", "Parent", "h1")
    dan = _user("d", "Dan", "Parent", "h1")
    lm = Ledger("m").every(7, "Care home shifts", 160.0, "income").every(28, "Child Benefit", 173.2, "income")
    ld = Ledger("d").every(7, "Agency work pay", 250.0, "income", end=dt.date(2026, 10, 1))
    ld.add(dt.date(2026, 10, 25), "Agency work pay", 90.0, "income")
    item = ent.universal_credit(_facts((maya, lm), (dan, ld)))
    assert "Dan's pay fell to £90 in the last 30 days" in item["why_you"]


def test_uc_childcare_is_85_percent_and_needs_both_working():
    item = ent.uc_childcare(_family())
    assert item["est_value"] == round(0.85 * 180 * 12) and item["depends_on"] == "universal_credit"
    assert "Little Stars Club" in item["why_you"]
    assert ent.uc_childcare(_family(with_childcare=False)) is None
    maya = _user("m", "Maya", "Parent", "h1")
    dan = _user("d", "Dan", "Parent", "h1")
    lm = Ledger("m").every(7, "Care home shifts", 160.0, "income").monthly("Little Stars Club", -180.0, "childcare")
    assert ent.uc_childcare(_facts((maya, lm), (dan, Ledger("d")))) is None  # Dan has no pay


def test_uc_childcare_capped_at_govuk_monthly_maximum():
    u = _user("m", "Maya", "Parent", "h1")
    led = Ledger("m").every(7, "Care home shifts", 100.0, "income").monthly("Nursery", -2000.0, "childcare")
    item = ent.uc_childcare(_facts((u, led)))  # one child (no Child Benefit seen) -> one-child cap
    assert item["est_value"] == round(1071.09 * 12)


def test_council_tax_reduction_for_low_income_council_tax_payers():
    item = ent.council_tax_reduction(_family())
    assert item["confidence"] == "likely" and "Leeds City Council" in item["why_you"]
    assert item["est_value"] is None


def test_council_tax_student_exemption():
    sam = _user("s", "Sam", "Student with irregular part-time income")
    led = Ledger("s").every(5, "Cafe shift pay", 90.0, "income").monthly("Manchester City Council", -120.0, "bills", 10)
    item = ent.council_tax_student(_facts((sam, led)))
    assert item["confidence"] == "likely" and item["est_value"] == 1440
    assert item["why_you"].startswith("You may not need to pay council tax as a full-time student. You paid £720 to Manchester City Council")
    no_bill = Ledger("s").every(5, "Cafe shift pay", 90.0, "income")
    assert ent.council_tax_student(_facts((sam, no_bill))) is None


def test_single_person_discount_for_someone_living_alone():
    alex = _user("a", "Alex", "Salaried office worker")
    led = Ledger("a").monthly("Meridian Ltd (salary)", 2350.0, "income", 28).monthly("Bristol City Council", -138.0, "bills", 15)
    item = ent.council_tax_single_person(_facts((alex, led)))
    assert item["est_value"] == 414 and item["confidence"] == "worth checking"
    shared = _user("a", "Alex", "Salaried office worker", household_id="h9")
    assert ent.council_tax_single_person(_facts((shared, led))) is None


def test_free_school_meals_and_uniform_need_school_costs_and_low_income():
    f = _family()
    fsm = ent.free_school_meals(f)
    assert fsm["depends_on"] == "universal_credit" and "Ark Primary School" in fsm["why_you"]
    uni = ent.school_uniform(f)
    assert uni and uni["checker_url"] == "https://www.gov.uk/find-local-council"
    no_school = _family(school=False, with_childcare=False)
    assert ent.free_school_meals(no_school) is None and ent.school_uniform(no_school) is None


def test_warm_home_discount_names_bill_payer():
    item = ent.warm_home_discount(_family())
    assert item["est_value"] == 150 and item["why_you"].startswith("Dan pays British Gas")
    assert "23 August 2026" in item["why_you"]
    assert ent.warm_home_discount(_family(energy=False)) is None


def test_help_to_save_for_low_income_workers():
    item = ent.help_to_save(_family())
    assert item and "£1,200" in item["why_you"] and item["est_value"] is None
    alex = _user()
    assert ent.help_to_save(_facts((alex, Ledger().monthly("Salary", 2350.0, "income", 28)))) is None


def test_tax_refund_only_below_personal_allowance():
    sam = _user("s", "Sam", "Student")
    item = ent.tax_refund_low_pay(_facts((sam, Ledger("s").every(7, "Cafe shift pay", 150.0, "income"))))
    assert item and "below the £12,570" in item["why_you"]
    alex = _user()
    assert ent.tax_refund_low_pay(_facts((alex, Ledger().monthly("Salary", 2350.0, "income", 28)))) is None
    both = ent.tax_refund_low_pay(_family())
    assert both["why_you"].startswith("Your pay is about") and "Dan's pay" in both["why_you"] and "both below" in both["why_you"]


def test_student_finance_when_paying_fees_directly():
    sam = _user("s", "Sam", "Student with irregular part-time income")
    led = Ledger("s").monthly("Course fee instalment", -800.0, "education", 26)
    item = ent.student_finance(_facts((sam, led)))
    assert item and "£4,800 in course fees" in item["why_you"]
    assert item["checker_url"] == "https://www.gov.uk/student-finance-calculator"
    assert ent.student_finance(_facts((_user(), led))) is None  # not a student


# ---- assembly ------------------------------------------------------------------------------

def test_items_are_ordered_json_safe_and_official():
    items = ent.assess(_family())
    assert items[0]["id"] == "universal_credit"
    confs = [i["confidence"] for i in items]
    assert confs == sorted(confs, key=lambda c: c != "likely")
    json.dumps(items)
    assert "—" not in json.dumps(items, ensure_ascii=False) and "FinTime" not in json.dumps(items)
    for i in items:
        assert i["gov_url"].startswith("https://www.gov.uk/")
        assert i["checker_url"] is None or i["checker_url"].startswith("https://www.gov.uk/")
        assert i["confidence"] in ("likely", "worth checking")
        assert i["why_you"] and i["how_to_claim"] and i["last_checked"]


def test_a_crashing_rule_is_skipped(monkeypatch):
    def boom(_f):
        raise RuntimeError("rule crashed")

    monkeypatch.setattr(ent, "RULES", [boom, ent.help_to_save])
    assert _ids(_family()) == ["help_to_save"]


def test_nothing_for_comfortable_single_earner_without_bills():
    assert _ids(_facts((_user(), Ledger().monthly("Salary", 3000.0, "income", 28)))) == []


# ---- endpoint on seeded personas -----------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MOCK_DATA", False)
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "entitlements.db"))
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    seed()
    return TestClient(app)


def test_endpoint_shapes_and_personas(client):
    body = client.get("/users/maya/entitlements").json()
    assert body["user_id"] == "maya" and body["disclaimer"].startswith("General information, not financial or tax advice.")
    ids = [i["id"] for i in body["items"]]
    assert ids[0] == "universal_credit" and {"uc_childcare", "council_tax_reduction", "warm_home_discount"} <= set(ids)
    assert body["total_est_value"] == sum(i["est_value"] or 0 for i in body["items"]) > 0

    alex = client.get("/users/alex/entitlements").json()
    assert [i["id"] for i in alex["items"]] == ["council_tax_single_person"]

    sam = [i["id"] for i in client.get("/users/sam/entitlements").json()["items"]]
    assert "student_finance" in sam and "universal_credit" not in sam

    dan = client.get("/users/dan/entitlements").json()
    assert [i["id"] for i in dan["items"]] == ids  # one household, one answer


def test_endpoint_unknown_user_is_404(client):
    assert client.get("/users/nobody/entitlements").status_code == 404
