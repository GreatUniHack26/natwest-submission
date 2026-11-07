"""P1: synthetic persona generator. Highest priority: everything depends on this data.

Requirements for the seeded generator (6 months of history up to config.TODAY):
  - recurring bills: rent (1st), phone, subscriptions
  - weekday pattern: e.g. £10-15 food on uni days (Tuesday)
  - irregular income for the student persona; fixed salary for a second persona
  - PLANTED for the demo: a spending spike in 'eating out' last week, and a
    December rent deadline so the forecast dips near 26 Dec
Personas: 'sam' (student), 'family' (household_id='h1', 2 adults + 2 kids), optional 'salaried'.
"""
from contracts.schemas import Pot, Transaction, User


def generate_persona(name: str, seed: int = 42) -> tuple[User, list[Transaction], list[Pot]]:
    raise NotImplementedError("P1: generate and write to SQLite (see module docstring)")
