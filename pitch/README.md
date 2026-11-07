# Pitch (P5)

| File | What it's for |
|---|---|
| `demo-script.md` | 3-minute demo, second by second, as Sam. Plus 60-second version, offline fallback, pre-flight checklist. |
| `slides.md` | 7 slides of content with sourced UK stats. |
| `judging-map.md` | Each judging criterion → the demo moment that proves it. |
| `qa-prep.md` | 12 likely judge questions + curveballs. |

## Story in one line
Sam has £1,640 and feels fine. FinTime's twin lived 1,000 futures and knows only £210 is safe, and that 26 December is likely −£144. The coach says no to Ibiza next month and gives Sam a path to Ibiza next year.

## Must say out loud
- Inclusion: built for variable and low income; plain-language and voice modes.
- Transparency: every answer shows the numbers and assumptions used.
- Responsible AI: maths is deterministic; the LLM only explains; never pushes purchases; information, not advice.
- Data is synthetic.

## Checklist before presenting
Full list in `demo-script.md` → "Pre-flight checklist". Short version:
- [ ] `/health`: all mock flags `false`, `llm` and `voice` `true`
- [ ] `POST /users/sam/timeline` returns 200 (was 500 on the running server on 7 Nov; restart API)
- [ ] Both Ibiza questions asked once (warms reply + audio cache)
- [ ] `DEMO_MODE=1` fallback tested once
- [ ] Backup screen recording ready
