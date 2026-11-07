# Data module (P1)

Storage, synthetic personas and need/want labelling. Everything else reaches data only through
`backend.data` (never `sqlite3`); a test enforces that.

## Quick start
```
make seed                            # generate all personas into SQLite (idempotent, safe to re-run)
MOCK_DATA=0 make api                 # serve real data   (DB path: DB_PATH, default ./fintime.db)
make test
```
With `MOCK_DATA=1` (the default) every function returns fixtures and the DB is never opened.
Seeding needs no API key: rules and the committed `label_cache.json` cover every generated merchant.

## Personas (`generator.py`, deterministic per seed, anchored to `config.TODAY`)
| id | persona | notes |
|---|---|---|
| `sam` | student, irregular income (Manchester) | planted eating-out spike, December rent pot |
| `pete` | university student with a part-time cafe job (Manchester) | 12 months / 731 transactions, termly maintenance, four pots, purchase/history/twin demo; see `pitch/pete-demo.md` |
| `alex` | salaried, fixed £2,350 on the 28th (Bristol) | the comfortable contrast case |
| `maya`, `dan` | low-income family, household `h1` (Leeds) | shared pots owned once by `maya`; `dan`'s hours were cut ~30 days ago |

`generate_persona(name)` for single users, `generate_household('family')` for the two-adult household.

## Public interface (`backend.data`)
`get_user` (unknown -> `KeyError`), `get_household_members`, `get_transactions(user, start, end)`,
`get_pots`, `add_pot` (duplicate id -> `DuplicatePotError`, unknown user -> `UnknownUserError`; both `ValueError`),
`set_override` / `get_overrides`, `categorise`, `generate_persona`, `generate_household`.

API errors: unknown user 404, duplicate pot 409, unknown/foreign transaction on PATCH 404, bad body 422.

## Labelling (`categoriser.py`)
Precedence: user override > income sign > whole-word `RULES` > `label_cache.json` > ONE batched LLM call
(cached, needs `LLM_API_KEY`) > `('other', 'want')` fallback with a warning (never cached).
Overrides are stored in `transaction_overrides` and layered on read, so forecast and alerts see them
and they survive re-seeding. Marking a spend as `income` removes it from spend maths (allowed on purpose).

## Related modules by the same owner
- `backend/planner/`: `plan_debt` (avalanche vs snowball, capped by safe-to-spend), `plan_goal`, `plan_emergency_fund`.
- `backend/benchmarks/`: `get_benchmark(region, household_size)` from ONS Family Spending (figures verified against the published workbooks).

## Known limits
- Planners and benchmarks are not exposed through the API or agent tools yet.
- Debts have no storage: `plan_debt` takes them as input.
