// "Can I afford it?" — POST /users/{id}/simulate {amount, date} -> PurchaseVerdict.
// Buying, waiting and not buying are all presented as fine answers; we never push buying.
import { useEffect, useMemo, useState } from "react";
import { HttpError, screensApi } from "../api";
import type { PurchaseVerdict } from "../types";
import {
  addDays, CalcLink, CalcPanel, dMid, dShort, ErrorState, Icon, Loading, Missing, money, todayIso,
  type CalcContent,
} from "./shared";
import "./AffordScreen.css";

/** Furthest date we check: the forecast horizon. Beyond it we say so rather than guess. */
const HORIZON_DAYS = 90;
const TIGHT_BELOW = 50;

const PRESETS: Record<string, { item: string; amount: number; inDays: number; quick: number[] }> = {
  sam: { item: "Trainers", amount: 60, inDays: 8, quick: [25, 60, 150, 400] },
  alex: { item: "Weekend in Edinburgh", amount: 450, inDays: 35, quick: [50, 150, 450, 900] },
  maya: { item: "Kids' winter coats", amount: 120, inDays: 14, quick: [20, 60, 120, 250] },
};
const DEFAULT_PRESET = { item: "", amount: 50, inDays: 0, quick: [25, 50, 100, 250] };

const NUM_LABELS: Record<string, string> = {
  price: "Purchase",
  safe_to_spend: "Safe to spend today",
  safe_after: "Safe to spend after buying",
};

type VState =
  | { s: "idle" }
  | { s: "loading" }
  | { s: "ok"; v: PurchaseVerdict; amount: number; date: string }
  | { s: "missing"; why: "horizon" | "data"; date: string }
  | { s: "error" };

