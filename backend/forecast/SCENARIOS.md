# What-if forecasts (#37)

POST `/users/{id}/forecast/what-if` accepts:

```json
{
  "days": 90,
  "overrides": {
    "income_multiplier": 0.5,
    "extra_monthly_cost": 300,
    "extra_one_off": {"amount": 30, "date": "2026-11-27"}
  }
}
```

It returns the existing `Forecast` contract, including scenario risks and
assumptions. Fetch the ordinary forecast for the baseline comparison. No
existing response field or frontend TypeScript type changes. Request and response shapes are validated by the API and integration suite.

Recognized values are finite non-boolean numbers. Income multipliers range
0–10 (default 1), applying to future scheduled income and its uncertainty only.
Additional monthly costs range £0–£1 billion (default zero), first paid on the
next monthly anniversary of the as-of date. Keep the original day of month and
clamp to short months without drifting afterwards. Existing history and pots
remain unchanged; overrides do not claim to rewrite recorded transactions.

`extra_one_off` is either a nonnegative GBP amount applied today, an object with
exactly `amount` and `date`, or a list of those objects. Each cost ranges £0–£1
billion. Dates must fall within the requested 7–365 day horizon, including today
and the end date. Multiple entries on one day add, then apply exactly once.
Unknown top-level override keys are ignored. Malformed recognized values produce
ValueError in Python and 422 through the API. Default/zero overrides preserve
baseline output exactly, including assumptions; effective changes are explained.

Mock-only what-if calls return 503 instead of an unrelated fixture. Missing
authoritative repository balance access also returns 503; unknown users return
404. Ordinary forecast, alerts, safe-spend and purchase routes retain their
existing success schemas and now map financial validation errors clearly.

Tests use the real engine with repository fakes and independent expected sums.
The job-loss example changes first expected shortfall from 3 January to
29 November. Combined half-income/£15 monthly/£7 one-off ends at -£22 versus
baseline £50 after 35 days. No LLM or external service participates.
