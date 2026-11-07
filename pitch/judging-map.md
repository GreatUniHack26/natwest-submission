# Judging map

Each criterion → the moment in the demo that proves it → the line to say → where it lives in code.
Times refer to `demo-script.md`.

## 1. Customer focus & user-centric design

| Proof | Demo moment | Say | Code |
|---|---|---|---|
| Starts from a real person, not a feature list | 0:15 Sam: café shifts, stipend, course fees | "Irregular income makes the balance the wrong number." | persona fixtures, `backend/forecast/recurring.py` |
| Personal, not generic | 0:35 £1,640 → £210, every line Sam's own | "Sam's rent, Sam's bills, Sam's payday." | `backend/forecast/pots.py` |
| Compares you to you | 1:55 groceries vs Sam's usual pace | "Sam vs Sam, never Sam vs average." | `backend/forecast/spending.py`, `alerts.py` |
| Accessible for underserved groups | 2:15 voice in/out; tone "Simple English" | "Talk to it. Or switch to simple English." | `web/src/components/ChatPanel.tsx`, `backend/agent/prompts/tone_simple.md`, `backend/agent/voice.py` |
| Fits where people already are | Phone build as a coach tab in a bank app | "It's a tab in the app you already use." | iOS Simulator build |

## 2. Innovation & creativity

| Proof | Demo moment | Say |
|---|---|---|
| Digital twin with 1,000 futures, not one guess | 0:55 "Your twin lived 1,000 possible futures" | "Not a forecast. A thousand of them." |
| Literal time travel | 1:10 drag scrubber to 26 Dec: likely −£144, 77% | "Scrub to any day and read your odds." |
| Try a decision before making it | 1:25 what-if holiday £1,600 → danger moves to 5 Dec | "Time-travel with a choice before you make it." |
| Advice that checks itself against the future | 1:35 deposit idea says "keep it instant-access, forecast leans on this money on 26 Nov" | "The twin checks its own advice." |
| Sale-aware "can I afford it?" | backup Q: £30 shirt → fits, sale 27 Nov | "Waiting is always a valid answer." |

Code: `backend/forecast/montecarlo.py`, `timeline.py`, `scenarios.py`, `deposits.py`, `sales.py`; `web/src/components/TimeTravel.tsx`, `TwinOdds.tsx`.

## 3. Social impact & inclusivity (fairness, ethics, transparency)

| Proof | Demo moment | Say |
|---|---|---|
| Targets the 1 in 4 with low resilience | 0:15 FCA stat | "A quarter of UK adults." |
| Transparency | Numbers-used chips under every coach reply; "How the twin simulates" assumptions | "Every answer shows its working." |
| Says no when no is right | 2:15 Ibiza: "−£390, would use your rent pot" | "It didn't tell Sam what Sam wanted to hear." |
| Never pushes purchases | Coach rule; shirt answer offers waiting or skipping | "Not buying is always respected." |
| Signposts free help | Coach mentions MoneyHelper / Citizens Advice / StepChange when struggling | "Points to free help early." |
| No shame | Alarms are neutral, one action each | "One action, not a lecture." |

Code: `backend/agent/prompts/base.md` (guardrails), `backend/integrations/news.py` (untrusted-text sanitising).

## 4. Use of AI & data (predictive, time travel, responsible AI)

| Proof | Demo moment | Say |
|---|---|---|
| Predictive insight | 30/60/90-day odds, coin-flip date 26 Dec, runway 17 days | "Sam sees it seven weeks early." |
| Financial time travel | Scrubber + what-if chips | (as above) |
| AI adds value without doing maths | 2:15 coach picks `simulate_purchase`, then `plan_savings_goal`, quotes £50/month | "The AI never does the maths. It explains our maths." |
| Memory across turns | "What if I went in a year instead?" works without repeating Ibiza or £600 | "It remembers the conversation." |
| Live context | Coach raised 26 Dec unprompted in every answer we tested | "It's proactive about risks you didn't ask about." |
| Real-world data feed | n8n workflow → UK cost-of-living headlines, publisher named | "It knows energy prices are moving, and says who said so." |
| Repeatable | Same numbers every rehearsal (seeded RNG) | "Same inputs, same answer. Auditable." |

Code: `backend/agent/orchestrator.py`, `context.py`, `tools.py`, `planner_tools.py`; `integrations/n8n/fintime-news.json`.

## 5. Feasibility & practicality

| Proof | Demo moment | Say |
|---|---|---|
| Uses data banks already have | Slide 6: Open Banking 15.16m connections | "Transaction data banks already hold." |
| Cheap, testable engine | Slide 6: plain Python, 500+ tests | "No GPU. Runs on a laptop." |
| Works when the AI doesn't | `DEMO_MODE` offline fallback | "If the model is down, the engine still answers." |
| Bank-app shaped | iOS coach tab | "Drops into an existing app." |
| Clear story from the customer's side | Whole demo told as Sam | (the demo itself) |
