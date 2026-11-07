"""Tests for issue #39: savings and tax tips engine (backend.rules)."""
import datetime as dt
import pytest

from backend import config, data, rules
from backend.rules import bike_to_work, railcard_16_25, student_council_tax
from contracts.schemas import Tip, Transaction, User

REQUIRED_DISCLAIMER = "General information, not financial or tax advice."
OFFICIAL_SOURCES = ("https://www.gov.uk/", "https://www.16-25railcard.co.uk")


def _tx(
    tx_id: str,
    merchant: str,
    amount: float,
    category: str,
    kind: str = "need",
    user_id: str = "u1",
) -> Transaction:
    return Transaction(
        id=tx_id,
        user_id=user_id,
        date=dt.date(2026, 11, 5),
        merchant=merchant,
        amount=amount,
        category=category,
        kind=kind,  # type: ignore[arg-type]
    )


def test_all_tips_sam_mock_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """With MOCK_DATA=True, Sam (student with transport, housing, and shift pay) gets all 3 tips."""
    monkeypatch.setattr(config, "MOCK_DATA", True)

    tips = rules.all_tips("sam")
    assert len(tips) == 3

    ids = [t.id for t in tips]
    assert ids == ["bike_to_work", "railcard_16_25", "student_council_tax"]

    for tip in tips:
        assert isinstance(tip, Tip)
        assert tip.disclaimer == REQUIRED_DISCLAIMER
        assert any(src in tip.body for src in OFFICIAL_SOURCES), f"Missing official source in {tip.id}"
        assert "may be worth checking" in tip.body.lower()

    by_id = {t.id: t for t in tips}
    # Sam's mock transport spend is £9.20
    assert by_id["bike_to_work"].est_saving == round(9.20 * 0.32, 2)
    assert by_id["railcard_16_25"].est_saving == round(9.20 / 3.0, 2)
    assert by_id["student_council_tax"].est_saving is None


def test_no_tips_when_user_data_does_not_support_any(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-student user with zero transport spend and zero housing spend gets []."""
    user = User(
        id="u_none",
        name="Pat",
        persona="Retired homeowner",
        region="York",
        tone="friendly",
    )
    txs = [
        _tx("t1", "Opening balance", 1500.00, "income", "income", user_id="u_none"),
        _tx("t2", "Tesco", -45.00, "groceries", "need", user_id="u_none"),
    ]
    monkeypatch.setattr(data, "get_user", lambda uid: user)
    monkeypatch.setattr(data, "get_transactions", lambda uid: txs)

    assert rules.all_tips("u_none") == []


def test_salaried_non_student_gets_only_bike_to_work(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-student employee with commuting spend gets bike_to_work but not student tips."""
    user = User(
        id="alex",
        name="Alex",
        persona="Salaried office worker, fixed monthly income",
        region="Bristol",
        tone="direct",
    )
    txs = [
        _tx("t1", "Meridian Ltd (salary)", 2350.00, "income", "income", user_id="alex"),
        _tx("t2", "First Bus", -50.00, "transport", "need", user_id="alex"),
        _tx("t3", "Bristol Lettings (rent)", -950.00, "housing", "need", user_id="alex"),
    ]
    monkeypatch.setattr(data, "get_user", lambda uid: user)
    monkeypatch.setattr(data, "get_transactions", lambda uid: txs)

    tips = rules.all_tips("alex")
    assert [t.id for t in tips] == ["bike_to_work"]
    assert tips[0].est_saving == 16.00
    assert "gov.uk" in tips[0].body
    assert tips[0].disclaimer == REQUIRED_DISCLAIMER


def test_bike_to_work_triggers_on_bike_shop_merchant_and_requires_employment_income(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """bike_to_work triggers on a Halfords purchase with pay, but not without employment income."""
    user = User(id="u1", name="Jordan", persona="Retail worker", region="Leeds")
    bike_tx = _tx("t1", "Halfords", -250.00, "shopping", "want")
    opening_tx = _tx("t0", "Opening balance", 1000.00, "income", "income")

    monkeypatch.setattr(data, "get_user", lambda uid: user)

    # Only opening balance -> no employment income -> None
    monkeypatch.setattr(data, "get_transactions", lambda uid: [opening_tx, bike_tx])
    assert bike_to_work.check("u1") is None

    # With shift/salary pay -> triggers with 32% of £250 = £80.00
    pay_tx = _tx("t2", "Retail shift pay", 400.00, "income", "income")
    monkeypatch.setattr(data, "get_transactions", lambda uid: [opening_tx, bike_tx, pay_tx])
    tip = bike_to_work.check("u1")
    assert tip is not None
    assert tip.id == "bike_to_work"
    assert tip.est_saving == 80.00


def test_student_rules_require_matching_spend_categories(monkeypatch: pytest.MonkeyPatch) -> None:
    """Student rules only fire when the respective transport or housing spend is present."""
    student = User(id="s1", name="Sam", persona="Full-time student", region="Manchester")
    monkeypatch.setattr(data, "get_user", lambda uid: student)

    # Only housing spend -> student_council_tax fires, railcard_16_25 does not
    monkeypatch.setattr(
        data,
        "get_transactions",
        lambda uid: [_tx("t1", "Uni Hall Rent", -600.00, "housing", "need", user_id="s1")],
    )
    assert railcard_16_25.check("s1") is None
    ct_tip = student_council_tax.check("s1")
    assert ct_tip is not None
    assert ct_tip.id == "student_council_tax"
    assert "https://www.gov.uk/council-tax/who-has-to-pay" in ct_tip.body

    # Only transport spend -> railcard_16_25 fires, student_council_tax does not
    monkeypatch.setattr(
        data,
        "get_transactions",
        lambda uid: [_tx("t2", "Northern Rail", -30.00, "transport", "need", user_id="s1")],
    )
    assert student_council_tax.check("s1") is None
    rc_tip = railcard_16_25.check("s1")
    assert rc_tip is not None
    assert rc_tip.id == "railcard_16_25"
    assert rc_tip.est_saving == 10.00
    assert "https://www.16-25railcard.co.uk" in rc_tip.body


def test_missing_data_and_exceptions_return_none_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing user or transaction lookup errors return None / [] without raising."""
    def _raise_key_error(uid: str):
        raise KeyError(f"Unknown user {uid!r}")

    monkeypatch.setattr(data, "get_user", _raise_key_error)

    assert bike_to_work.check("missing") is None
    assert railcard_16_25.check("missing") is None
    assert student_council_tax.check("missing") is None
    assert rules.all_tips("missing") == []

    # Invalid empty user_id also returns None / [] safely
    assert bike_to_work.check("") is None
    assert railcard_16_25.check("") is None
    assert student_council_tax.check("") is None
    assert rules.all_tips("") == []
