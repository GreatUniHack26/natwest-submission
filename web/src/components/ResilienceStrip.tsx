import { useEffect, useState } from "react";
import { api, apiUrl } from "../api";
import { gbp } from "../format";
import type { SpendingForecast, TwinSimulations } from "../types";
import { loadAlarms, type NatAlarm } from "./NatAlarms";
import { talkToNat } from "./NatLauncher";
import Row, { Chip } from "./Row";

interface Owed { total_est_value: number | null; items: unknown[] }

const pct = (value: number) => `${Math.round(value * 100)}%`;

/** Nat's top alarm as one row, then the key numbers as list rows. */
export default function ResilienceStrip({ userId }: { userId: string }) {
  const [month, setMonth] = useState<SpendingForecast | null>(null);
  const [sim, setSim] = useState<TwinSimulations | null>(null);
  const [owed, setOwed] = useState<Owed | null>(null);
  const [alarm, setAlarm] = useState<NatAlarm | null>(null);

  useEffect(() => {
    const c = new AbortController();
    const keep = <T,>(set: (v: T) => void) => (v: T) => { if (!c.signal.aborted) set(v); };
    api.spending(userId, c.signal).then(keep(setMonth), () => {});
    api.simulations(userId, c.signal).then(keep(setSim), () => {});
    fetch(apiUrl(`/users/${encodeURIComponent(userId)}/entitlements`), { signal: c.signal })
      .then((r) => (r.ok ? r.json() : null)).then(keep(setOwed), () => {});
    loadAlarms(userId, c.signal).then(keep((alarms: NatAlarm[]) => {
      setAlarm(alarms.find((a) => a.level === "act") ?? alarms.find((a) => a.level === "watch") ?? null);
    }), () => {});
    return () => c.abort();
  }, [userId]);

  const shortfall30 = sim?.chance_below_zero_within["30"];
  const owedCount = owed?.items.length ?? 0;
  const overBudget = month ? month.projected_month > month.typical_month * 1.1 : false;
  const risk = shortfall30 === undefined ? null : shortfall30 >= 0.5 ? "bad" : shortfall30 >= 0.2 ? "warn" : "good";

  return (
    <>
      {alarm && (
        <div className="block nat-alert" role={alarm.level === "act" ? "alert" : "status"}>
          <Row avatar="N" title={alarm.title} subtitle="Tap to talk it through" onClick={talkToNat} />
        </div>
      )}
      <section className="sect" aria-labelledby="glance-h">
        <div className="sect-head"><h2 id="glance-h">At a glance</h2></div>
        <ul className="rows block">
          <li>
            <Row icon="shopping-cart" title="Spending this month"
              subtitle={month ? `Usually ${gbp(Math.round(month.typical_month))}` : "Working it out"}
              value={month ? gbp(Math.round(month.projected_month)) : "…"}
              chip={month ? <Chip tone={overBudget ? "warn" : "good"}>{overBudget ? "High" : "On track"}</Chip> : undefined}
              href="#month" />
          </li>
          <li>
            <Row icon="umbrella" title="Chance of running short" subtitle="In the next 30 days"
              value={shortfall30 !== undefined ? pct(shortfall30) : "…"}
              chip={risk ? <Chip tone={risk}>{risk === "bad" ? "High" : risk === "warn" ? "Some" : "Low"}</Chip> : undefined}
              href="#forecast" />
          </li>
          <li>
            <Row icon="hourglass-medium" title="If your pay stopped" subtitle="How long your money lasts, not using pots"
              value={sim ? `${sim.runway_days_if_income_stops}${sim.runway_capped ? "+" : ""} days` : "…"}
              href="#forecast" />
          </li>
          <li>
            <Row icon="hand-coins" title="Money you could get"
              subtitle={owedCount ? `${owedCount} ${owedCount > 1 ? "things" : "thing"} to check` : "We keep checking for you"}
              value={owed?.total_est_value ? `£${Math.round(owed.total_est_value).toLocaleString("en-GB")}` : undefined}
              href="#tips" />
          </li>
        </ul>
      </section>
    </>
  );
}
