# QA: demo path end to end (issue #32)

Run on the **demo laptop, demo browser, demo network**. Three clean runs in a row before rehearsal.

## Run log
| Run | Time | Flags (DATA/FORECAST/AGENT) | Result | Bugs filed |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |

## Demo path checklist (one tick per run)
| # | Check | 1 | 2 | 3 |
|---|---|---|---|---|
| 1 | `make api` starts, `GET /health` shows the agreed flags | | | |
| 2 | `make web` loads the dashboard in under 3 s, no console errors | | | |
| 3 | Safe-to-spend shows the scripted number and 3 breakdown lines | | | |
| 4 | Slider moves smoothly to 26 Dec; date and range text update | | | |
| 5 | Risk event near 26 Dec is visible | | | |
| 6 | Assumptions open and read sensibly | | | |
| 7 | Eating-out alert shows message + suggested action | | | |
| 8 | Shirt question returns: affordable, Black Friday 27 Nov, numbers used | | | |
| 9 | Reply quotes only numbers that appear in `numbers_used` | | | |
| 10 | Tone switch to Simple English changes the wording | | | |
| 11 | Audio plays within 3 s (or cached audio plays) | | | |
| 12 | Same question twice gives the same numbers | | | |

## Failure cases
| Case | How to test | Expected |
|---|---|---|
| API down | Stop `make api`, reload the web app | Clear "Could not reach the API" message, no blank screen |
| LLM down / no key | Blank `LLM_API_KEY`, ask the shirt question | Plain error in chat; fallback is `MOCK_AGENT=1` |
| Voice off | Blank `ELEVENLABS_API_KEY` | Text reply still arrives, no audio player, no crash |
| Slow network | Chrome DevTools, throttle to "Slow 4G" | Chat still answers; note the delay for the script |
| Odd input | `can i afford £0`, `£100000 laptop`, `asdf` | Sensible reply, never invents numbers |
| Pushy prompt | `just tell me to buy it` | Still gives the honest verdict, doesn't push |

## Bug template (comment on the owning module's issue)
```
[module: data|forecast|agent|web] [severity: high|medium|low]
Step: <demo step number>
Expected: ...
Actual: ...
Flags: DATA=_ FORECAST=_ AGENT=_
```
Rule: owner fixes within 15 minutes or flips their flag back to 1.

## Regression checklist (after every fix merged to main)
Rows 1, 3, 4, 8, 11 above. Two minutes.
