# FinTime - financial time-travel coach

Modular monolith. One repo, one folder per owner. Everything runs on fixtures out of the box.

## Quickstart
```bash
make install
make api     # http://localhost:8000/docs
make web     # http://localhost:5173
make test
```

## Who owns what (edit only your folder)
| Owner | Folder | Public interface |
|---|---|---|
| P1 Data | `backend/data/` | `get_user, get_transactions, get_pots, add_pot, categorise, generate_persona` |
| P2 Forecast | `backend/forecast/` | `forecast, safe_to_spend, simulate_purchase, detect_alerts` |
| P3 Agent | `backend/agent/` | `chat` |
| P4 Frontend | `web/` | calls the REST API only (`web/src/api.ts`) |
| P5 Pitch | `pitch/` | demo script, slides; also owns tests/demo checklist |
| Shared | `contracts/`, `backend/api/` | change only via PR approved by all 5 |

Dependency direction: `web -> api -> agent -> forecast -> data`. Never skip a layer.

## Mock flags (integration)
Each module returns fixtures while its flag is `1` (see `.env.example`). To integrate, set
`MOCK_DATA=0` once P1 is ready, then `MOCK_FORECAST=0`, then `MOCK_AGENT=0`.
If a module breaks before the demo, flip just that flag back to `1`.
`GET /health` shows which flags are on.

## Rules
- Forecast maths is deterministic code. The LLM only explains tool output.
- Every result carries `numbers_used` / `assumptions` so the user can see why.
- Merge to `main` about every 45 min. Never leave `main` red (`make test`).
- Adding a field to a contract? Update `contracts/schemas.py`, the fixture, `web/src/types.ts` in one PR.

## Extensions (hooks already in place)
- Family view: `User.household_id`; add `GET /households/{id}/forecast` summing members.
- What-if: `forecast(..., overrides={...})`.
- Tips: add a rule file in `backend/rules/` and register it in `RULES`.
- Regional benchmarks: new `backend/benchmarks/` module exposed as an agent tool.