export default function AffordScreen({ userId, onAskCoach }: {
  userId: string;
  /** Optional: open the coach with a prefilled question. The button is hidden when not given. */
  onAskCoach?: (message: string) => void;
}) {
  const today = todayIso();
  const maxDate = addDays(today, HORIZON_DAYS);
  const preset = PRESETS[userId] ?? DEFAULT_PRESET;

  const [item, setItem] = useState(preset.item);
  const [amountText, setAmountText] = useState(String(preset.amount));
  const [date, setDate] = useState(addDays(today, preset.inDays));
  const [vs, setVs] = useState<VState>({ s: "idle" });
  const [tick, setTick] = useState(0);
  const [numsOpen, setNumsOpen] = useState(false);
  const [calcOpen, setCalcOpen] = useState(false);

  // Reset inputs when the persona changes.
  useEffect(() => {
    const p = PRESETS[userId] ?? DEFAULT_PRESET;
    setItem(p.item); setAmountText(String(p.amount)); setDate(addDays(todayIso(), p.inDays));
  }, [userId]);

  const amount = Number(amountText);
  const amountValid = amountText.trim() !== "" && Number.isFinite(amount) && amount > 0;

  useEffect(() => {
    if (!amountValid || !date) { setVs({ s: "idle" }); return; }
    if (date < today) { setVs({ s: "idle" }); return; }
    if (date > maxDate) { setVs({ s: "missing", why: "horizon", date }); return; }
    const ctrl = new AbortController();
    setVs({ s: "loading" });
    const t = window.setTimeout(() => {
      screensApi.simulateOn(userId, amount, date, ctrl.signal).then(
        (v) => !ctrl.signal.aborted && setVs({ s: "ok", v, amount, date }),
        (e: unknown) => {
          if (ctrl.signal.aborted) return;
          if (e instanceof HttpError && (e.status === 503 || e.status === 422)) {
            setVs({ s: "missing", why: e.status === 422 ? "horizon" : "data", date });
          } else setVs({ s: "error" });
        },
      );
    }, 350);
    return () => { ctrl.abort(); window.clearTimeout(t); };
  }, [userId, amount, amountValid, date, today, maxDate, tick]);

  const label = (item.trim() || "this").replace(/^./, (c) => c.toLowerCase());

  return (
    <div className="fts fts-afford">
      <div className="fts-page">
        <div className="fts-head">
          <h1>Can I afford it?</h1>
          <p>Test a purchase before you make it. We'll show what it does to your balance. Buying, waiting and not buying are all fine answers.</p>
        </div>

        <div className="fta-cols">
          <section className="fts-card fta-form" aria-label="Purchase details">
            <label className="fta-field">What is it?
              <input value={item} onChange={(e) => setItem(e.target.value)} placeholder="For example, trainers" />
            </label>
            <label className="fta-field">How much?
              <span className="fta-amount">
                <span aria-hidden="true">£</span>
                <input type="number" min="0" step="0.01" inputMode="decimal" value={amountText}
                  onChange={(e) => setAmountText(e.target.value)} aria-describedby="fta-amt-hint" />
              </span>
            </label>
            {!amountValid && amountText !== "" && (
              <span id="fta-amt-hint" className="fta-hint"><Icon name="info" />Enter an amount above £0.</span>
            )}
            <div className="fta-quick" aria-label="Quick amounts" role="group">
              {preset.quick.map((q) => (
                <button key={q} type="button" onClick={() => setAmountText(String(q))} aria-pressed={amount === q}>£{q}</button>
              ))}
            </div>
            <label className="fta-field">When would you buy it?
              <input type="date" value={date} min={today} max={maxDate} onChange={(e) => setDate(e.target.value)} />
            </label>
            {onAskCoach && (
              <button type="button" className="fts-btn fts-btn--ghost"
                onClick={() => onAskCoach(`Can I afford ${money(amountValid ? amount : 0, amount % 1 ? 2 : 0)} for ${label}?`)}>
                <Icon name="chat-circle-text" />Talk it through with the coach
              </button>
            )}
          </section>

          <section className="fts-card fta-verdict" aria-live="polite" aria-label="Verdict">
            {vs.s === "idle" && (
              <div className="fts-state">
                <span className="fts-chip fts-chip--lav"><Icon name="scales" />Ready when you are</span>
                <h2 className="fts-state-title">Enter an amount and a date.</h2>
                <p className="fts-muted">We'll check it against your safe-to-spend and your forecast.</p>
              </div>
            )}
            {vs.s === "loading" && <Loading label="Checking your forecast" rows={4} />}
            {vs.s === "error" && <ErrorState onRetry={() => setTick((t) => t + 1)} />}
            {vs.s === "missing" && (
              <Missing title={`We don't have enough data for ${dMid(vs.date)}.`}>
                {vs.why === "horizon"
                  ? <>A forecast that far ahead would be a guess. We won't show a guessed number. Try a date before {dShort(maxDate)}.</>
                  : <>We can't build a forecast from your data yet. We won't show a guessed number.</>}
              </Missing>
            )}
            {vs.s === "ok" && (
              <VerdictBody v={vs.v} amount={vs.amount} date={vs.date} label={label}
                numsOpen={numsOpen} onToggleNums={() => setNumsOpen((o) => !o)} onCalc={() => setCalcOpen(true)} />
            )}
          </section>
        </div>
      </div>
      {calcOpen && vs.s === "ok" && <CalcPanel content={calcContent(vs.v, vs.amount, vs.date)} onClose={() => setCalcOpen(false)} />}
    </div>
  );
}

type St = "ok" | "tight" | "no";
const VS: Record<St, { label: string; icon: string }> = {
  ok: { label: "Affordable", icon: "check-circle" },
  tight: { label: "Affordable, but tight", icon: "warning" },
  no: { label: "Not yet", icon: "clock" },
};

