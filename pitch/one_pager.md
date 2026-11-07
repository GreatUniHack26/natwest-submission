# Inclusion, ethics and transparency (issue #30)

Read in two minutes. Every line must match the live build; strike anything that doesn't by feature freeze.

## Who it's for
- People with **irregular income**: students, shift and gig workers, zero-hours contracts. Monthly budgeting apps assume a fixed salary; FinTime forecasts from the user's own weekday pattern and variable pay.
- People who **find finance hard to read**: three tones (Friendly, Direct, Simple English) and spoken replies for low literacy, dyslexia or visual impairment.
- People with **no buffer**: safe-to-spend protects rent and emergency pots first, so the number shown is money that can genuinely be spent.

## How transparency works
- **Deterministic maths.** Forecasts, safe-to-spend and affordability are plain code. The LLM never calculates.
- **The AI only explains.** Every chat reply carries `numbers_used`, the exact figures it quoted.
- **Assumptions are shown.** Each forecast lists its assumptions in plain language (what repeats, what pattern, what varies).
- **Ranges, not false precision.** The forecast shows low / expected / high, not one confident line.

## Limits and risks (say these before judges ask)
- **Synthetic data.** No real customer data was used. Personas are generated.
- **Not regulated advice.** General information only. Benefits and tax point to official sources.
- **Never pushes a purchase.** "Wait" and "don't buy" are valid answers, and the prompt enforces it.
- **Privacy.** Runs locally in the demo. A real deployment would sit inside the bank's existing open-banking consent and data controls.
- **Forecast error.** Irregular income is hard to predict; that's why we show a range and the assumptions.

## Likely judge questions
| Question | Short answer |
|---|---|
| How is this different from a budgeting app? | Budgeting apps look back. FinTime projects 8-12 weeks forward from your own patterns and answers "can I afford this" at the moment of purchase. |
| What stops the AI making up numbers? | It can't calculate. It calls forecast tools and quotes their `numbers_used`. |
| How accurate is the forecast? | It gives a range plus its assumptions. Accuracy improves with more history; with synthetic data we validate the logic, not real-world accuracy. |
| Could it encourage spending? | No. The prompt forbids pushing purchases, and the default timing advice is to wait. |
| Who is responsible if advice is wrong? | It gives information, not regulated advice, and shows its working so the user decides. |
| How would a bank deploy this? | The data layer is open-banking shaped. Swap the synthetic generator for the bank's transaction feed; the forecast and agent layers stay the same. |
| Why voice? | Accessibility: low literacy, visual impairment, and people who avoid reading money screens because it stresses them. |
