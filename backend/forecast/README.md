# Forecast assumptions and verification

All calculations are deterministic. Cash flows and totals use integer pence;
GBP boundaries round half-up. Same repository inputs, as-of date and overrides
produce the same output. No agent, network, LLM or database imports are allowed.

The repository must supply `get_balance(user_id, as_of)`: the authoritative GBP
balance at close of that date. Future flows start the next day; a simulated
purchase today adjusts the opening point once. A missing balance interface is
an explicit error, never an invitation to sum unanchored transaction history.

Recurrence uses up to 180 days, grouped by user, merchant and sign, requiring
three observations. Bills must fit the median within 10%. Weekly and monthly
schedules permit three-day timing variation. Calendar anchors remain fixed
through short months. Irregular income uses the mean observed receipt and mean
rounded cadence when gaps are between 1 and 45 days and the largest gap is at
most three times the smallest. Positive non-income receipts are not wages.

Everyday statistics use 84 days ending before the evaluation date, with zeros
for days/weeks without spending. Only matched recurring observation IDs are
excluded; unrelated purchases at the same merchant remain. Refunds do not
predict future income. Population standard deviation describes observed
variation, not a statistical confidence guarantee. Under one week of history,
unobserved weekdays use the overall daily mean. Missing history is disclosed.

Daily independent spend/payment variances add. Variable-income uncertainty
combines observed amount variance with a timing proxy: receipt times the
coefficient of variation of observed gaps. Calendar month-length variation is
known and does not add timing uncertainty. Assumptions cannot promise income.

Risks are first expected-negative (high), first low-negative (medium), and first
use of protected pot money (medium), inspected daily, including between chart
points. Pot conventions live in `reservations.py`. Safe-to-spend reserves bills
through the next fixed income (bills first on the same date); absent/uncertain
income causes a disclosed 90-day reservation. Negative results remain visible.

Purchases use today's safe budget and rerun the same engine. New or earlier
expected/low/pot crossings are worsening, independently of explanation strings.
An unchanged pre-existing risk alone does not reject every purchase. Zero cost
is allowed. Dates must be today through 365 days ahead; sale suggestions cover
42 days and only events marked general because the facade has no item category.
Missing sale data is disclosed and never implies a discount.

Tests use hand-calculated ledgers and repository fakes; they are not evidence
of SQLite or generated-persona integration. The six-month controlled Sam case
asserts £210 safe, £30 affordable with £180 remaining and a 27 November sale,
plus an expected balance of £185 on 25 December and -£36 on 26 December.
Property checks apply only to quantities the model guarantees: fixed-input
extra costs lower balances exactly after their date, bands remain ordered,
breakdowns reconcile, inputs remain unchanged and output is deterministic.

Run `make test`. Optional coverage inspection:
`pytest --cov=backend.forecast --cov-branch --cov-report=term-missing`.
Coverage is a branch-inspection aid, not proof of model validity. Tests need no
network, LLM/voice credentials or production data. Real-data integration depends
on P1's repository/balance interfaces and agreed generated data.
