Implement the FinTime UI from the design files in design/ into this codebase.

Source of truth:

- @UI-Mockups/FinTime App.dc.html: the full prototype. It has the markup, inline styles and a logic class with the sample data and logic.
- @UI-Mockups/FinTime Showcase.dc.html: every screen and state at desktop (1440px) and mobile (390px), for visual reference.

Step 1, explore before coding:

- Read the repo structure, framework, routing, state management, styling approach and existing components.
- Find the API endpoints and data models. Map them to the data the design uses: balance, pots, bills, transactions, forecast with low/high band, alerts, purchase-affordability check, coach chat, personas, tips, benchmarks.
- Tell me what you found and any gaps, such as design features with no endpoint, before you build.

Step 2, build in the repo's own conventions:

- Screens: persona picker (landing), Dashboard, Can I afford it?, Transactions, Household (Maya & Dan only), Tips and benchmarks, Coach chat (docked on desktop, full-screen on mobile).
- Shared components: top bar with persona switcher, persona card, persona banner and "Why this fits me" side panel, tone selector (Friendly/Direct/Simple), safe-to-spend breakdown, forecast chart with range band, risk markers and date scrubber, alert card, pot card with progress ring, verdict card, "Numbers used" expander, "How was this calculated?" panel, Need/Want chip with inline edit.
- Replace the sample data in the prototype's logic class (the P object, verdict(), reply()) with real API calls. Keep the same output shapes.
- Persona and tone must flow through every number, alert, tip and chat reply.
- States: loading, missing data ("We don't have enough data. We won't show a guessed number.") and error with retry, on every data view.
- Responsive: bottom tab bar under about 768px, top nav above.

Design rules:

- Palette (no other colours, no gradients): purple #5A287D, deep purple #3C1053, accent #7B3FA0, lavender #F1EAF7, page #F5F5F7, divider #E3DAEB, text #1F1F1F and #5E5E5E, success #007A4D, warning #F2A900, danger #C8102E.
- Fonts: Montserrat for headings and money, Nunito Sans for body. Use tabular figures for money. Icons are Phosphor.
- Cards use a 12px radius; buttons and chips are pills. Hit targets are at least 44px, focus rings are visible, and every red/amber/green carries an icon or label.
- Copy: keep short plain sentences and never push the user to buy. Every tip footer reads "General information, not financial or tax advice."
- Put colours, spacing and radii into the repo's theme or tokens, not scattered literals.

Step 3: Add tests for the verdict and forecast logic. Then run the app and compare each screen against the Showcase frames at 1440px and 390px.

Work in small commits, one screen per commit, starting with the shell, the persona context and the dashboard.
