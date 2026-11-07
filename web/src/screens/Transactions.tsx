// Transactions grouped by day, with a Need/Want chip that saves via
// PATCH /users/{id}/transactions/{tx_id} {category, kind}.
import { useMemo, useState } from "react";
import { screensApi } from "../api";
import type { Kind, Transaction } from "../types";
import { addDays, cap, dLong, Icon, money, StateSwitch, useLoad, Missing } from "./shared";
import "./Transactions.css";

type Filter = "all" | "need" | "want" | "income";
const FILTERS: [Filter, string][] = [["all", "All"], ["need", "Needs"], ["want", "Wants"], ["income", "Income"]];
const PAGE_DAYS = 30;
const TOTAL_DAYS = 7;

const ICON: Record<string, string> = {
  groceries: "shopping-cart", "eating out": "hamburger", takeaway: "hamburger", transport: "bus",
  subscriptions: "music-notes", income: "arrow-down-left", clothing: "t-shirt", clothes: "t-shirt",
  phone: "device-mobile", shopping: "package", energy: "lightning", bills: "receipt", housing: "house-line",
  education: "graduation-cap", fitness: "barbell", fuel: "gas-pump", childcare: "baby",
};

export default function Transactions({ userId }: { userId: string }) {
  const [state, retry, update] = useLoad<Transaction[]>(
    (signal) => screensApi.transactions(userId, {}, signal),
    [userId],
    { isMissing: (txs) => txs.length === 0 },
  );
  const [filter, setFilter] = useState<Filter>("all");
  const [days, setDays] = useState(PAGE_DAYS);
  const [edited, setEdited] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState<Set<string>>(new Set());
  const [failed, setFailed] = useState<{ id: string; kind: Kind } | null>(null);

  async function setKind(tx: Transaction, kind: Kind) {
    setFailed(null);
    setSaving((s) => new Set(s).add(tx.id));
    update((list) => list.map((t) => (t.id === tx.id ? { ...t, kind } : t)));
    try {
      const saved = await screensApi.overrideTransaction(userId, tx.id, { category: tx.category, kind });
      update((list) => list.map((t) => (t.id === tx.id ? saved : t)));
      setEdited((s) => new Set(s).add(tx.id));
    } catch {
      update((list) => list.map((t) => (t.id === tx.id ? { ...t, kind: tx.kind } : t)));
      setFailed({ id: tx.id, kind });
    } finally {
      setSaving((s) => { const n = new Set(s); n.delete(tx.id); return n; });
    }
  }

  return (
    <div className="fts fts-tx">
      <div className="fts-page fts-page--narrow">
        <div className="fts-head">
          <h1>Transactions</h1>
          <p>Tap Need or Want to correct a label. FinTime learns from your changes.</p>
        </div>
        <StateSwitch state={state} onRetry={retry} loadingLabel="Loading transactions" rows={6}
          missing={<div className="fts-card"><Missing title="We don't have any transactions for you yet.">
            We won't show a guessed number. Once payments come in, they'll appear here.</Missing></div>}>
          {(txs) => (
            <TxList txs={txs} filter={filter} setFilter={setFilter} days={days} onMore={() => setDays((d) => d + PAGE_DAYS)}
              edited={edited} saving={saving} failed={failed} onSetKind={setKind} />
          )}
        </StateSwitch>
      </div>
    </div>
  );
}

