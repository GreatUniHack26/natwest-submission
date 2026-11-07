# Kickoff decisions (issue #1)

Proposed by P5. Each item needs all 5 approvals in the issue comments; contract changes go in one PR.

| # | Decision | Proposal | Why | Status |
|---|---|---|---|---|
| 1 | Rent vs pot mismatch (£475 rent, £950 "December rent" pot) | Rename the pot to **"Dec + Jan rent"**, keep £950 (2 x £475). | Matches the story: Sam sets aside two months of rent to bridge the gap until January income, which is exactly the 26 Dec risk the forecast shows. No numbers change elsewhere. | Proposed |
| 2 | Where `sales_calendar.json` lives | Move to `backend/forecast/`, add `forecast.upcoming_sales(within_days)`; the agent tool calls that. | `simulate_purchase` needs it for `better_date`. Leaving it in `agent/` makes forecast import from agent and breaks the layer rule. | Proposed |
| 3 | Category name for clothes | Use **`clothing`** everywhere. Change the categoriser rule for Uniqlo from `clothes` to `clothing`. | The sales calendar uses `clothing`. With `clothes`, Black Friday never matches the shirt and the hero demo moment breaks. | Proposed |
| 4 | Personas | **Sam** (student, irregular shift income, Manchester) is the only demo persona. `family` is stretch. | All fixtures and the pitch are built on Sam. One persona, one clean story. | Proposed |
| 5 | One-line story | "FinTime keeps a twin of your money and lets you time-travel through it." | Gives the forecast a name judges remember. No code change. | Proposed |
| 6 | Git workflow | Short branches, PR into `main`, nobody merges red tests, merge about every 45 min. `develop` is unused; delete it or keep it identical to `main`. | One integration branch avoids drift. | Proposed |
| 7 | Contracts | Changes need all 5 approvals, one PR updating `schemas.py`, the fixture and `web/src/types.ts` together. | Already in the README; confirming. | Proposed |
| 8 | Model + keys | LLM model pinned in `.env` (`LLM_MODEL`). One person holds the LLM key, one holds the ElevenLabs key; shared privately, never committed. | Stable demo, no leaked secrets. | Holders: ______ |

## Field conventions to confirm
- `Transaction.amount`: negative = spend, positive = income (GBP).
- `Pot.due_date`: nullable; `null` = open-ended (emergency fund).
- `Forecast.assumptions`: plain-language strings shown to the user.

## Setup check (everyone comments "green" on issue #1)
`make install`, `make api`, `make web`, `make test` (17 tests pass on the current scaffold).
