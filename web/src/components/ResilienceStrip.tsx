import { useEffect, useState } from "react";
import { api, apiUrl } from "../api";
import { dateLabel, gbp } from "../format";
import type { Alert, SpendingForecast, TwinSimulations } from "../types";
import CountUp from "./CountUp";
import Icon from "./Icon";

interface Owed { total_est_value: number | null; items: unknown[] }

const pct = (value: number) => `${Math.round(value * 100)}%`;
const friendlyDates = (text: string) => text.replace(/\b(\d{4}-\d{2}-\d{2})\b/g, (iso) => dateLabel(iso));

/** The challenge, made visible: understand → anticipate → resilience → fairness, then the one alarm that matters now. */
export default function ResilienceStrip({ userId }: { userId: string }) {
  const [month, setMonth] = useState<SpendingForecast | null>(null);
  const [sim, setSim] = useState<TwinSimulations | null>(null);
  const [owed, setOwed] = useState<Owed | null>(null);
  const [alarm, setAlarm] = useState<Alert | null>(null);

  useEffect(() => {
    const c = new AbortController();
    const keep = <T,>(set: (v: T) => void) => (v: T) => { if (!c.signal.aborted) set(v); };
    api.spending(userId, c.signal).then(keep(setMonth), () => {});
    api.simulations(userId, c.signal).then(keep(setSim), () => {});
    fetch(apiUrl(`/users/${encodeURIComponent(userId)}/entitlements`), { signal: c.signal })
      .then((r) => (r.ok ? r.json() : null)).then(keep(setOwed), () => {});
    api.alerts(userId, c.signal).then(keep((alerts: Alert[]) => {
      const order = { high: 0, medium: 1, low: 2 } as const;
      setAlarm([...alerts].sort((a, b) => order[a.severity] - order[b.severity])[0] ?? null);
    }), () => {});
    return () => c.abort();
  }, [userId]);

  const shortfall30 = sim?.chance_below_zero_within["30"];
  const level = (v: number) => (v >= 0.5 ? "high" : v >= 0.2 ? "medium" : "low");
  const owedCount = owed?.items.length ?? 0;

  return (
    <section className="resilience" aria-label="Your financial resilience at a glance">
      {alarm && (
        <div className="alarm-banner" data-severity={alarm.severity} role={alarm.severity === "high" ? "alert" : "status"}>
          <span className="alarm-banner-icon" aria-hidden="true"><Icon name="alerts" /></span>
          <div className="alarm-banner-copy">
            <p className="alarm-banner-kicker">{alarm.severity === "high" ? "Needs attention now" : "Heads up"}</p>
            <p className="alarm-banner-text">{friendlyDates(alarm.message)}</p>
            {alarm.suggested_action && <p className="alarm-banner-action"><strong>Do this:</strong> {alarm.suggested_action}</p>}
          </div>
          <a className="alarm-banner-cta" href="#coach">Ask Nat <Icon name="chevron" /></a>
        </div>
      )}

      <ul className="resilience-tiles">
        <li>
          <a href="#forecast" className="r-tile" data-level={month ? (month.projected_month > month.typical_month * 1.1 ? "medium" : "low") : undefined}>
            <span className="r-kicker">Budget · this month</span>
            <span className="r-value money" aria-label={month ? gbp(Math.round(month.projected_month)) : "loading"}>
              {month ? <CountUp value={Math.round(month.projected_month)} /> : "…"}
            </span>
            <span className="r-label">{month ? `heading for, usually ${gbp(Math.round(month.typical_month))}` : "everyday spending this month"}</span>
          </a>
        </li>
        <li>
          <a href="#forecast" className="r-tile" data-level={shortfall30 !== undefined ? level(shortfall30) : undefined}>
            <span className="r-kicker">Time travel · next 30 days</span>
            <span className="r-value">{shortfall30 !== undefined ? pct(shortfall30) : "…"}</span>
            <span className="r-label">
              chance of a shortfall{sim?.coin_flip_date ? `; likely from ${dateLabel(sim.coin_flip_date)}` : ""}
            </span>
          </a>
        </li>
        <li>
          <a href="#forecast" className="r-tile">
            <span className="r-kicker">Resilience · runway</span>
            <span className="r-value">{sim ? `${sim.runway_days_if_income_stops}${sim.runway_capped ? "+" : ""}` : "…"}<small> days</small></span>
            <span className="r-label">if your pay stopped today, without touching pots</span>
          </a>
        </li>
        <li>
          <a href="#tips" className="r-tile" data-level={owedCount ? "good" : undefined}>
            <span className="r-kicker">Fairness · money you might be owed</span>
            <span className="r-value money">
              {owed === null ? "…" : owed.total_est_value ? <>up to {gbp(Math.round(owed.total_est_value))}</> : owedCount ? `${owedCount} to check` : "None found"}
            </span>
            <span className="r-label">{owedCount ? `${owedCount} scheme${owedCount > 1 ? "s" : ""} from GOV.UK to check` : "we keep checking GOV.UK schemes"}</span>
          </a>
        </li>
      </ul>
      <p className="r-footnote">
        <Icon name="forecast" /> Every number comes from your own transactions and {sim?.simulations?.toLocaleString("en-GB") ?? "1,000"} simulated futures, never guessed by AI. Tap any figure to see how it’s worked out.
      </p>
    </section>
  );
}
