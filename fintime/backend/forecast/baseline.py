"""P2: everyday-spend baseline.

Average non-recurring spend per weekday (and per category) over the last 8-12 weeks,
plus a std-dev used for the low/high band and for alerts.
"""
from contracts.schemas import Transaction


def weekday_baseline(transactions: list[Transaction]) -> dict[int, tuple[float, float]]:
    """Return {weekday(0=Mon): (mean_spend, std_dev)} excluding recurring bills and income."""
    raise NotImplementedError("P2: see module docstring")


def category_weekly_mean(transactions: list[Transaction]) -> dict[str, tuple[float, float]]:
    """Return {category: (mean_weekly_spend, std_dev)} - feeds alerts.py."""
    raise NotImplementedError("P2: see module docstring")
