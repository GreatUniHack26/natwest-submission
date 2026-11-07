# Slides outline (issue #29)

Target: 4:00 total. 6 slides before the demo, 4 after. One idea per slide, big text, no paragraphs.

| # | Slide | On screen | Say | Judging criterion |
|---|---|---|---|---|
| 1 | Title | **FinTime**: a financial twin you can time-travel through | Team names, one line | none |
| 2 | Problem | Irregular income + apps that only look backwards = surprises | "For people on shifts, gig work or student loans, the problem isn't last month. It's the next 8 weeks." | Customer focus |
| 3 | Persona | Sam: student, Manchester, cafe shifts, income changes weekly | Who we built for and why they're underserved | Customer focus, Social impact |
| 4 | Solution | The twin answers 3 questions: What can I spend today? What's coming? Can I afford this? | Safe to spend, time travel, can-I-afford, alerts | Innovation |
| 5 | Financial time travel | History → recurring bills + weekday pattern → 8-12 week projection with a low/expected/high range → risk dates | "Deterministic maths. The AI only explains it." | Use of AI and data |
| 6 | Demo | (switch to the live app, see `demo_script.md`) | | All |
| 7 | Architecture | Use the team's FinTime architecture diagram | "Modular: data, forecast, agent, web. Each layer swaps independently." | Feasibility |
| 8 | Responsible AI | Numbers used on every answer. Assumptions shown. Never pushes a purchase. Information, not advice. **Synthetic data.** | Transparency is built into the contract, not bolted on | Social impact (ethics), Use of AI |
| 9 | Impact + feasibility | Plain-language tone, voice, built for variable income. Runs on open-banking-shaped data; a bank could plug its own feed in. | Who benefits and how a bank ships it | Social impact, Feasibility |
| 10 | Roadmap | Family view · what-if life events · tips engine (reliefs and benefits) · regional benchmarks · debt planner · proactive nudges | One line each. Close on the tagline. | Innovation, Feasibility |

## Criteria coverage check
| Criterion | Slides |
|---|---|
| Customer focus | 2, 3, demo |
| Innovation | 4, 10 |
| Social impact + ethics | 3, 8, 9 |
| Use of AI and data | 5, 8, demo |
| Feasibility | 7, 9, 10 |

## Rules for the deck
- State "all data is synthetic" on slide 8, out loud.
- Every claim must match the live build. If a feature isn't built, it goes on the roadmap slide, not the solution slide.
- Only quote statistics with a source on the slide. Candidate for the roadmap slide: Policy in Practice estimates £22.7bn of UK benefits and support goes unclaimed each year (Missing Out, 2024).
