"""P1 - DATA module. Public interface (do not rename without a contracts PR):

    get_user, get_balance, get_household_members, get_transactions, get_pots, add_pot, categorise,
    generate_persona, generate_household
"""
from .categoriser import categorise
from .generator import generate_household, generate_persona
from .repository import add_pot, get_balance, get_household_members, get_pots, get_transactions, get_user

__all__ = [
    "get_user", "get_balance", "get_household_members", "get_transactions", "get_pots", "add_pot",
    "categorise", "generate_persona", "generate_household",
]