function TxList({ txs, filter, setFilter, days, onMore, edited, saving, failed, onSetKind }: {
  txs: Transaction[]; filter: Filter; setFilter: (f: Filter) => void; days: number; onMore: () => void;
  edited: Set<string>; saving: Set<string>; failed: { id: string; kind: Kind } | null;
  onSetKind: (tx: Transaction, kind: Kind) => void;
}) {
  const sorted = useMemo(() => [...txs].sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : b.id.localeCompare(a.id))), [txs]);
  const latest = sorted[0]?.date ?? "";
  const earliest = sorted[sorted.length - 1]?.date ?? "";
  const from = addDays(latest, -(days - 1));
  const weekFrom = addDays(latest, -(TOTAL_DAYS - 1));

  const { groups, needs, wants } = useMemo(() => {
    let needs = 0, wants = 0;
    const groups: { date: string; items: Transaction[] }[] = [];
    for (const t of sorted) {
      if (t.date >= weekFrom && t.amount < 0) {
        if (t.kind === "need") needs -= t.amount;
        if (t.kind === "want") wants -= t.amount;
      }
      if (t.date < from) continue;
      if (filter !== "all" && t.kind !== filter) continue;
      const last = groups[groups.length - 1];
      if (last && last.date === t.date) last.items.push(t);
      else groups.push({ date: t.date, items: [t] });
    }
    return { groups, needs, wants };
  }, [sorted, filter, from, weekFrom]);

  return (
    <>
      <div className="ftt-bar">
        <div className="fts-seg" role="radiogroup" aria-label="Filter">
          {FILTERS.map(([id, label]) => (
            <button key={id} type="button" role="radio" aria-checked={filter === id} onClick={() => setFilter(id)}>{label}</button>
          ))}
        </div>
        <div className="ftt-totals">
          <span>Needs <strong className="fts-money">{money(needs, 2)}</strong></span>
          <span>Wants <strong className="fts-money">{money(wants, 2)}</strong></span>
          <span>last {TOTAL_DAYS} days</span>
        </div>
      </div>

      {groups.length === 0 && (
        <div className="fts-card ftt-empty">
          <Icon name="receipt" />
          <strong>Nothing here yet</strong>
          <span>No transactions match this filter in the last {days} days.</span>
        </div>
      )}

      {groups.map((g) => (
        <section key={g.date} className="ftt-group" aria-labelledby={`ftt-d-${g.date}`}>
          <h2 id={`ftt-d-${g.date}`}>{dLong(g.date)}</h2>
          <ul className="fts-card ftt-rows">
            {g.items.map((t) => (
              <TxRow key={t.id} t={t} edited={edited.has(t.id)} saving={saving.has(t.id)}
                failedKind={failed?.id === t.id ? failed.kind : null} onSetKind={onSetKind} />
            ))}
          </ul>
        </section>
      ))}

      {from > earliest && (
        <button type="button" className="fts-btn fts-btn--ghost ftt-more" onClick={onMore}>
          <Icon name="clock-counter-clockwise" />Show earlier transactions
        </button>
      )}
    </>
  );
}

function TxRow({ t, edited, saving, failedKind, onSetKind }: {
  t: Transaction; edited: boolean; saving: boolean; failedKind: Kind | null;
  onSetKind: (tx: Transaction, kind: Kind) => void;
}) {
  const isIncome = t.kind === "income";
  const isNeed = t.kind === "need";
  const next: Kind = isNeed ? "want" : "need";
  const label = isNeed ? "Need" : "Want";
  return (
    <li className="ftt-row">
      <span className="fts-bubble ftt-ic"><Icon name={ICON[t.category.toLowerCase()] ?? "receipt"} /></span>
      <div className="ftt-main">
        <span className="ftt-m">{t.merchant}</span>
        <span className="ftt-sub">{cap(t.category)}</span>
      </div>
      {edited && <span className="ftt-edited"><Icon name="pencil-simple" />Edited</span>}
      {isIncome ? (
        <span className="ftt-chip ftt-chip--income"><Icon name="arrow-down-left" />Income</span>
      ) : (
        <button type="button" className={`ftt-chip ftt-chip--${t.kind}`} disabled={saving}
          aria-label={`${t.merchant}, labelled ${label}. Change to ${next === "need" ? "Need" : "Want"}`}
          onClick={() => onSetKind(t, next)}>
          <Icon name={isNeed ? "house" : "sparkle"} />{label}<Icon name="arrows-down-up" className="ftt-swap" />
        </button>
      )}
      <span className={`fts-money ftt-amt${t.amount > 0 ? " is-in" : ""}`}>
        {t.amount > 0 ? "+" : "−"}£{Math.abs(t.amount).toFixed(2)}
      </span>
      {failedKind && (
        <div className="ftt-fail" role="alert">
          <Icon name="warning-circle" />We couldn't save that change.
          <button type="button" className="fts-link" onClick={() => onSetKind(t, failedKind)}>Try again</button>
        </div>
      )}
    </li>
  );
}
