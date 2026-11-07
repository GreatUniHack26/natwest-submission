"""Kickoff proposals are coherent; approval is a human gate, never a test result."""
from contracts import mock
from contracts.schemas import Forecast, Pot, Transaction
from backend.data.categoriser import categorise


def test_rent_matches_single_month_rent_pot():
    rent = next(Transaction(**t) for t in mock.load('transactions') if t['category'] == 'housing')
    pot = next(Pot(**p) for p in mock.load('pots') if p['name'] == 'December rent')
    assert -rent.amount == pot.amount == 950


def test_fixture_risk_matches_low_band_not_expected_shortfall():
    result = Forecast(**mock.load('forecast'))
    event, = result.risk_events
    point = next(p for p in result.points if p.date == event.date)
    assert point.low < 0 <= point.expected
    assert event.severity == 'medium'


def test_uniqlo_category_matches_calendar():
    data = Transaction(id='shirt',user_id='sam',date='2026-11-07',merchant='Uniqlo',amount=-30,category='other',kind='want')
    assert categorise([data])[0].category == 'clothing'
