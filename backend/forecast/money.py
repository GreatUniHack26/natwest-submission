"""Round GBP at boundaries; project and add money in integer pence."""
from decimal import Decimal, ROUND_HALF_UP
import math


def pence(value: float) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)) or not math.isfinite(value):
        raise ValueError('Money must be a finite number')
    return int((Decimal(str(value)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def pounds(value: int) -> float:
    return value / 100
