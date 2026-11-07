# FinTime: a financial twin you can time-travel through

> Draft for issue #31. Replaces the top of the root `readme.md` after integration (T+4:15). Fill every `[ ]` from the live build; delete anything not built.

## The problem
People on irregular income (students, shift and gig workers) get surprised by money. Banking apps show what already happened. Nobody shows what's about to happen.

## What FinTime does
FinTime builds a twin of your finances from your transaction history and projects it 8-12 weeks forward.
- **Safe to spend:** what you can really spend today, after rent and emergency pots and bills due before your next pay.
- **Time travel:** drag a slider through your future balance, with a low / expected / high range and the dates where you could go negative.
- **Alerts:** early warnings when a category suddenly jumps, each with one suggested action.
- **Can I afford it?:** ask at the till. It answers with the numbers, and suggests better timing (for example, a sale three weeks away).
- **Plain language and voice:** Friendly, Direct or Simple English, spoken aloud.

## Demo in 60 seconds
1. `make install && make api` (terminal 1), `make web` (terminal 2)
2. Open http://localhost:5173
3. Look at safe to spend, drag the slider to 26 Dec, ask "I'm in Uniqlo, can I afford a £30 shirt?"

## Architecture
[ insert the FinTime architecture diagram ]
`web -> api -> agent -> forecast -> data`. Forecast maths is deterministic Python. The LLM only calls tools and explains their output.

## What is real vs mocked
| Module | Demo setting | Notes |
|---|---|---|
| Data | [ real / fixtures ] | Synthetic persona generator + SQLite |
| Forecast | [ real / fixtures ] | Recurring bills + weekday baseline + range |
| Agent | [ real / fixtures ] | LLM tool loop, model: [ ] |
| Voice | [ on / off ] | ElevenLabs text to speech, cached demo lines |

## AI usage and data disclosure
- All data is **synthetic**. No real customer data.
- The LLM never calculates. Every reply lists the `numbers_used` it quoted, and forecasts list their assumptions.
- It never pushes a purchase. General information, not regulated financial advice.

## Limitations and next steps
- Forecast accuracy is validated on synthetic data only.
- Next: family view, what-if life events, tips engine (reliefs and benefits checks), regional benchmarks, debt planner, proactive nudges, a real open-banking feed.

## Team
[ names and roles ]
