# Household integration proposal (#35; approval required)

`household_forecast(household_id, horizon=90)` returns the existing Forecast
shape, identifying the household in `user_id`. Daily dates align before sums;
weekly/end points follow the individual convention. Low/expected/high each sum
member values, treating their uncertainty as perfectly correlated. Daily risks
are recalculated against aggregate balances and protected funds.

`household_safe_to_spend(household_id)` conservatively sums individual safe
amounts and labels every member's breakdown. This is an oversight view of
separately owned funds, not a promise that one member can spend another's money.

P1 must provide `get_household_members(household_id) -> list[User]` and authoritative
close-of-date `get_balance(user_id, as_of)`. Returned user records are checked
again against membership. Empty/unknown households and missing members are
explicit lookup errors. There is no hardcoded family membership.

Each account balance and shared pot must have exactly one owner in repository
results. Duplicate global pot IDs are rejected instead of double-counting them.
A shared balance must not be returned as independently owned money for two users;
this ownership requirement must be enforced in the data layer because the current
contracts do not contain account IDs. `internal_transfer` rows are excluded from
income/spending inference for ordinary and household projections; voluntary future
transfers are not forecast as consumption or wages. Other categories are unchanged.
These representation conventions need P1's approval before real integration.

Proposed shared routes:

- `GET /households/{household_id}/forecast?days=90` (7–365 inclusive).
- `GET /households/{household_id}/safe-to-spend`.

Responses preserve existing contracts. Unknown/empty/member-missing households
return 404, invalid horizons/ownership return 422, and missing repository access
or mock-only household mode returns 503. Household fixture fallbacks do not exist
and must not leak Sam's unrelated data. TestClient tests verify exact numbers
and errors through the real calculation code with repository fakes.

The shared API changes require all-five approval before merge. Family-persona
and actual SQLite verification remain blocked by upstream #4/#5; controlled
boundary tests are not proof of those integrations.
