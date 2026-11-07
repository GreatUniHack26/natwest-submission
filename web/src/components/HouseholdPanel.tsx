import { useEffect, useId, useRef, useState, type CSSProperties } from "react";
import { api, householdApi } from "../api";
import { dateLabel, gbp } from "../format";
import type { Forecast, HouseholdMemberShare, SafeToSpend, User } from "../types";
import CountUp from "./CountUp";
import ForecastChart from "./ForecastChart";
import Icon from "./Icon";
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

/* ---------- Live household ---------- */

const DEFAULT_FAMILY_USER = import.meta.env.VITE_FAMILY_USER_ID || "maya";
const HORIZON_DAYS = 90;

type LiveData = { user: User; householdId: string; safe: SafeToSpend; forecast: Forecast };
type LiveState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "no-household"; user: User }
  | { status: "ready"; data: LiveData };

const titleCase = (id: string) => id.charAt(0).toUpperCase() + id.slice(1);
const possessive = (name: string) => `${name}’${name.endsWith("s") ? "" : "s"}`;
const plus = (amount: number) => (amount < 0 ? `−${gbp(-amount)}` : gbp(amount));

/** Turns labels like "maya: protected pot December rent" into per-member totals. */
export function parseMembers(breakdown: SafeToSpend["breakdown"]): HouseholdMemberShare[] {
  const members = new Map<string, HouseholdMemberShare>();
  const member = (id: string) => {
    let entry = members.get(id);
    if (!entry) {
      entry = { id, balance: 0, pots: 0, bills: 0, net: 0, notes: [], billItems: [] };
      members.set(id, entry);
    }
    return entry;
  };

  for (const { label, amount } of breakdown) {
    const match = /^([\w-]+): (.+)$/.exec(label);
    if (!match) continue;
    const [, id, rest] = match;
    const entry = member(id);
    let bill: RegExpExecArray | null;
    if (/^balance at close of /.test(rest)) entry.balance += amount;
    else if (/^protected pot /.test(rest)) entry.pots += amount;
    else if ((bill = /^unfunded (.+) on (\d{4}-\d{2}-\d{2})$/.exec(rest))) {
      entry.bills += amount;
      entry.billItems.push({ name: bill[1], date: bill[2], amount: -amount });
    } else if (/no certain income/.test(rest)) {
      entry.notes.push("No regular income found, so 90 days of bills are held back.");
    } else if (amount === 0) {
      entry.notes.push(rest.charAt(0).toUpperCase() + rest.slice(1) + ".");
    } else {
      entry.bills += amount;
    }
  }

  for (const entry of members.values()) entry.net = entry.balance + entry.pots + entry.bills;
  return [...members.values()].sort((a, b) => b.balance - a.balance);
}

/** First date the combined expected balance drops below zero. Prefers the engine's daily risk event. */
function firstBelowZero(forecast: Forecast): string | null {
  const event = forecast.risk_events.find((risk) => /expected balance falls below zero/i.test(risk.reason));
  if (event) return event.date;
  return forecast.points.find((point) => point.expected < 0)?.date ?? null;
}

function biggestRisk(safe: SafeToSpend, forecast: Forecast, members: HouseholdMemberShare[], belowZero: string | null) {
  if (belowZero) {
    const bills = members.flatMap((m) => m.billItems.filter((b) => b.date <= belowZero).map((b) => ({ ...b, who: m.id })))
      .sort((a, b) => b.amount - a.amount || a.date.localeCompare(b.date));
    const top = bills[0];
    return {
      level: "high" as const,
      text: `The household’s combined balance is expected to drop below zero around ${dateLabel(belowZero)}.`
        + (top ? ` The biggest bill before then is ${possessive(titleCase(top.who))} ${top.name}: ${gbp(top.amount)} on ${dateLabel(top.date)}.` : ""),
    };
  }
  if (safe.safe_amount < 0) {
    return {
      level: "medium" as const,
      text: `Bills and pots add up to ${gbp(-safe.safe_amount)} more than the household holds today.`,
    };
  }
  const risk = [...forecast.risk_events].sort((a, b) =>
    (a.severity === "high" ? 0 : a.severity === "medium" ? 1 : 2) - (b.severity === "high" ? 0 : b.severity === "medium" ? 1 : 2))[0];
  if (risk && risk.severity !== "low") return { level: risk.severity, text: `${risk.reason} (${dateLabel(risk.date)})` };
  return { level: "low" as const, text: `No big risks spotted in the next ${forecast.horizon_days} days.` };
}

