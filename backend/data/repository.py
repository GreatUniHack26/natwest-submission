"""P1: storage layer. Mock mode returns fixtures; real mode reads SQLite (config.DB_PATH).

Only this file may touch the database. Other modules go through the functions below.
config.DB_PATH is read on every call (not cached) so tests/tools can point it elsewhere.
"""
import datetime as dt
import sqlite3
from contextlib import contextmanager
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterator, Optional

from backend import config
from contracts import mock
from contracts.schemas import Pot, Transaction, User
from .generator import OPENING_BALANCE_MERCHANT

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    persona      TEXT NOT NULL,
    region       TEXT NOT NULL,
    household_id TEXT,
    tone         TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transactions (
    id       TEXT PRIMARY KEY,
    user_id  TEXT NOT NULL REFERENCES users(id),
    date     TEXT NOT NULL,           -- ISO yyyy-mm-dd (sorts lexicographically)
    merchant TEXT NOT NULL,
    amount   REAL NOT NULL,
    category TEXT NOT NULL,
    kind     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transactions_user_date ON transactions(user_id, date);
CREATE TABLE IF NOT EXISTS pots (
    id       TEXT PRIMARY KEY,
    user_id  TEXT NOT NULL REFERENCES users(id),
    name     TEXT NOT NULL,
    amount   REAL NOT NULL,
    due_date TEXT
);
CREATE INDEX IF NOT EXISTS idx_pots_user ON pots(user_id);
"""


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """Connection per call; commits on success, rolls back on error, always closes."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)  # idempotent: schema is created lazily
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _iso(d: Optional[dt.date]) -> Optional[str]:
    return d.isoformat() if d else None


def get_user(user_id: str) -> User:
    if config.MOCK_DATA:
        return User(**mock.load("user"))
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise KeyError(f"Unknown user {user_id!r} (run `make seed`?)")
    return User(**dict(row))


def get_household_members(household_id: str) -> list[User]:
    """All users sharing `household_id`, ordered by id. Unknown household -> []."""
    if config.MOCK_DATA:
        return []  # fixtures have no households
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM users WHERE household_id = ? ORDER BY id", (household_id,)
        ).fetchall()
    return [User(**dict(r)) for r in rows]


def get_transactions(
    user_id: str, start: Optional[dt.date] = None, end: Optional[dt.date] = None
) -> list[Transaction]:
    if config.MOCK_DATA:
        txs = [Transaction(**t) for t in mock.load("transactions")]
        return [t for t in txs if (not start or t.date >= start) and (not end or t.date <= end)]
    sql, args = "SELECT * FROM transactions WHERE user_id = ?", [user_id]
    if start:
        sql, args = sql + " AND date >= ?", args + [_iso(start)]
    if end:
        sql, args = sql + " AND date <= ?", args + [_iso(end)]
    with _connect() as conn:
        rows = conn.execute(sql + " ORDER BY date, id", args).fetchall()
    return [Transaction(**dict(r)) for r in rows]


def get_pots(user_id: str) -> list[Pot]:
    if config.MOCK_DATA:
        return [Pot(**p) for p in mock.load("pots")]
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM pots WHERE user_id = ? ORDER BY id", (user_id,)).fetchall()
    return [Pot(**dict(r)) for r in rows]


def add_pot(pot: Pot) -> Pot:
    if config.MOCK_DATA:
        return pot  # not persisted in mock mode
    with _connect() as conn:
        if conn.execute("SELECT 1 FROM users WHERE id = ?", (pot.user_id,)).fetchone() is None:
            raise ValueError(f"Cannot add pot: unknown user {pot.user_id!r}")
        if conn.execute("SELECT 1 FROM pots WHERE id = ?", (pot.id,)).fetchone() is not None:
            raise ValueError(f"Cannot add pot: id {pot.id!r} already exists")
        conn.execute(
            "INSERT INTO pots (id, user_id, name, amount, due_date) VALUES (?, ?, ?, ?, ?)",
            (pot.id, pot.user_id, pot.name, pot.amount, _iso(pot.due_date)),
        )
    return pot


def save_persona(user: User, transactions: list[Transaction], pots: list[Pot]) -> None:
    """Seed support: atomically replace everything stored for `user` (idempotent).

    Always acts on the real DB, regardless of MOCK_DATA.
    """
    with _connect() as conn:
        for table in ("transactions", "pots"):
            conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (user.id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user.id,))
        conn.execute(
            "INSERT INTO users (id, name, persona, region, household_id, tone) VALUES (?, ?, ?, ?, ?, ?)",
            (user.id, user.name, user.persona, user.region, user.household_id, user.tone),
        )
        conn.executemany(
            "INSERT INTO transactions (id, user_id, date, merchant, amount, category, kind) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(t.id, t.user_id, _iso(t.date), t.merchant, t.amount, t.category, t.kind) for t in transactions],
        )
        conn.executemany(
            "INSERT INTO pots (id, user_id, name, amount, due_date) VALUES (?, ?, ?, ?, ?)",
            [(p.id, p.user_id, p.name, p.amount, _iso(p.due_date)) for p in pots],
        )


def get_balance(user_id: str, as_of: dt.date) -> float:
    """Close-of-date balance anchored by one explicit opening-balance entry.

    The synthetic generator's opening row is a start-of-day balance, not pay.
    Unanchored/sparse mock fixtures are insufficient and fail explicitly.
    """
    if get_user(user_id).id != user_id:
        raise KeyError(f'Unknown user {user_id!r}')
    transactions = get_transactions(user_id, end=as_of)
    anchors = [t for t in transactions if t.merchant == OPENING_BALANCE_MERCHANT and t.kind == 'income']
    if len(anchors) != 1:
        raise ValueError('Exactly one authoritative opening-balance entry is required')
    opening = anchors[0]
    values = [Decimal(str(t.amount)) for t in transactions if t.date >= opening.date]
    if not all(value.is_finite() for value in values):
        raise ValueError('Balance transactions must contain finite amounts')
    return float(sum(values, Decimal(0)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


def get_household_members(household_id: str) -> list[User]:
    """Resolve stored membership; each account balance/pot has one user owner."""
    if config.MOCK_DATA:
        user = User(**mock.load('user'))
        return [user] if user.household_id == household_id else []
    with _connect() as conn:
        rows = conn.execute('SELECT * FROM users WHERE household_id = ? ORDER BY id', (household_id,)).fetchall()
    return [User(**dict(row)) for row in rows]
