import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent } from "react";
import { api } from "../api";
import { dateLabel, gbp } from "../format";
import type { Timeline, TimelineEvent } from "../types";

const HEIGHT = 300;
const PAD = { top: 18, right: 14, bottom: 44, left: 52 };
const DEMO_TODAY = import.meta.env.VITE_DEMO_TODAY ?? "2026-11-07";

function addDays(iso: string, days: number) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

interface Preset { id: string; label: string; overrides: Record<string, unknown> }
const PRESETS: Preset[] = [
  { id: "trip", label: "Holiday £1,600 in 4 weeks", overrides: { extra_one_off: { amount: 1600, date: addDays(DEMO_TODAY, 28) } } },
  { id: "cut", label: "Hours cut by 30%", overrides: { income_multiplier: 0.7 } },
  { id: "bill", label: "New £100/month bill", overrides: { extra_monthly_cost: 100 } },
];

const money = (v: number) => gbp(Math.round(v));
const pct = (v: number) => `${Math.round(v * 100)}%`;

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(640);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new ResizeObserver(([entry]) => setWidth(Math.max(280, Math.round(entry.contentRect.width))));
    obs.observe(el);
    return () => obs.disconnect();
  }, []);
  return [ref, width] as const;
}

export default function TimeTravel({ userId, revision = 0 }: { userId: string; revision?: number }) {
  const [data, setData] = useState<Timeline | null>(null);
  const [failed, setFailed] = useState(false);
  const [preset, setPreset] = useState<Preset | null>(null);
  const [custom, setCustom] = useState({ amount: "", date: addDays(DEMO_TODAY, 28) });
  const [cursor, setCursor] = useState(0);
  const [wrap, width] = useWidth<HTMLDivElement>();
  const gradientId = useId().replace(/:/g, "");

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    api.timeline(userId, 90, preset?.overrides ?? {}, controller.signal).then(
      (result) => { if (!controller.signal.aborted) setData(result); },
      () => { if (!controller.signal.aborted) setFailed(true); },
    );
    return () => controller.abort();
  }, [userId, preset, revision]);

  useEffect(() => {
    // Jump the scrubber to the first moment that matters.
    if (!data) return;
    const target = data.scenario?.first_below_zero ?? data.first_below_zero;
    const index = target ? data.days.findIndex((d) => d.date === target) : -1;
    setCursor(index > 0 ? index : Math.min(28, data.days.length - 1));
  }, [data]);

  const geo = useMemo(() => {
    if (!data) return null;
    const innerW = width - PAD.left - PAD.right;
    const innerH = HEIGHT - PAD.top - PAD.bottom;
    const values = data.days.flatMap((d) => [d.p10, d.p90, d.protected, 0]).concat(data.scenario?.expected ?? []);
    let lo = Math.min(...values);
    let hi = Math.max(...values);
    const span = Math.max(hi - lo, 200);
    lo -= span * 0.08;
    hi += span * 0.08;
    const x = (i: number) => PAD.left + (i / (data.days.length - 1)) * innerW;
    const y = (v: number) => PAD.top + (1 - (v - lo) / (hi - lo)) * innerH;
    const line = (vals: number[]) => vals.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
    const fan = `${line(data.days.map((d) => d.p90))}${data.days.map((d, i) => `L${x(data.days.length - 1 - i).toFixed(1)},${y(data.days[data.days.length - 1 - i].p10).toFixed(1)}`).join("")}Z`;
    const step = data.days.map((d, i) => `${i ? `L${x(i).toFixed(1)},${y(data.days[i - 1].protected).toFixed(1)}L` : "M"}${x(i).toFixed(1)},${y(d.protected).toFixed(1)}`).join("");
    const ticks = niceTicks(lo, hi, 4);
    const months = data.days.map((d, i) => ({ d, i })).filter(({ d, i }) => i === 0 || d.date.endsWith("-01"));
    return { innerW, innerH, x, y, lo, hi, fan, median: line(data.days.map((d) => d.p50)), step,
      scenario: data.scenario ? line(data.scenario.expected) : null, ticks, months };
  }, [data, width]);

  const eventsByDay = useMemo(() => {
    const map = new Map<string, TimelineEvent[]>();
    data?.events.forEach((e) => map.set(e.date, [...(map.get(e.date) ?? []), e]));
    return map;
  }, [data]);

  if (failed && !data) return <p className="panel-empty">Couldn’t run the time-travel simulation.</p>;
  if (!data || !geo) return <div className="panel-loading" role="status"><span>Simulating your next 90 days…</span><span className="skeleton" /></div>;

  const day = data.days[Math.min(cursor, data.days.length - 1)];
  const sinceToday = data.events.filter((e) => e.date > data.days[0].date && e.date <= day.date && e.kind !== "pot");
  const paidIn = sinceToday.filter((e) => e.amount > 0).reduce((s, e) => s + e.amount, 0);
  const paidOut = sinceToday.filter((e) => e.amount < 0).reduce((s, e) => s + e.amount, 0);
  const todays = eventsByDay.get(day.date) ?? [];
  const nextEvent = data.events.find((e) => e.date > day.date);
  const scenarioValue = data.scenario?.expected[cursor];
  const cx = geo.x(cursor);
  const usingPots = day.p50 < day.protected && day.protected > 0;

  function scrub(event: PointerEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = (event.clientX - rect.left - PAD.left) / (rect.width - PAD.left - PAD.right);
    setCursor(Math.round(Math.min(1, Math.max(0, ratio)) * (data!.days.length - 1)));
  }

  function applyCustom() {
    const amount = Number(custom.amount);
    if (!Number.isFinite(amount) || amount <= 0) return;
    setPreset({ id: "custom", label: `${gbp(amount)} on ${dateLabel(custom.date)}`, overrides: { extra_one_off: { amount, date: custom.date } } });
  }

  return (
    <div className="tt">
      <div className="tt-story" aria-live="polite">
        <div>
          <p className="tt-date"><time dateTime={day.date}>{dateLabel(day.date)}</time>{cursor === 0 ? " · today" : ` · in ${cursor} days`}</p>
          <p className="tt-amount money" data-negative={day.p50 < 0}>{money(day.p50)}</p>
          <p className="tt-range">8 in 10 futures: {money(day.p10)} to {money(day.p90)}</p>
        </div>
        <div className="tt-facts">
          <p className="tt-chance" data-level={day.chance_below_zero >= 0.5 ? "high" : day.chance_below_zero >= 0.2 ? "medium" : "low"}>
            <strong>{pct(day.chance_below_zero)}</strong> chance below £0
          </p>
          {usingPots && <p className="tt-flag">Likely dipping into pot money</p>}
          {scenarioValue !== undefined && preset && (
            <p className="tt-what-if-value">What-if: <strong className="money">{money(scenarioValue)}</strong></p>
          )}
          <p className="tt-since">
            Since today: <span className="tt-in">+{money(paidIn)}</span> pay, <span className="tt-out">{money(paidOut)}</span> bills
          </p>
          {todays.length > 0
            ? <p className="tt-today">{todays.map((e) => `${e.label} ${e.amount > 0 ? "+" : ""}${money(e.amount)}`).join(" · ")}</p>
            : nextEvent && <p className="tt-next">Next: {nextEvent.label} {dateLabel(nextEvent.date)}</p>}
        </div>
      </div>

      <div className="tt-chart" ref={wrap}>
        <svg width={width} height={HEIGHT} viewBox={`0 0 ${width} ${HEIGHT}`} role="img"
          aria-label={`Balance over the next ${data.horizon_days} days. ${data.first_below_zero ? `Likely below zero from ${dateLabel(data.first_below_zero)}.` : "Stays above zero in most futures."}`}
          onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); scrub(e); }}
          onPointerMove={(e) => { if (e.buttons || e.pointerType === "mouse") scrub(e); }}>
          <defs>
            <linearGradient id={`fan-${gradientId}`} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="var(--tint)" stopOpacity="0.28" />
              <stop offset="100%" stopColor="var(--tint)" stopOpacity="0.08" />
            </linearGradient>
            <clipPath id={`below-${gradientId}`}><rect x={PAD.left} y={geo.y(0)} width={geo.innerW} height={Math.max(0, HEIGHT - PAD.bottom - geo.y(0))} /></clipPath>
          </defs>
          {geo.ticks.map((t) => (
            <g key={t} className="tt-grid">
              <line x1={PAD.left} x2={width - PAD.right} y1={geo.y(t)} y2={geo.y(t)} />
              <text x={PAD.left - 8} y={geo.y(t) + 4} textAnchor="end">{t === 0 ? "£0" : `${t < 0 ? "−" : ""}£${Math.abs(t) >= 1000 ? `${Math.abs(t) / 1000}k` : Math.abs(t)}`}</text>
            </g>
          ))}
          <rect className="tt-danger" x={PAD.left} y={geo.y(0)} width={geo.innerW} height={Math.max(0, HEIGHT - PAD.bottom - geo.y(0))} />
          <line className="tt-zero" x1={PAD.left} x2={width - PAD.right} y1={geo.y(0)} y2={geo.y(0)} />
          <path className="tt-fan" d={geo.fan} fill={`url(#fan-${gradientId})`} />
          <path className="tt-pots" d={geo.step} />
          {geo.scenario && <path className="tt-scenario" d={geo.scenario} pathLength={1} key={preset?.id} />}
          <path className="tt-median" d={geo.median} pathLength={1} key={`m-${userId}`} />
          <path className="tt-median tt-median-danger" d={geo.median} pathLength={1} clipPath={`url(#below-${gradientId})`} key={`d-${userId}`} />
          {geo.months.map(({ d, i }) => (
            <text key={d.date} className="tt-month" x={geo.x(i)} y={HEIGHT - 8} textAnchor={i === 0 ? "start" : "middle"}>
              {i === 0 ? "Today" : new Date(`${d.date}T00:00:00Z`).toLocaleString("en-GB", { month: "short", timeZone: "UTC" })}
            </text>
          ))}
          {[...eventsByDay.entries()].map(([date, events]) => {
            const i = data.days.findIndex((d) => d.date === date);
            if (i < 0) return null;
            const kind = events.some((e) => e.kind === "pot") ? "pot" : events.some((e) => e.kind === "income") ? "income" : "bill";
            const big = events.some((e) => Math.abs(e.amount) >= 200);
            return <circle key={date} className={`tt-event tt-event-${kind}`} cx={geo.x(i)} cy={HEIGHT - PAD.bottom + 14} r={big ? 5 : 3.2}
              style={{ "--i": i } as CSSProperties}><title>{events.map((e) => `${e.label} ${money(e.amount)}`).join(", ")} · {dateLabel(date)}</title></circle>;
          })}
          {data.risks.filter((r) => r.severity === "high").map((r) => {
            const i = data.days.findIndex((d) => d.date === r.date);
            return i < 0 ? null : <circle key={r.date} className="tt-risk-pulse" cx={geo.x(i)} cy={geo.y(data.days[i].p50)} r={6} />;
          })}
          <line className="tt-cursor" x1={cx} x2={cx} y1={PAD.top} y2={HEIGHT - PAD.bottom + 4} />
          <circle className="tt-cursor-dot" cx={cx} cy={geo.y(day.p50)} r={5.5} />
          {scenarioValue !== undefined && <circle className="tt-cursor-scenario" cx={cx} cy={geo.y(scenarioValue)} r={4.5} />}
        </svg>
      </div>

      <label className="tt-slider">
        <span className="visually-hidden">Travel to a date</span>
        <input type="range" min={0} max={data.days.length - 1} value={cursor}
          aria-valuetext={`${dateLabel(day.date)}: likely ${money(day.p50)}, ${pct(day.chance_below_zero)} chance below zero`}
          onChange={(e) => setCursor(Number(e.target.value))} />
      </label>

      <ul className="tt-legend" aria-label="Chart legend">
        <li><i className="lg-median" />Most likely</li>
        <li><i className="lg-fan" />8 in 10 futures</li>
        <li><i className="lg-pots" />Protected in pots</li>
        <li><i className="lg-income" />Pay</li>
        <li><i className="lg-bill" />Bill</li>
        {preset && <li><i className="lg-scenario" />What-if</li>}
      </ul>

      <div className="tt-whatif">
        <p className="tt-whatif-title">Change the future</p>
        <div className="tt-chips" role="group" aria-label="What-if scenarios">
          {PRESETS.map((p) => (
            <button key={p.id} type="button" className="tt-chip" aria-pressed={preset?.id === p.id}
              onClick={() => setPreset(preset?.id === p.id ? null : p)}>{p.label}</button>
          ))}
        </div>
        <form className="tt-custom" onSubmit={(e) => { e.preventDefault(); applyCustom(); }}>
          <label>One-off cost (£)<input inputMode="decimal" value={custom.amount} placeholder="e.g. 400"
            onChange={(e) => setCustom({ ...custom, amount: e.target.value })} /></label>
          <label>On<input type="date" value={custom.date} min={addDays(DEMO_TODAY, 1)} max={addDays(DEMO_TODAY, 90)}
            onChange={(e) => setCustom({ ...custom, date: e.target.value })} /></label>
          <button type="submit" className="tt-chip tt-try">Try it</button>
        </form>
        {preset && data.scenario && (
          <p className="tt-whatif-result" role="status">
            <strong>{preset.label}:</strong>{" "}
            {data.scenario.first_below_zero
              ? <>below £0 from <strong>{dateLabel(data.scenario.first_below_zero)}</strong>{data.first_below_zero && data.first_below_zero !== data.scenario.first_below_zero ? ` (was ${dateLabel(data.first_below_zero)})` : ""}</>
              : "you stay above £0 in the expected path"}
            {" · "}ends {money(Math.abs(data.scenario.end_difference))} {data.scenario.end_difference < 0 ? "lower" : "higher"}.
            <button type="button" className="tt-clear" onClick={() => setPreset(null)}>Clear</button>
          </p>
        )}
      </div>
    </div>
  );
}

function niceTicks(lo: number, hi: number, count: number) {
  const raw = (hi - lo) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const ticks = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi; t += step) ticks.push(Math.round(t));
  if (!ticks.includes(0) && lo < 0 && hi > 0) ticks.push(0);
  return ticks.sort((a, b) => a - b);
}