function Sparkline({ forecast, belowZero }: { forecast: Forecast; belowZero: string | null }) {
  const clipId = useId().replace(/:/g, "");
  const points = forecast.points;
  if (points.length < 2) return null;

  const W = 400, H = 120, PAD = 8;
  const t0 = Date.parse(points[0].date);
  const t1 = Date.parse(points[points.length - 1].date);
  const lo = Math.min(0, ...points.map((p) => p.low));
  const hi = Math.max(0, ...points.map((p) => p.high));
  const x = (date: string) => PAD + ((Date.parse(date) - t0) / Math.max(1, t1 - t0)) * (W - PAD * 2);
  const y = (value: number) => PAD + ((hi - value) / Math.max(1, hi - lo)) * (H - PAD * 2);
  const zeroY = y(0);

  const line = points.map((p, i) => `${i ? "L" : "M"}${x(p.date).toFixed(1)},${y(p.expected).toFixed(1)}`).join(" ");
  const band = points.map((p, i) => `${i ? "L" : "M"}${x(p.date).toFixed(1)},${y(p.high).toFixed(1)}`).join(" ")
    + " " + [...points].reverse().map((p) => `L${x(p.date).toFixed(1)},${y(p.low).toFixed(1)}`).join(" ") + " Z";
  const markerX = belowZero ? Math.min(W - PAD, Math.max(PAD, x(belowZero))) : null;
  const last = points[points.length - 1];

  const summary = `Combined expected balance from ${gbp(points[0].expected)} today to ${plus(last.expected)} on ${dateLabel(last.date)}.`
    + (belowZero ? ` Drops below zero around ${dateLabel(belowZero)}.` : " Stays above zero.");

  return (
    <figure className="hh-spark">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={summary}>
        <defs>
          <clipPath id={`${clipId}-below`}><rect x="0" y={zeroY} width={W} height={Math.max(0, H - zeroY)} /></clipPath>
        </defs>
        <path className="hh-spark-band" d={band} />
        <line className="hh-spark-zero" x1={PAD} x2={W - PAD} y1={zeroY} y2={zeroY} />
        <path className="hh-spark-line" d={line} pathLength={1} />
        <path className="hh-spark-line hh-spark-negative" d={line} pathLength={1} clipPath={`url(#${clipId}-below)`} />
        {markerX !== null && (
          <g className="hh-spark-marker">
            <line x1={markerX} x2={markerX} y1={PAD} y2={H - PAD} />
            <circle cx={markerX} cy={zeroY} r={4.5} />
          </g>
        )}
      </svg>
      <figcaption className="hh-spark-axis" aria-hidden="true">
        <span>Today <strong className="money">{gbp(Math.round(points[0].expected))}</strong></span>
        {belowZero && <span className="hh-spark-flag"><Icon name="risk" /> Below £0 from {dateLabel(belowZero)}</span>}
        <span>{dateLabel(last.date)} <strong className="money">{plus(Math.round(last.expected))}</strong></span>
      </figcaption>
    </figure>
  );
}

const MISSING_DATA = "We don’t have enough data. We won’t show a guessed number.";

function initials(id: string) {
  return id.slice(0, 1).toUpperCase();
}

