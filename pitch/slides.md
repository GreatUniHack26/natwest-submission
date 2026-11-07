# FinTime slides (7 slides)

Rule for every slide: one idea, one number, big. Speaker notes under each.
Stats marked **[verified]** were checked against the primary source on 7 Nov 2026. **[secondary]** = confirmed in several reports citing the primary, but the primary PDF was not opened. Anything not marked, don't put on a slide.

---

## Slide 1 - Title

**FinTime**
*See your money's future before it happens.*

A digital twin of your money, with an AI coach that explains it in plain English.

Team names · NatWest challenge: AI-Powered Financial Inclusion & Resilience

> Notes: open with Sam's hook from the demo script, not with the slide.

---

## Slide 2 - The problem

**Your balance is the wrong number.**

- **1 in 4** UK adults have low financial resilience. **[verified]** FCA, Financial Lives May 2024 survey, published 16 May 2025.
  That's **13.1 million** people (24%). **[secondary]** same survey, key findings.
- **1 in 10** have no cash savings at all. **[verified]** FCA, same release.
- **62%** of adults said their cost of living went up in the past month. **31%** of renters/mortgage payers find housing costs hard to afford; **34%** of bill payers find energy hard to afford. **[verified]** ONS, Public opinions and social trends, GB, survey 1 Oct 2025 - 4 Jan 2026.

People on irregular or low incomes get hurt by **timing**, not just totals: the bill lands before the shift pay. Banking apps show the past.

> Notes: don't read the bullets. Say "a quarter of the country", then point at Sam.

Sources:
- FCA press release, 16 May 2025: https://www.fca.org.uk/news/press-releases/more-people-have-bank-accounts-one-ten-have-no-cash-savings
- FCA Financial Lives 2024 key findings (PDF): https://www.fca.org.uk/publication/financial-lives/financial-lives-survey-2024-key-findings.pdf
- ONS, Public opinions and social trends, GB, December 2025: https://www.ons.gov.uk/peoplepopulationandcommunity/wellbeing/bulletins/publicopinionsandsocialtrendsgreatbritain/december2025

---

## Slide 3 - The solution

**A digital twin of your money.**

Four things, one screen:
1. **Safe to spend:** £1,640 in the bank → **£210** actually free, after rent pot, emergency pot and bills.
2. **Time travel:** 1,000 simulated futures. "26 Dec: likely −£144, 77% chance below £0."
3. **Alarms + idle money:** "Groceries double the usual pace." "Your £1,250 in pots could earn ~£14, keep it instant-access."
4. **Coach (text or voice):** "Ibiza next month? No, here's why. In a year? £50 a month, after fixing December."

> Notes: these are Sam's real numbers from the demo. One line each; the demo shows the rest.

---

## Slide 4 - How the AI works

**Maths you can audit. Language you can understand.**

Diagram (left to right, three columns):

```
 DATA                    TWIN ENGINE (deterministic Python)          COACH (Claude, tool-calling)
 ─────                   ─────────────────────────────────           ────────────────────────────
 Transactions  ──┐       Recurring bills + income detection          Reads a live snapshot of the twin
 (Open Banking)  │       90-day forecast (expected line)             Picks a tool, e.g. simulate_purchase,
 Pots            ├────▶  Monte Carlo: 1,000 seeded futures   ──────▶ plan_savings_goal, run_twin_simulations
 Calendar of     │        - replays your own past spending days      Quotes numbers verbatim + "numbers used"
 sales           │        - late / smaller pay, surprise costs       Never does arithmetic itself
 UK news (n8n) ──┘       Safe-to-spend, alarms, deposit ideas        Tone: friendly / direct / simple English
                                                                       │
                                                                       ▼
                                                              Voice (ElevenLabs) · text · numbers shown
```

- The engine does every calculation. Same inputs → same answer, every time (seeded).
- The LLM only chooses which tool to call and explains the result. About a dozen tools, max 5 tool rounds per answer.
- News comes in through an n8n workflow (BBC Business, Guardian Money, Bank of England RSS), treated as untrusted text and always credited.

> Notes: the one sentence to land: "The AI never does the maths. It explains our maths."

---

## Slide 5 - Responsible AI & inclusion

**Built for people banks find hard to predict.**

- **Irregular income first.** The twin models late pay and variable shifts; Sam, a student on café shifts, is the main persona. Maya, a care worker sharing a household, tests the low-income case.
- **Transparent.** Every answer lists the numbers it used. Every forecast lists its assumptions ("How the twin simulates").
- **Never pushes spending.** The coach is banned from "treat yourself". Waiting or not buying is always a valid answer.
- **Not advice.** General information only. Tax, benefits, legal → GOV.UK, Citizens Advice, MoneyHelper. Struggling → StepChange.
- **No shame.** Compares you to your own past, not to other people. Small realistic steps.
- **Accessible.** Plain English mode, voice in and out, screen-reader labels on charts and sliders.
- **Safe with untrusted text.** Merchant names, news and chat history are treated as data, not instructions (prompt-injection guard).

> Notes: say "information, not advice" out loud. Judges listen for it.

---

## Slide 6 - Feasibility

**It runs today. Nothing here needs a new law or a new data source.**

- **Data:** transaction feeds like the ones Open Banking already provides. UK Open Banking had **15.16 million** user connections in July 2025, "nearly one in three" adults. **[verified]** Open Banking Ltd, 1 Sept 2025. (OBL notes this counts connections, not unique people.)
- **Engine:** plain deterministic Python. Cheap, fast, testable: 500+ automated tests. No GPU.
- **AI:** one hosted LLM call per question, with an offline rule-based fallback (`DEMO_MODE`) if the model is down.
- **Bank-ready shape:** works as a "coach" tab inside an existing app; shown running in the iOS Simulator.
- **Regulation:** designed as general information under Consumer Duty principles. The FCA's new **targeted support** regime (rules PS25/22, live from 6 April 2026 per FCA announcements **[secondary]**) is a natural next step for a bank to offer more tailored nudges.
- **Today's demo uses synthetic data.** No real customer data.

Source: https://www.openbanking.org.uk/news/open-banking-surges-to-15-million-uk-users-as-july-marks-record-adoption/

> Notes: if asked "would NatWest actually ship this?" → yes: data they already hold, maths they can audit, an LLM that only talks.

---

## Slide 7 - Impact & roadmap

**From "where did my money go?" to "where is it going?"**

Impact for Sam: sees the 26 Dec problem **7 weeks early**, not on the day.

Roadmap:
1. **Now:** twin, time travel, pots, alarms, coach, voice, news. Three personas.
2. **Next:** full-duplex voice (talk over the coach, barge-in). Household view for couples and shared bills (Maya + Dan).
3. **Then:** proactive nudges ("your shift pay is late; want to move £20 from…?"), pilot with real Open Banking data, measure overdraft days avoided.
4. **With a bank:** offer inside the banking app; route people in difficulty to help earlier.

**What we'd measure:** fewer days overdrawn, fewer missed bills, more people with an emergency pot.

> Notes: end on the line "FinTime shows you where it's going." Don't claim impact numbers we haven't measured.

---

## Optional slide 8 - Why this wins (only if a slot needs filling)

| Judges ask | FinTime answers |
|---|---|
| Real need? | Timing problems for irregular incomes |
| Innovative? | 1,000-future twin + time travel + what-if |
| Fair & transparent? | Numbers shown, no pushing, signposting |
| AI adds value? | Predicts and explains; never guesses numbers |
| Realistic? | Open Banking data, deterministic engine, runs today |
