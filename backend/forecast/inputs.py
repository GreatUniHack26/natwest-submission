"""Forecast's repository boundary; never invent a balance from transactions.

P1 must supply get_balance(user_id, as_of): GBP available at the close of as_of,
including that day's actual transactions. No forecast fixture is a balance source.
"""
import datetime as dt
from dataclasses import dataclass

from backend.data import repository
from contracts.schemas import Pot, Transaction
from .money import pence


class ForecastDataUnavailable(RuntimeError):
    pass


@dataclass
class Inputs:
    user_id: str
    as_of: dt.date
    balance: int
    transactions: list[Transaction]
    pots: list[Pot]


def load_inputs(user_id: str, as_of: dt.date) -> Inputs:
    user = repository.get_user(user_id)
    if user.id != user_id:
        raise LookupError(f'Unknown user: {user_id}')
    get_balance = getattr(repository, 'get_balance', None)
    if get_balance is None:
        raise ForecastDataUnavailable('Data repository must provide get_balance(user_id, as_of); no authoritative balance source is available')
    balance = pence(get_balance(user_id, as_of))
    start = as_of - dt.timedelta(days=180)
    transactions = repository.get_transactions(user_id, start=start, end=as_of)
    pots = repository.get_pots(user_id)
    if any(t.user_id != user_id for t in transactions) or any(p.user_id != user_id for p in pots):
        raise ValueError('Repository returned financial data for another user')
    if any(pence(p.amount) < 0 for p in pots):
        raise ValueError('Pot amounts must be nonnegative')
    return Inputs(user_id, as_of, balance, [t for t in transactions if start <= t.date <= as_of], pots)
