# FinTime demo script (3:00)

One persona, Sam. One story: "the bank balance lies; the twin doesn't."
Demo date is fixed at **Sat 7 Nov 2026**, so every number below is repeatable (the Monte Carlo is seeded).

**SAY** = words out loud. **DO** = clicks. **SHOW** = what is on screen.
Numbers checked against the live API on 7 Nov 2026. If a number on screen differs, say the screen's number.
Spoken text is ~450 words (about 2:50). Coach replies take 5-15 s each. If you're behind at 1:55, cut Alarms to one line: "And alarms when spending drifts: groceries are double the usual pace."

---

## 0:00 - 0:15 | Hook

**DO:** App open on Sam's Overview. Hand off the clicker; look at the judges, not the screen.

**SAY:**
> "Sam has £1,640 in the bank. Sam feels fine.
> But on Boxing Day, Sam will very likely be overdrawn. Nothing in a normal banking app tells Sam that today."

## 0:15 - 0:35 | Problem

**SAY:**
> "One in four UK adults has low financial resilience. That's the FCA's number.
> Sam is a student in Manchester: café shifts that change every week, rent, a course fee every month.
> With income like that, the balance is the wrong number. Banking apps show the past. Sam needs the future."

## 0:35 - 0:55 | The twin: what is actually safe

**DO:** Point at the **Safe to spend** card. Hover the breakdown.

**SHOW:** £1,640 balance → £950 December rent pot → £300 emergency pot → £180 bills before payday → **£210 safe to spend**.

**SAY:**
> "FinTime builds a digital twin of Sam's money from transactions. Synthetic data today, Open Banking data for real.
> First, it takes out money that's already spoken for: rent pot, emergency pot, bills before payday.
> So it's not £1,640. It's £210, and every line of the sum is shown."

## 0:55 - 1:35 | Time travel + Monte Carlo

**DO:** Scroll to **Time travel** (nav: Forecast). Point at the badge "Your twin lived 1,000 possible futures".

**SAY:**
> "Then the twin lives Sam's next 90 days, a thousand times. It replays Sam's real spending days, lets pay arrive late, throws in surprise costs.
> Next 30 days: about a 4% chance of going below zero. By 60 days: in every single future, Sam goes below zero."

**DO:** Drag the scrubber to **26 Dec**.

**SHOW:** Story line: "likely −£144", **77% chance below £0**. Marker: Course fee instalment −£800.

**SAY:**
> "Here's why. 26 December: the next £800 course fee lands, right after December rent. Shift pay can't keep up. Most likely balance minus £144, a 77% chance of being overdrawn.
> And if pay stopped today, Sam's runway is 17 days."

**DO:** Click the what-if chip **Holiday £1,600 in 4 weeks**.

**SHOW:** "below £0 from **5 Dec** (was 26 Dec) · ends £1,600 lower."

**SAY:**
> "And Sam can time-travel with a choice before making it. A £1,600 holiday pulls the danger date three weeks earlier, to 5 December."

**DO:** Click **Clear**.

## 1:35 - 1:55 | Pots + idle money

**DO:** Nav: **Pots**. Point at the two pots, then **Deposit ideas**.

**SAY:**
> "Pots protect money from Sam. But £1,250 is sitting idle.
> FinTime suggests an instant-access saver: about £14 of interest at an illustrative 4%.
> And a safety check: not fixed-term, because the forecast leans on that money around 26 November. The twin checks its own advice."

## 1:55 - 2:15 | Alarms