function HouseholdLive({ data }: { data: LiveData }) {
  const { safe, forecast } = data;
  const members = parseMembers(safe.breakdown);
  if (members.length === 0 || forecast.points.length < 2) {
    return <p className="panel-empty hh-missing">{MISSING_DATA}</p>;
  }

  const belowZero = firstBelowZero(forecast);
  const risk = biggestRisk(safe, forecast, members, belowZero);
  const names = members.map((m) => titleCase(m.id));
  const positiveBalance = members.reduce((sum, m) => sum + Math.max(0, m.balance), 0);
  const short = safe.safe_amount < 0;
  const riskLabel = { high: "High", medium: "Medium", low: "Low" }[risk.level];

  return (
    <>
      <p className="household-description hh-intro">
        {names.join(" and ")}: both incomes, both sets of bills, one plan. Each person’s money stays in their own account.
      </p>

      <section className="hh-hero hh-rise" aria-labelledby="hh-hero-title">
        <div className="hh-hero-main">
          <h3 id="hh-hero-title" className="hh-hero-label">Safe to spend together</h3>
          <p className="hh-hero-amount money" aria-label={gbp(safe.safe_amount)}>
            <CountUp value={safe.safe_amount} />
          </p>
          {short && (
            <span className="hh-chip hh-chip-danger">
              <Icon name="risk" /> Shortfall: bills and pots are more than you hold
            </span>
          )}
        </div>
        <div className="hh-hero-side">
          <p className="money">
            Balance {gbp(safe.balance)} − pots {gbp(safe.pots_total)} − bills {gbp(safe.upcoming_bills)}
          </p>
          <details className="hh-calc">
            <summary>How was this calculated?</summary>
            <ol>
              <li>We add up {names.join(" and ")}’s balances: <strong className="money">{gbp(safe.balance)}</strong>.</li>
              <li>We keep aside money in pots: <strong className="money">{gbp(safe.pots_total)}</strong>.</li>
              <li>We take off bills due before each person’s next income: <strong className="money">{gbp(safe.upcoming_bills)}</strong>.</li>
              <li>What’s left to spend together: <strong className="money">{gbp(safe.safe_amount)}</strong>.</li>
            </ol>
          </details>
        </div>
      </section>

      <div className="hh-grid">
        <section className="hh-card hh-rise" style={{ "--i": 1 } as CSSProperties} aria-labelledby="hh-forecast-title">
          <h3 id="hh-forecast-title">Combined balance, next {forecast.horizon_days} days</h3>
          <Sparkline forecast={forecast} belowZero={belowZero} />
        </section>

        <article className="hh-card hh-risk hh-rise" data-level={risk.level} style={{ "--i": 2 } as CSSProperties}
          aria-labelledby="hh-risk-title">
          <div className="hh-risk-head">
            <span className="hh-chip hh-sev" data-level={risk.level}>
              <Icon name={risk.level === "low" ? "alerts" : "risk"} /> {riskLabel}
            </span>
            <h3 id="hh-risk-title">Biggest risk</h3>
          </div>
          <p className="hh-risk-text">{risk.text}</p>
          {belowZero && (
            <a className="hh-pill-link" href="#forecast">See the forecast <Icon name="chevron" /></a>
          )}
        </article>
      </div>

      <div className="hh-members" role="list" aria-label="Household members">
        {members.map((m, i) => {
          const share = positiveBalance > 0 ? Math.max(0, m.balance) / positiveBalance : 0;
          const pct = Math.round(share * 100);
          return (
            <section key={m.id} role="listitem" className="hh-card hh-member hh-rise" data-index={i}
              style={{ "--i": i + 3 } as CSSProperties} aria-labelledby={`hh-member-${m.id}`}>
              <div className="hh-member-head">
                <span className="hh-avatar" data-alt={i % 2 === 1} aria-hidden="true">{initials(m.id)}</span>
                <div>
                  <h3 id={`hh-member-${m.id}`}>{titleCase(m.id)}</h3>
                  <p>Brings {pct}% of the combined balance</p>
                </div>
              </div>
              <div className="hh-share" aria-hidden="true">
                <span style={{ "--w": `${pct}%` } as CSSProperties} />
              </div>
              <div>
                <p className="hh-member-label">Personal safe to spend</p>
                <p className="hh-member-amount money" data-negative={m.net < 0}>{plus(m.net)}</p>
              </div>
              <dl className="hh-rows">
                <div><dt>Balance</dt><dd className="money">{gbp(m.balance)}</dd></div>
                <div><dt>Own pots</dt><dd className="money">{plus(m.pots)}</dd></div>
                <div><dt>Bills before next income</dt><dd className="money">{plus(m.bills)}</dd></div>
              </dl>
              {m.notes.map((note) => (
                <p key={note} className="hh-member-note"><Icon name="alerts" /> {note}</p>
              ))}
            </section>
          );
        })}
      </div>
    </>
  );
}

function useHousehold(userId: string, enabled: boolean) {
  const [state, setState] = useState<LiveState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    const { signal } = controller;
    setState((previous) => (previous.status === "ready" ? previous : { status: "loading" }));

    (async () => {
      const user = await api.user(userId, signal);
      if (!user.household_id) return { status: "no-household", user } as const;
      const [safe, forecast] = await Promise.all([
        householdApi.safeToSpend(user.household_id, signal),
        householdApi.forecast(user.household_id, HORIZON_DAYS, signal),
      ]);
      return { status: "ready", data: { user, householdId: user.household_id, safe, forecast } } as const;
    })().then(
      (next) => { if (!signal.aborted) setState(next); },
      () => { if (!signal.aborted) setState({ status: "error" }); },
    );

    return () => controller.abort();
  }, [userId, enabled, attempt]);

  return { state, retry: () => setAttempt((n) => n + 1) };
}

export default function HouseholdPanel({ demo, userId = DEFAULT_FAMILY_USER }: { demo: boolean; userId?: string }) {
  const { state, retry } = useHousehold(userId, !demo);
  const region = useRef<HTMLElement>(null);

  function retryPanel() {
    region.current?.focus({ preventScroll: true });
    retry();
  }

  return (
    <section ref={region} className="panel household-panel" id="household" tabIndex={-1} aria-labelledby="household-title">
      <h2 id="household-title">Household</h2>
      {demo ? <HouseholdDemo /> : state.status === "ready" ? <HouseholdLive data={state.data} /> : state.status === "loading" ? (
        <div className="panel-loading" role="status">
          <span>Loading household…</span>
          <span className="skeleton" aria-hidden="true" />
          <span className="skeleton" aria-hidden="true" />
        </div>
      ) : state.status === "no-household" ? (
        <div className="hh-empty">
          <span className="hh-avatar" aria-hidden="true"><Icon name="household" /></span>
          <h3>Household view is for shared money</h3>
          <p>{state.user.name} manages money alone, so there’s nothing to combine.</p>
        </div>
      ) : (
        <div className="panel-error">
          <p role="alert">Couldn’t load household.</p>
          <button className="secondary-button" type="button" onClick={retryPanel}>
            Try again<span className="visually-hidden"> to load household</span>
          </button>
        </div>
      )}
    </section>
  );
}
