"""One ranked, de-duplicated alert feed in plain words.

Every surface (Home banner, Nat's notification, the alerts list, Nat's live
context) reads this feed, so the same problem is never shown twice. Each alarm
is built from deterministic engine output only:

- act:   money trouble the forecast sees coming (shortfall date, pot money at risk)
- watch: spending running ahead of the usual pace (one per category; overspend and
         sudden-change signals for the same category are merged)
- good:  reassurance and opportunities (a bill already covered by its pot,
         schemes they may be owed, idle pot money that could earn interest)

Copy rules: a short title a 17- or 80-year-old understands, one line of reason
with the real numbers, one concrete action, and a question to ask Nat.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Callable

from backend import config, data
from backend import forecast as fc

MAX_ALARMS = 6
RANK = {"act": 0, "watch": 1, "good": 2}


def _day(value: dt.date | str) -> str:
    d = dt.date.fromisoformat(value) if isinstance(value, str) else value
    return f"{d.day} {d:%b}"


def _money(value: float) -> str:
    value = round(value)
    return f"-£{abs(value):,}" if value < 0 else f"£{value:,}"


def _safe(fn: Callable[[], Any], default: Any = None) -> Any:
    try:
        return fn()
    except Exception:
        return default


def _alarm(id_: str, level: str, title: str, body: str, action: str, ask: str,
           link: str = "#forecast", when: str | None = None) -> dict:
    return {"id": id_, "level": level, "title": title, "body": body, "action": action,
            "ask_nat": ask, "link": link, "when": when}


def _chance_on(sim: dict | None, day: str) -> float | None:
    if not sim:
        return None
    points = [p for p in sim.get("points", []) if p["date"] >= day]
    return points[0]["chance_below_zero"] if points else None


def _next_income(user_id: str, after: str) -> dict | None:
    timeline = _safe(lambda: fc.timeline(user_id, 60))
    if not timeline:
        return None
    return next((e for e in timeline["events"] if e["kind"] == "income" and e["date"] > after), None)


def build_alarms(user_id: str) -> list[dict]:
    today = config.TODAY
    raw = _safe(lambda: fc.detect_alerts(user_id), []) or []
    month = _safe(lambda: fc.spending_forecast(user_id))
    sim = _safe(lambda: fc.simulate_futures(user_id, 90))
    alarms: list[dict] = []

    # Act: the forecast's first shortfall date (one alarm, not one per band).
    risk = next((a for a in raw if a.type == "risk" and a.severity == "high"), None)
    if risk:
        date = risk.message.split(":")[0].strip()
        chance = _chance_on(sim, date)
        odds = f"In {round(chance * 100)} of 100 futures you're below £0 by then." if chance is not None else \
            "Your expected balance drops below £0 on that day."
        action = "Check which bills are due before then and keep extras small."
        alarms.append(_alarm(f"short:{date}", "act", f"You may run short around {_day(date)}", odds, action,
                             f"How do I avoid running short around {_day(date)}?", "#forecast", date))

    # Act: pot money at risk (from the daily forecast, with the Monte Carlo share when available).
    timeline = _safe(lambda: fc.timeline(user_id, 60))
    pot_dip = next((r for r in (timeline or {}).get("risks", []) if "protected by pots" in r["reason"].lower()), None)
    if pot_dip:
        pots = _safe(lambda: data.get_pots(user_id), []) or []
        named = next((p.name for p in pots if p.due_date), None) or "pot"
        share = sim.get("chance_dip_into_pots") if sim else None
        body = (f"At this pace you'd be spending money meant for your {named.lower()} pot."
                + (f" That happens in {round(share * 100)} of 100 futures." if share else ""))
        alarms.append(_alarm(f"pots:{pot_dip['date']}", "act", f"Your {named} money could get used around {_day(pot_dip['date'])}",
                             body, "Spend only your safe-to-spend amount until then.",
                             f"How do I keep my {named.lower()} pot safe?", "#pots", pot_dip["date"]))

    # Watch: one alarm per category running hot (overspend + sudden change merged).
    hot = {a.category for a in raw if a.type in ("overspend", "sudden_change") and a.category}
    rows = {r["category"]: r for r in (month or {}).get("categories", [])}
    days_left = (month["days_in_month"] - month["days_elapsed"]) if month else 0
    for category in sorted(hot, key=lambda c: -(rows.get(c, {}).get("projected_month", 0))):
        row = rows.get(category)
        name = category.capitalize()
        if row:
            body = (f"{_money(row['spent_so_far'])} so far this month. Usually about "
                    f"{_money(row['expected_so_far'])} by now.")
            room = row["typical_month"] - row["spent_so_far"]
            weeks = max(1, round(days_left / 7))
            action = (f"Keep {category} to about {_money(room / weeks)} a week for the rest of the month."
                      if room > 0 else f"You've used your usual {category} budget. Try to pause it until next month.")
        else:
            body, action = f"{name} spending jumped this week.", f"Pick a {category} limit for next week."
        alarms.append(_alarm(f"spend:{category}", "watch", f"{name} spending is running high", body, action,
                             f"How can I cut back on {category} this month?", "#forecast"))

    # Good: a dated pot already covering a bill soon.
    for pot in sorted(_safe(lambda: data.get_pots(user_id), []) or [], key=lambda p: p.due_date or dt.date.max):
        if pot.due_date and 0 <= (pot.due_date - today).days <= 31:
            alarms.append(_alarm(f"covered:{pot.id}", "good", f"{pot.name} is covered",
                                 f"{_money(pot.amount)} is set aside for {_day(pot.due_date)}. It won't count as spending money.",
                                 "Nothing to do. Leave the pot alone.", f"Is my {pot.name.lower()} safe?", "#pots",
                                 pot.due_date.isoformat()))
            break

    # Good: schemes they may be owed.
    owed = _safe(lambda: __import__("backend.rules.entitlements", fromlist=["x"]).entitlements_summary(user_id))
    if owed and owed.get("items"):
        likely = [i for i in owed["items"] if i["confidence"] == "likely"]
        top = (likely or owed["items"])[0]
        total = owed.get("total_est_value") or 0
        title = f"You may be owed up to {_money(total)} a year" if total else f"{len(owed['items'])} kinds of help to check"
        alarms.append(_alarm("owed", "good", title, f"Start with {top['title']}. {top['why_you']}",
                             "Use the official GOV.UK checker to be sure.", "What help could I be missing?", "#tips"))

    # Good: idle pot money that could earn interest.
    dep = _safe(lambda: fc.deposit_ideas(user_id))
    if dep and dep.get("total_est_interest", 0) >= 5:
        best = dep["ideas"][0]
        alarms.append(_alarm("idle", "good", f"Your pots could earn about {_money(dep['total_est_interest'])}",
                             f"{best['pot']} sits unused until it's due. An instant-access saver keeps it available.",
                             "See which pots could earn interest.", "Can my pot money earn anything?", "#pots"))

    seen, unique = set(), []
    for item in sorted(alarms, key=lambda a: RANK[a["level"]]):
        if item["id"] not in seen:
            seen.add(item["id"])
            unique.append(item)
    return unique[:MAX_ALARMS]
