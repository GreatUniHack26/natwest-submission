"""P1 - DATA module. Public interface (do not rename without a contracts PR):

    get_user, get_transactions, get_pots, add_pot, categorise, generate_persona
"""
from .categoriser import categorise
from .generator import generate_persona
from .repository import add_pot, get_pots, get_transactions, get_user

__all__ = ["get_user", "get_transactions", "get_pots", "add_pot", "categorise", "generate_persona"]
