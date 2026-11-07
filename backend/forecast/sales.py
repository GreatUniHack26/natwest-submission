"""Single sales calendar, owned by forecast; no agent dependency or import I/O."""
import datetime as dt
import json
from pathlib import Path

from backend import config

CALENDAR_PATH = Path(__file__).with_name('sales_calendar.json')


class CalendarUnavailable(RuntimeError):
    pass


def upcoming_sales(within_days: int = 60, *, as_of: dt.date | None = None) -> list[dict]:
    if isinstance(within_days, bool) or not isinstance(within_days, int) or not 0 <= within_days <= 365:
        raise ValueError('within_days must be an integer between 0 and 365')
    start = as_of or config.TODAY
    end = start + dt.timedelta(days=within_days)
    try:
        rows = json.loads(CALENDAR_PATH.read_text())
        if not isinstance(rows, list):
            raise ValueError('Calendar must be a list')
        valid = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('name'), str) or not row['name']:
                raise ValueError('Sale needs a name')
            day = dt.date.fromisoformat(row['date'])
            if not isinstance(row.get('categories'), list) or not all(isinstance(c, str) for c in row['categories']):
                raise ValueError('Sale needs category names')
            if start <= day <= end:
                valid.append(row)
        return sorted(valid, key=lambda row: (row['date'], row['name']))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CalendarUnavailable('Sales calendar is missing or malformed') from exc
