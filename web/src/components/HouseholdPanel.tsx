import { useState } from "react";
import { dateLabel, gbp } from "../format";
import type { Forecast } from "../types";
import ForecastChart from "./ForecastChart";
import "./HouseholdPanel.css";

const householdBudget = [
  { label: "Combined balance", amount: 2900 },
  { label: "Money set aside", amount: -950 },
  { label: "Bills before next income", amount: -1240 },
];

const categoryTotals = [
  { label: "Housing and bills", amount: 1420 },
  { label: "Groceries", amount: 385 },
  { label: "Transport", amount: 160 },
  { label: "Eating out", amount: 110 },
];

const members = [
  { name: "Priya", role: "Adult", status: "On track" },
  { name: "Dan", role: "Adult", status: "Budget to review" },
  { name: "Maya", role: "Youth account", status: "On track" },
  { name: "Leo", role: "Youth account", status: "On track" },
] as const;

const householdForecast: Forecast = {
  user_id: "family-demo",
  horizon_days: 56,
  points: [
    { date: "2026-11-07", low: 2900, expected: 2900, high: 2900 },
    { date: "2026-11-14", low: 2390, expected: 2550, high: 2710 },
    { date: "2026-11-21", low: 2110, expected: 2300, high: 2490 },
    { date: "2026-11-28", low: 2620, expected: 2850, high: 3080 },
    { date: "2026-12-05", low: 1420, expected: 1700, high: 1980 },
    { date: "2026-12-12", low: 1090, expected: 1420, high: 1750 },
    { date: "2026-12-19", low: 790, expected: 1170, high: 1550 },
    { date: "2026-12-26", low: 400, expected: 830, high: 1260 },
    { date: "2027-01-02", low: 1520, expected: 2000, high: 2480 },
  ],
  risk_events: [],
  assumptions: [
    "The sample forecast includes household income and recurring bills.",
    "The projected range widens to reflect uncertainty in future spending.",
  ],
};

function HouseholdDemo() {
  const [cursor, setCursor] = useState(0);
  const point = householdForecast.points[cursor];
  const safeAmount = householdBudget.reduce((total, item) => total + item.amount, 0);

  return (
    <>
      <p className="household-demo-note">Sample data for the Family demo.</p>
      <div className="household-layout">
        <section className="household-spending" aria-labelledby="household-spending-title">
          <h3 id="household-spending-title">Combined safe to spend</h3>
          <p className="spending-amount money">{gbp(safeAmount)}</p>
          <p className="household-description">Available after money set aside and upcoming bills.</p>
          <dl className="household-totals">
            {householdBudget.map(({ label, amount }) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd className="money">{gbp(amount)}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="household-forecast" aria-labelledby="household-forecast-title">
          <h3 id="household-forecast-title">Combined forecast</h3>
          <div className="forecast-stage">
            <div className="forecast-summary">
              <div>
                <p className="forecast-label">
                  Expected balance <time dateTime={point.date}>{dateLabel(point.date)}</time>
                </p>
                <p className="forecast-amount">{gbp(point.expected)}</p>
              </div>
              <div className="forecast-range">
                <span>Projected range</span>
                <strong>{gbp(point.low)} to {gbp(point.high)}</strong>
              </div>
            </div>
            <ul className="forecast-legend" aria-label="Household chart legend">
              <li><span className="legend-expected" aria-hidden="true" /> Expected balance</li>
              <li><span className="legend-range" aria-hidden="true" /> Projected range</li>
            </ul>
            <ForecastChart data={householdForecast} cursor={cursor} onCursorChange={setCursor} />
          </div>
          <details className="forecast-assumptions">
            <summary>Household forecast assumptions</summary>
            <ul>{householdForecast.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul>
          </details>
        </section>

        <section className="household-categories" aria-labelledby="household-categories-title">
          <h3 id="household-categories-title">Spending by category</h3>
          <p className="household-description">Household totals for the last 30 days.</p>
          <dl className="household-totals">
            {categoryTotals.map(({ label, amount }) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd className="money">{gbp(amount)}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="household-members" aria-labelledby="household-members-title">
          <h3 id="household-members-title">Household members</h3>
          <p className="household-description">Only each member’s status is shared here.</p>
          <ul className="grouped-list" role="list">
            {members.map((member) => (
              <li key={member.name}>
                <div>
                  <strong>{member.name}</strong>
                  <p>{member.role}</p>
                </div>
                <span className="household-status" data-review={member.status === "Budget to review"}>
                  {member.status}
                </span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </>
  );
}

export default function HouseholdPanel({ demo }: { demo: boolean }) {
  return (
    <section className="panel household-panel" id="household" tabIndex={-1} aria-labelledby="household-title">
      <h2 id="household-title">Household</h2>
      {demo ? <HouseholdDemo /> : (
        <p className="panel-empty">Live household information is currently unavailable.</p>
      )}
    </section>
  );
}
