"""P1: storage layer. Mock mode returns fixtures; real mode reads SQLite (config.DB_PATH).

Only this file may touch the database. Other modules go through the functions below.
"""
import datetime as dt
from typing import Optional

from backend import config
from contracts import mock
from contracts.schemas import Pot, Transaction, User


def get_user(user_id: str) -> User:
    if config.MOCK_DATA:
        return User(**mock.load("user"))
    raise NotImplementedError("P1: SELECT user from SQLite")


def get_transactions(
    user_id: str, start: Optional[dt.date] = None, end: Optional[dt.date] = None
) -> list[Transaction]:
    if config.MOCK_DATA:
        txs = [Transaction(**t) for t in mock.load("transactions")]
        return [t for t in txs if (not start or t.date >= start) and (not end or t.date <= end)]
    raise NotImplementedError("P1: SELECT transactions WHERE user_id AND date range")


def get_pots(user_id: str) -> list[Pot]:
    if config.MOCK_DATA:
        return [Pot(**p) for p in mock.load("pots")]
    raise NotImplementedError("P1: SELECT pots for user")


def add_pot(pot: Pot) -> Pot:
    if config.MOCK_DATA:
        return pot  # not persisted in mock mode
    raise NotImplementedError("P1: INSERT pot")