function VerdictBody({ v, amount, date, label, numsOpen, onToggleNums, onCalc }: {
  v: PurchaseVerdict; amount: number; date: string; label: string;
  numsOpen: boolean; onToggleNums: () => void; onCalc: () => void;
}) {
  const st: St = !v.affordable ? "no" : v.safe_after < TIGHT_BELOW ? "tight" : "ok";
  const safeNow = v.numbers_used.safe_to_spend ?? v.safe_after + amount;
  const dp = (n: number) => (Number.isInteger(n) ? 0 : 2);

  const sentence = useMemo(() => {
    if (st === "ok") return `Buying ${label} on ${dShort(date)} still leaves ${money(v.safe_after)} safe to spend, with your pots and bills covered.`;
    if (st === "tight") return `You could buy ${label} on ${dShort(date)}, but it would leave only ${money(v.safe_after)} safe to spend. Waiting or skipping it are just as good.`;
    if (safeNow < 0) return `Your pots and upcoming bills already take more than your balance, so buying ${label} would leave you ${money(-v.safe_after)} short. Waiting or not buying keeps things from getting tighter.`;
    if (v.safe_after < 0) return `Buying ${label} would leave you ${money(-v.safe_after)} short of your safe-to-spend. Waiting or not buying keeps you covered.`;
    return `Buying ${label} on ${dShort(date)} would bring a low point forward in your forecast. Waiting or not buying keeps you covered.`;
  }, [st, label, date, v.safe_after, safeNow]);

  const better = v.better_date
    ? `A general sale is listed for ${dMid(v.better_date)}. Prices may be lower then, but that isn't guaranteed.`
    : st === "no"
      ? "We can't see a better date in the next 6 weeks. A new pot could help you save towards it."
      : `${dMid(date)} works as well as any date we can see.`;

  const nums: [string, string][] = [
    ["Purchase date", dMid(date)],
    ...Object.entries(v.numbers_used).map(([k, n]): [string, string] => [
      NUM_LABELS[k] ?? k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()),
      (k === "price" ? "−" : "") + money(k === "price" ? Math.abs(n) : n, dp(n)),
    ]),
  ];

  return (
    <>
      <div className={`fta-vhead fta-vhead--${st}`}>
        <span className={`fta-vchip fta-vchip--${st}`}><Icon name={VS[st].icon} />{VS[st].label}</span>
        <div className="fta-vfig">
          <span className="fts-money fta-vbig">{money(v.safe_after, dp(v.safe_after))}</span>
          <span className="fta-vcap">{v.safe_after < 0 ? "short after buying, once pots and bills are kept aside" : "safe to spend after buying"}</span>
        </div>
        <p className="fta-vsentence">{sentence}</p>
      </div>
      <div className="fta-vbody">
        <h3>Your options</h3>
        <div className="fta-options">
          <div className="fta-opt">
            <span className="fta-opt-t"><Icon name="shopping-bag" />Buy on {dShort(date)}</span>
            <span className="fts-money fta-opt-fig">{money(v.safe_after, dp(v.safe_after))}</span>
            <span className="fta-opt-x">{v.safe_after < 0 ? "short after pots and bills" : "left safe to spend"}</span>
          </div>
          <div className="fta-opt">
            <span className="fta-opt-t"><Icon name="hourglass" />{v.better_date ? `Wait until ${dShort(v.better_date)}` : "Wait"}</span>
            <span className="fts-money fta-opt-fig">{v.better_date ? "Sale day" : "No sale soon"}</span>
            <span className="fta-opt-x">{v.better_date ? "prices may be lower, not guaranteed" : "no general sale in the next 6 weeks"}</span>
          </div>
          <div className="fta-opt">
            <span className="fta-opt-t"><Icon name="hand-palm" />Don't buy it</span>
            <span className="fts-money fta-opt-fig">{money(safeNow, dp(safeNow))}</span>
            <span className="fta-opt-x">{safeNow < 0 ? "short after pots and bills, without buying" : "stays safe to spend"}</span>
          </div>
        </div>
        <div className="fta-better">
          <Icon name="calendar-check" />
          <div>
            <strong>Better date</strong>
            <span>{better}</span>
          </div>
        </div>
        <div className="fta-nums-bar">
          <button type="button" className="fta-nums-toggle" aria-expanded={numsOpen} aria-controls="fta-nums" onClick={onToggleNums}>
            <Icon name={numsOpen ? "caret-down" : "caret-right"} />Numbers used
          </button>
          <CalcLink onClick={onCalc} />
        </div>
        {numsOpen && (
          <table id="fta-nums" className="fta-nums">
            <tbody>
              {nums.map(([l, r]) => (
                <tr key={l}><td>{l}</td><td className="fts-money">{r}</td></tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

function calcContent(v: PurchaseVerdict, amount: number, date: string): CalcContent {
  const safe = v.numbers_used.safe_to_spend ?? v.safe_after + amount;
  return {
    title: "How we checked this purchase",
    steps: [
      `We start from today's safe to spend: ${money(safe, 2)}. That's your balance after keeping your pots and upcoming bills aside.`,
      `We take off the purchase: ${money(amount, 2)}. That leaves ${money(v.safe_after, 2)}.`,
      `We rerun your daily forecast with the purchase on ${dShort(date)}, to check it doesn't bring a low point forward.`,
      `If it leaves ${money(TIGHT_BELOW)} or more and adds no new risk, we say Affordable. Between £0 and ${money(TIGHT_BELOW)}, we say it's tight. Otherwise, we say Not yet.`,
    ],
    sources: "Your NatWest transactions, your pots, your regular bills, a calendar of general sale dates, and the amount and date you entered.",
    unknown: "Future prices. A sale date is a calendar event, not a promise of a lower price. One-off costs you haven't paid yet aren't in the forecast either.",
  };
}
