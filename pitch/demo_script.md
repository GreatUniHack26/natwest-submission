# Demo script and storyboard (issue #28)

Persona: **Sam**, student in Manchester, irregular cafe-shift income.
Pitch line: **"FinTime keeps a twin of your money, and lets you time-travel through it."**

Roles
- **Presenter** (talks, never touches the laptop): ______
- **Driver** (clicks and types, never talks): ______ (suggest the P4 frontend owner, who knows the UI)

Numbers below come from the fixtures. Re-check them against the live build at integration (issue #2) and update this file.

## Setup (before walking on stage)
- Browser on `http://localhost:5173`, zoom 125%, one tab only, notifications off.
- API running (`make api`), `GET /health` shows the agreed flags.
- Tone set to **Friendly**, voice on, volume tested.
- Chat box empty. Slider at today (7 Nov).

## Run sheet (2:30 demo inside a 4:00 pitch)

| Time | Step | Driver does | Presenter says | Depends on |
|---|---|---|---|---|
| 0:00-0:20 | Hook | Nothing. Dashboard visible. | "Meet Sam. Student in Manchester, works cafe shifts. Some weeks £140, some weeks nothing. Every banking app tells Sam what already happened. None of them tell Sam what's about to happen." | none |
| 0:20-0:45 | Safe to spend | Point cursor at the safe-to-spend card, then the breakdown lines. | "Sam has £1,640 in the bank. Feels fine. FinTime says only **£210** is actually safe to spend. £1,250 is already set aside for rent and emergencies, and £180 of bills land before the next pay." | forecast (pots), data |
| 0:45-1:15 | Time travel | Drag the slider slowly to 26 Dec. Hover the risk line. Open "Assumptions". | "This is Sam's financial twin, 8 weeks ahead. Around Boxing Day the expected balance is £180, but the low line drops below zero before January income arrives. And here's exactly why: rent repeats, spending follows Sam's own weekday pattern, shift pay varies. No black box." | forecast (engine), web (slider) |
| 1:15-1:35 | Alert | Scroll to the alerts. | "It also spots changes early. Eating out is up 60% on Sam's 4-week average. It doesn't just warn, it gives one action: cap eating out at £25 for 7 days." | forecast (alerts) |
| 1:35-2:10 | Can I afford it? | Type: `I'm in Uniqlo, can I afford a £30 shirt?` and press Enter. Point at the "Numbers used" line. | "Now the moment money decisions really happen: at the till. Yes, Sam can afford it, it leaves £180 safe. But Black Friday is 27 November, three weeks away. Waiting could save money. Every number it quoted came from the forecast code. The AI only explains." | agent, forecast (simulate) |
| 2:10-2:30 | Tone + voice | Switch tone to **Simple English**, send the same question, press play on the audio. | "Not everyone reads finance comfortably. Sam can pick plain language, and hear the answer out loud." | agent (tone, voice), web |
| 2:30 | Hand back | Leave the dashboard on screen. | "That's the twin. Back to the slides." | none |

## Optional beats (only if built and tested 3x by feature freeze)
| Step | Driver types | Presenter says | Depends on |
|---|---|---|---|
| What if | `What if I lose my Saturday shift?` | "Change one thing, and the twin replays the future: the shortfall arrives on [date from live build]." | forecast `overrides`, new agent tool |
| Tip | Open the tips card | "It also finds money: schemes and reliefs Sam may be eligible for. Information, never advice." | rules/ |

## Cut plan (if something isn't ready)
| Broken module | Cut |
|---|---|
| Voice | Skip the audio, keep the Simple English switch. Say "and it can read this aloud". |
| Agent (LLM) | Run with `MOCK_AGENT=1`. The canned reply is the same story. |
| Forecast | Run with `MOCK_FORECAST=1`. Fixtures carry the same numbers. |
| Everything | Play the backup video (see `fallback_plan.md`). |

## 3-minute version
Drop the alert step (1:15-1:35) and say one line about alerts during the time-travel step.
