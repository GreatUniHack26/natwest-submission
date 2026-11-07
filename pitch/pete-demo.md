# Pete: student demo

All data is synthetic. Pete is a full-time university student in Manchester,
renting a room and working roughly 8–12 cafe hours a week during term, with
more shifts in summer. Amounts and examples below use seed 42 and demo date
**7 November 2026**. This is a representative demo story, not a claim about
average student finances.

## Start the demo

```sh
make seed
MOCK_DATA=0 MOCK_FORECAST=0 MOCK_AGENT=0 DEMO_TODAY=2026-11-07 make api
make web
```

Select **Pete** on the landing page or in the top bar. Pete is the default
dashboard persona. Check `/health`: data and forecast must both be false to
use Pete's ledger instead of the shared Sam fixtures. Live coach replies need
the project's LLM credentials; voice also needs the voice integration credentials.
No key or network is required to seed, categorise, or calculate his forecasts.

To reset only Pete after adding demo pots (leaves other personas alone):

```sh
python3 -c 'from backend.data.seed import seed; print(seed(personas=["pete"], households=[]))'
```

Use the same `DB_PATH` for seeding and the API. Transaction label overrides
survive reseeding by design; clear demo overrides separately if you changed labels.

## What's in his account

- **731 transactions** from 7 November 2025 through 7 November 2026, across
  12 spending categories, including one opening balance representing earlier savings.
- Weekly cafe wages: £100 / £125 / £150 during term; £175 / £200 / £225
  in summer. Historical receipts vary; future pay is uncertain.
- £175 monthly family support on the 20th, plus £1,800 maintenance payments
  on 12 January, 20 April and 21 September. These dates/amounts are fictional.
- £625 rent on the 1st; £12 phone, £48 energy and £10 shared internet monthly.
- Spotify Student, Netflix and PureGym; regular supermarket shops, campus
  lunches, bus fares, train trips home, toiletries, printing and social nights.
- Less frequent books, clothing, cinema, a laptop repair and room essentials.
- A recent eating-out spike, about 2.2 times the preceding four-week weekly average.
- **£1,750 balance**, **£1,325 protected in pots**, **£101.80 upcoming bills**,
  leaving **£323.20 safe to spend**. The bills reserve includes a toiletries
  payment inferred as recurring from the historical ledger.

| Pot | Amount | Due |
|---|---:|---|
| Manchester Student Lettings (rent) | £625 | 1 December 2026 |
| Emergency fund | £350 | Open-ended |
| Laptop replacement | £200 | 6 May 2027 |
| Train home and gifts | £150 | 19 December 2026 |

The rent pot deliberately matches the rent merchant and due date exactly so
the forecast pays that bill from the pot once, without reserving it twice.
Pot balances are already included in the account balance, not extra money.

## Suggested walkthrough and follow-ups

| Feature | Ask or show | Verified baseline / purpose |
|---|---|---|
| Safe to spend | “Why can't I spend my whole balance?” | £1,750 balance versus £323.20 safe after pots and bills |
| Small purchase | “Can I afford a £30 shirt?” | Affordable; £293.20 safe afterwards; general sale date 27 November, with no discount guarantee |
| Follow-up | “What about a £500 laptop instead?” | Unaffordable; £176.80 over today's safe budget |
| Protection | “Can I use my rent pot for it?” | Coach explains what the protected £625 is for |
| Recorded history | “What did I spend in October 2026?” | £1,243.09 spent, £900 received; net cash flow −£343.09 |
| Follow-up | “How much of that was eating out?” | £126.11 in October; groceries £165.30; rent £625 |
| Compare months | “How does that compare with September?” | September: £1,261.28 spent and £2,475 received, including maintenance |
| Specific purchase | “What did I spend at Uniqlo in October?” | Winter jacket, £59.90 on 16 October |
| Alerts | “Why has my eating-out spending been flagged?” | Recent takeaway spike compared with recorded habits |
| Spending projection | “Where is this month's spending heading?” | Real category projections, with historical typical spending |
| Time travel | Open Future; move through December, January and February | Rent steps, weekly wages, uncertainty bands, dated events; baseline protected-money risk on 1 February |
| What-if | Set future income to 50% in the time machine | Expected balance first drops below zero on 14 January 2027 |
| Twin odds | “How likely am I to run out over 90 days?” | Seeded simulated futures; quote the tool's results, not a guaranteed outcome |
| Savings goal | “Could I save £400 for a laptop by May?” | Planner checks feasibility and proposes a pot; this does not itself add money |
| Savings pots | Add a small new pot and return to Home | Safe budget and forecasts refresh after saving |
| Deposit ideas | “Could my pots earn anything before I need them?” | Four pot suggestions using an illustrative rate, not a live offer |
| Student tips | Open Tips | Student Council Tax and Railcard information based on student/rent/transport history |
| Accessibility | Ask for the explanation in simple mode; play voice if configured | Same financial data in a different presentation |

The coach's `get_spending_history` tool accepts explicit dates, an exact category,
or a merchant substring. Totals include every matching transaction; only the
latest 20 individual records are returned. Opening savings and internal transfers
are excluded from income/spending totals. Conversation history already carries
follow-ups; the tool now lets the coach verify their historical amounts.

Forecasts learn from the last 180 days, with everyday spending based on 84 days;
the full year remains searchable in Activity and through the history tool.
Termly maintenance has gaps too long for the current recurrence detector, so
January's next payment is **not assumed** in the forecast. Explain that limitation
when showing the income-cut scenario rather than promising or inventing a payment.
Existing label overrides or extra pots change the baseline numbers above.

## Checks

`pytest -q tests/test_pete_demo.py` checks the complete generated ledger through
SQLite, API responses, categorisation without live calls, affordable/unaffordable
purchases, alerts, historical follow-ups, timeline, what-if, twin simulations,
deposit ideas and student tips. It does not call a live LLM or voice provider.