**DO:** Nav: **Alerts** (or point at **This month's spending**).

**SHOW:** Groceries £86.15 vs £40.21 usual by today. Eating out £52.11, 59% above Sam's weekly average.

**SAY:**
> "One week into November, groceries are already double what's usual by now. Eating out is up 59%.
> Each alert has one action, not a lecture. And it compares Sam to Sam, not to some average person."

## 2:15 - 2:50 | Voice coach: the Ibiza moment

**DO:** Nav: **Coach**. Tick **Read replies aloud**. Click the mic.

**SAY (into the mic, as Sam):**
> "Can I go to Ibiza next month? Flights and hotel are about £600."

**SHOW / coach says (live; wording varies):** "Doesn't look affordable right now. Safe to spend is £210, so you'd be at −£390. The only way to pay would be your rent and emergency pots…"
Numbers-used chips: `price 600 · safe_to_spend 210 · safe_after −390`.

**DO:** Mic again.

**SAY (as Sam):**
> "What if I went in a year instead?"

**SHOW / coach says:** "You'd need **£50 a month for 12 months**. Right now your forecast leaves about £0 a month spare, so fix 26 December first… I can re-run the plan for a later date or a smaller trip."

**SAY (to judges):**
> "Notice two things. The AI never did the maths: every number came from our engine, and it shows them.
> And it didn't tell Sam what Sam wanted to hear. It said no, then gave a path: £50 a month, after fixing December."

## 2:50 - 3:00 | Close

**SAY:**
> "13 million UK adults have low financial resilience. FinTime lets them see it coming weeks early, in plain English, out loud if they want.
> Most finance apps show you where your money went. FinTime shows you where it's going. Thank you."

---

## 60-second version

Use when time is cut or the judges are already at the stand.

| Time | DO | SAY |
|---|---|---|
| 0:00 | Overview open | "Sam has £1,640 and feels fine. FinTime knows only £210 is safe. The rest is rent, emergency money and bills." |
| 0:12 | Time travel, drag to 26 Dec | "Sam's twin lived 1,000 futures. On 26 December an £800 course fee lands: 77% chance of going overdrawn. Sam sees it seven weeks early." |
| 0:27 | Coach, mic: "Can I go to Ibiza next month? It's about £600." | "Coach says no: it would leave Sam at −£390 and eat the rent pot. It shows the numbers it used. The AI never does the maths; it explains our engine." |
| 0:45 | Point at alerts | "Plus alarms when spending drifts, and ideas to earn interest on idle pot money safely." |
| 0:52 | Look at judges | "Built for irregular incomes. Plain English and voice. Shows you where your money is going, not where it went." |

---

## If the network dies

The forecast, Monte Carlo, pots, alerts and deposit ideas are all local Python. **Only the coach (Claude) and voice (ElevenLabs) need the internet.**

1. **Before going on stage** (do it anyway): start the API with the offline fallback ready.
   ```bash
   DEMO_MODE=1 make api
   ```
   In `DEMO_MODE`, the coach serves a cached or rule-based reply built from the same engine numbers. No LLM call.
2. **What still works offline:** the Ibiza question. Fallback answer: "A £600 purchase is above your current safe-to-spend of £210 and would leave your safe-to-spend at −£390. Waiting until 27 Nov or pausing this purchase will help…" Same numbers-used chips.
3. **What does not:** the "in a year?" follow-up. The fallback answers with the safe-to-spend breakdown instead of a savings plan. **Swap the second question for** "Can I afford a £30 shirt?" → "fits, leaves £180, a sale starts 27 Nov". Say: "Even offline, every answer comes from the engine, not a model guessing."
4. **Voice:** pre-cached replies play from `/audio/…mp3` if the same question was asked during rehearsal (cache is keyed on the exact text). If the mic fails, type the question. Don't apologise; say "same thing, typed."
5. **Worst case:** play the backup screen recording and narrate the 60-second version over it.

## Pre-flight checklist (T-15 min)

- [ ] `GET /health` → `mock` all `false`, `llm: true`, `voice: true`.
- [ ] **`POST /users/sam/timeline` returns 200.** On 7 Nov it returned 500 from the running server even though `timeline('sam')` works when called directly. Restart the API and re-check; the Time travel chart depends on it.
- [ ] Browser zoom 125%, notifications off, Sam selected, scrolled to top.
- [ ] Ask both Ibiza questions once (warms the reply cache and audio cache).
- [ ] Mic permission granted in the browser; test once with the room's noise.
- [ ] Backup screen recording on the desktop.
- [ ] Stay on Sam. Don't open Maya live: her safe-to-spend shows −£522 and runway 0 days; correct maths for an over-committed household, but it needs explaining.
