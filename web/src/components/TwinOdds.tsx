import { useEffect, useState, type CSSProperties } from "react";
import { api } from "../api";
import { dateLabel } from "../format";
import type { TwinSimulations } from "../types";

const pct = (value: number) => `${Math.round(value * 100)}%`;

/** Monte Carlo summary: the twin lived 1,000 possible futures. */
export default function TwinOdds({ userId, revision = 0 }: { userId: string; revision?: number }) {
  const [sim, setSim] = useState<TwinSimulations | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api.simulations(userId, controller.signal).then(
      (result) => { if (!controller.signal.aborted) setSim(result); },
      () => { if (!controller.signal.aborted) setSim(null); },
    );
    return () => controller.abort();
  }, [userId, revision]);

  if (!sim) return null;
  const within = Object.entries(sim.chance_below_zero_within);

  return (
    <section className="twin-odds" aria-label="Digital twin simulations">
      <p className="twin-badge">
        <span className="twin-spinner" aria-hidden="true" />
        Your twin lived <strong>{sim.simulations.toLocaleString("en-GB")}</strong> possible futures
      </p>
      <div className="twin-stats">
        <div className="twin-stat">
          <p className="twin-stat-label">Chance of going below £0</p>
          <ul className="twin-odds-row">
            {within.map(([days, chance], index) => (
              <li key={days} style={{ "--c": chance, "--i": index } as CSSProperties} data-level={chance >= 0.5 ? "high" : chance >= 0.2 ? "medium" : "low"}>
                <span className="twin-ring" aria-hidden="true" />
                <strong>{pct(chance)}</strong>
                <span>in {days} days</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="twin-stat">
          <p className="twin-stat-label">Runway if pay stopped today</p>
          <p className="twin-big">{sim.runway_capped ? `${sim.runway_days_if_income_stops}+` : sim.runway_days_if_income_stops}<span> days</span></p>
          <p className="twin-note">without touching your pots</p>
        </div>
      </div>
      {sim.coin_flip_date && (
        <p className="twin-callout">
          From <time dateTime={sim.coin_flip_date}>{dateLabel(sim.coin_flip_date)}</time>, more than half of your futures are below £0.
          {sim.chance_dip_into_pots > 0.5 && ` ${pct(sim.chance_dip_into_pots)} of futures borrow from your pots first.`}
        </p>
      )}
      <details className="forecast-assumptions">
        <summary>How the twin simulates</summary>
        <ul>{sim.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
      </details>
    </section>
  );
}
