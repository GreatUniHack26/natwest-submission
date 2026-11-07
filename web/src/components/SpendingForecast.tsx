import type { CSSProperties } from "react";
import { gbp } from "../format";
import type { SpendingForecast as Forecast } from "../types";

const statusLabel = { over: "Running hot", watch: "Watch", on_track: "On track" } as const;
const title = (category: string) => category.charAt(0).toUpperCase() + category.slice(1);

/** The twin's month-end view per category: spent so far, where it's heading, what's usual. */
export default function SpendingForecast({ data }: { data: Forecast }) {
  if (data.categories.length === 0) return <p className="panel-empty">No everyday spending recorded this month yet.</p>;

  const scale = Math.max(...data.categories.map((c) => Math.max(c.projected_month, c.typical_month)), 1);
  const pct = (value: number) => `${(value / scale) * 100}%`;
  const hot = data.categories.filter((c) => c.status === "over");
  const progress = `${(data.days_elapsed / data.days_in_month) * 100}%`;

  return (
    <>
      <div className="month-summary">
        <div>
          <p className="month-label">Heading for this month</p>
          <p className="month-amount money">{gbp(Math.round(data.projected_month))}</p>
        </div>
        <p className="month-usual">
          usually <strong className="money">{gbp(Math.round(data.typical_month))}</strong>
          <span className="month-progress" style={{ "--p": progress } as CSSProperties}>
            day {data.days_elapsed} of {data.days_in_month}
          </span>
        </p>
      </div>

      {hot.length > 0 && (
        <ul className="month-alarms" aria-label="Spending alarms">
          {hot.map((c) => (
            <li key={c.category} role="alert">
              <span className="alarm-dot" aria-hidden="true" />
              {c.alarm}
            </li>
          ))}
        </ul>
      )}

      <ul className="month-bars" aria-label="Spending by category">
        {data.categories.map((c, index) => (
          <li key={c.category} data-status={c.status} style={{ "--i": index } as CSSProperties}>
            <div className="month-bar-head">
              <strong>{title(c.category)}</strong>
              <span className="month-chip" data-status={c.status}>{statusLabel[c.status]}</span>
              <span className="money month-bar-figures">
                {gbp(c.spent_so_far)} <span>→ {gbp(Math.round(c.projected_month))}</span>
              </span>
            </div>
            <div className="month-track"
              role="img"
              aria-label={`${title(c.category)}: ${gbp(c.spent_so_far)} spent so far, heading for ${gbp(c.projected_month)}, usually ${gbp(c.typical_month)}.`}>
              <span className="month-projected" style={{ "--w": pct(c.projected_month) } as CSSProperties} />
              <span className="month-spent" style={{ "--w": pct(c.spent_so_far) } as CSSProperties} />
              <span className="month-typical" style={{ "--x": pct(c.typical_month) } as CSSProperties} title={`Usual: ${gbp(c.typical_month)}`} />
            </div>
          </li>
        ))}
      </ul>
      <p className="month-key">
        <span><i className="key-spent" />Spent</span>
        <span><i className="key-projected" />Projected</span>
        <span><i className="key-typical" />Usual month</span>
      </p>
    </>
  );
}
