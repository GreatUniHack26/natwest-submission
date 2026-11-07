# Kickoff proposals — issue #1 remains open

This PR makes the following choices reviewable. They are **not approved** until
all five team members record approval on issue #1. P5's proposals in PR #44
were considered; that PR remains independently owned by P5.

| Topic | Proposal in this PR |
|---|---|
| Contracts | Preserve all Pydantic and TypeScript field shapes. GBP amounts: negative spending, positive receipts. `Pot.due_date = null` means open-ended. Forecast assumptions are explanatory strings. |
| Rent | £950 monthly rent and £950 December-rent pot. Correct the transaction fixture from £475 to £950. This follows #1/#3's single-month matching requirement; it differs from PR #44's proposed two-month pot rename and needs P1/P5 agreement. |
| Risk severity | Expected balance below zero is high; only the low band below zero is medium. Correct the fixture and matching alert to medium without changing its chart numbers. Real engine tests independently exercise a high expected shortfall near 26 December. |
| Calendar | One file at `backend/forecast/sales_calendar.json`; `forecast.upcoming_sales(within_days=60)` supplies the agent and purchase simulator. No import-time file I/O or forecast-to-agent dependency. Malformed/missing calendars raise `CalendarUnavailable`, so callers can explain missing timing information. |
| Category | Uniqlo uses `clothing`, matching the calendar. |
| Personas | Sam remains the student demo persona. Family remains required for #4/#35; no replacement by Sara. |
| Story | “FinTime keeps a twin of your money and lets you time-travel through it.” |
| Git | Feature branches from latest `develop`; verified PRs target `develop`. `main` is release-only. This supersedes the scaffold and PR #44's older main-only integration proposal. Never bypass reviews or checks. |
| Approvals | Shared contracts/API changes require all five approvals. Owner-module changes need their owner's review. Automated tests cannot supply these approvals. |
| Model and credentials | Keep the existing `LLM_MODEL` configuration pending P3 confirmation of provider/model availability. LLM and ElevenLabs key holders are still unassigned; share secrets privately. Forecast verification requires neither service. |

## Required data interfaces for forecast integration

P1 must review and implement `get_balance(user_id, as_of) -> float` in GBP,
representing the authoritative balance at the **close of as_of**. The forecast
never infers a bank balance from unanchored transaction totals or fixture output.
The initial data model does not supply this source, so real forecast integration
remains blocked until P1 supplies it under #5.

For #35, propose `get_household_members(household_id) -> list[User]`. Membership
must come from stored users, not hardcoded persona names. Shared account/pot
ownership and internal-transfer representation require P1 agreement before
claiming real household integration. Unknown users/households must fail clearly.

## Local setup and evidence

Restore `.gitignore` and `.env.example` from the architecture archive. Create a
local `.env` from the example without overwriting an existing one; never commit
keys. The scaffold reads process environment variables, so export local settings
before invoking Python when changing the defaults.

On the implementation machine:

- `PATH="$PWD/.git/forecast-venv/bin:$PATH" make install`: passed.
- `PATH="$PWD/.git/forecast-venv/bin:$PATH" make api`: started on port 8000.
- `make web`: Vite started on port 5173.
- `GET /health`: `ok=true`; all three mock flags true.
- Browser verification: dashboard, £210 safe-to-spend, chart, corrected risk,
  alerts and chat controls rendered; no browser errors or Vite overlay detected.
- `PATH="$PWD/.git/forecast-venv/bin:$PATH" make test`: 66 passed.
- `npm --prefix web run build`: TypeScript and production build passed.

This is one-machine evidence. All five-machine setup confirmations, all-five
approvals, model/key-holder decisions and upstream data integration remain open.
