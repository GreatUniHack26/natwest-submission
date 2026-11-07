# Judge Q&A prep

Answer in one breath, then stop. If they want more, they'll ask.

**1. Why not let the LLM do the forecasting?**
LLMs are bad at arithmetic and can't show their working. If a model tells someone they can afford rent and it's wrong, that's real harm. So the maths is deterministic Python: same inputs, same answer, and every number can be traced. The LLM only picks which calculation to run and explains the result. It is told never to do arithmetic, and every reply carries the `numbers_used` it quoted.

**2. How do you stop it giving bad advice? What about regulation?**
Three layers. First, the numbers come from the engine, not the model. Second, the system prompt bans pushing purchases ("treat yourself" is forbidden) and requires naming the numbers used. Third, it's framed as general information, not regulated advice: tax, benefits or legal questions get general facts and a link to GOV.UK, Citizens Advice or MoneyHelper. For a bank, the FCA's new targeted-support regime (from April 2026) is the route to more tailored nudges.

**3. What about people with no stable income at all?**
That's who we built it for. Sam's pay is café shifts that vary week to week. The twin doesn't assume a salary: it learns income patterns from transactions, lets pay arrive 1-3 days late in a quarter of futures, and varies amounts by how much they've varied before. Instead of one fake-precise line, you get odds: "77% chance below £0 on 26 Dec." Runway ("17 days if pay stopped") is the honest number for someone with no guaranteed income.

**4. How is the Monte Carlo seeded? Is it repeatable?**
Yes. The random generator is seeded from a hash of user, date, number of simulations and scenario. Same day, same data → identical results, so the demo and the tests are repeatable and anyone can audit an answer later. Tomorrow's run uses a new seed because the date changes.

**5. What goes into each simulated future?**
Each of the 1,000 futures replays Sam's own past spending days (same weekday, last 84 days), so habits carry over. Bills and income vary by their real spread. Irregular pay can be 1-3 days late. A surprise cost hits about once every 45 days, typically around £49, capped at £600. All of this is listed in the app under "How the twin simulates".

**6. Data privacy?**
Today's demo uses synthetic data only. In production it would read the same transaction data a bank already holds, or Open Banking with the customer's consent. Calculations run on our side; the LLM sees a short summary snapshot, not raw statements. Conversation memory is sent back by the app each turn (last 20 turns), not stored by the coach. A bank deployment would use a model hosted under its own data agreements.

**7. Isn't "100% chance of going below zero" scary? Doesn't that cause anxiety?**
It's true for Sam's numbers, and hiding it is worse. We pair every risk with one small, concrete step and a date far enough away to act. Sam learns about 26 December on 7 November, seven weeks early, not when the payment bounces. Tone is never shaming, and the coach points to free help (StepChange, Citizens Advice) when things look hard.

**8. How is this different from existing budgeting apps?**
Most show where money went: categories and pie charts. FinTime shows where it's going, with odds, on a specific date, and lets you test a decision before you make it. Two other differences: it understands ring-fenced pots (balance £1,640, safe £210), and it's built for irregular incomes rather than monthly salaries.

**9. What if the AI or the network fails?**
The forecast, simulations, pots and alerts don't use AI at all, so they keep working. For the coach, `DEMO_MODE` serves a rule-based reply built from the same engine numbers. The one thing you lose is natural conversation.

**10. How do you handle prompt injection, e.g. a merchant called "ignore your rules"?**
Merchant names, category labels, news headlines and chat history are all treated as data. The prompt says so explicitly, news text is stripped of HTML and length-capped before the model sees it, and the model can only act through a fixed list of tools that validate their inputs. Worst case it says something odd; it cannot change a number.

**11. Is it feasible for NatWest to ship?**
Yes. It needs transaction data the bank already has, a deterministic engine that runs on ordinary servers (500+ automated tests), and one LLM call per question. It's designed as a coach tab inside an existing app; we have it running in the iOS Simulator in that form. Nothing depends on new regulation or new data sources.

**12. How would you measure impact?**
Days spent overdrawn, missed bill payments, and the share of users with an emergency pot, compared before and after. Plus a simple one: how many days' warning users got before their first predicted shortfall. We haven't measured these yet; today's data is synthetic.

---

## Curveballs (one-liners)

- **"Where do the deposit rates come from?"** Illustrative 4% AER, labelled "not a product offer". A bank would plug in its own savings products.
- **"Why Claude?"** Strong tool use and good at following safety rules. The architecture is model-agnostic: the model only calls tools.
- **"Why does the coach keep mentioning 26 December?"** By design. It surfaces the most important risk even if you didn't ask.
- **"Why is the 30-day risk only 4% but 60-day 100%?"** The rent pot covers December rent, so the next month looks fine. The gap opens when the second £800 course fee lands on 26 Dec.
- **"What about households?"** Built: Maya and Dan share a household forecast with shared bills. It's on the roadmap slide; avoid a live demo unless asked.
- **"Is the news reliable?"** It's third-party, named by publisher, and only used to explain how costs might move. It never changes a calculation.
