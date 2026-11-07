import datetime as dt

import pytest

from backend import config
from backend.data import repository
from contracts.schemas import User


@pytest.fixture
def ledger(monkeypatch):
    """Repository boundary fake; not a claim of SQLite/persona integration."""
    state = {'balance': 1640, 'transactions': [], 'pots': []}
    monkeypatch.setattr(config, 'MOCK_FORECAST', False)
    monkeypatch.setattr(config, 'TODAY', dt.date(2026, 11, 7))
    monkeypatch.setattr(repository, 'get_user', lambda uid: User(id=uid, name=uid, persona='test', region='Manchester'))
    monkeypatch.setattr(repository, 'get_balance', lambda uid, as_of: state['balance'], raising=False)
    monkeypatch.setattr(repository, 'get_transactions', lambda uid, start=None, end=None: state['transactions'])
    monkeypatch.setattr(repository, 'get_pots', lambda uid: state['pots'])
    return state
