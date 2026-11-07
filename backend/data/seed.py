"""Seed the SQLite DB with generated personas. Run: `make seed` (idempotent).

Labels are computed once here via categorise() (rules + cache; no live LLM call when every
merchant is known). Persists via repository.save_persona (the only code allowed to touch the DB).
"""
from backend import config
from backend.data.categoriser import categorise
from backend.data.generator import generate_household, generate_persona
from backend.data.repository import save_persona

PERSONAS = ["sam", "salaried"]  # single-user personas
HOUSEHOLDS = ["family"]  # multi-user personas


def seed(
    personas: list[str] = PERSONAS, households: list[str] = HOUSEHOLDS, seed_value: int = 42
) -> dict[str, int]:
    """Generate and store everyone, replacing existing rows. Returns {user_id: tx count}."""
    members = [generate_persona(name, seed_value) for name in personas]
    for name in households:
        members += generate_household(name, seed_value)
    counts = {}
    for user, txs, pots in members:
        save_persona(user, categorise(txs), pots)  # labels pre-computed at seed time
        counts[user.id] = len(txs)
    return counts


if __name__ == "__main__":
    for uid, n in seed().items():
        print(f"seeded {uid}: {n} transactions -> {config.DB_PATH}")
