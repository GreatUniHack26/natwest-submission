"""Seed the SQLite DB with generated personas. Run: `make seed` (idempotent).

Persists via repository.save_persona (the only code allowed to touch the DB).
"""
from backend import config
from backend.data.generator import generate_persona
from backend.data.repository import save_persona

PERSONAS = ["sam"]  # add 'family' / 'salaried' as they land (issue #4)


def seed(personas: list[str] = PERSONAS, seed_value: int = 42) -> dict[str, int]:
    """Generate and store each persona, replacing any existing rows. Returns tx counts."""
    counts = {}
    for name in personas:
        user, txs, pots = generate_persona(name, seed_value)
        save_persona(user, txs, pots)
        counts[user.id] = len(txs)
    return counts


if __name__ == "__main__":
    for uid, n in seed().items():
        print(f"seeded {uid}: {n} transactions -> {config.DB_PATH}")
