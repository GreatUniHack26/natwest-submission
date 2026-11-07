import { useEffect, useState, type CSSProperties } from "react";
import { api } from "../api";
import { dateLabel, gbp } from "../format";
import type { DepositIdeas as Ideas } from "../types";
import Icon from "./Icon";

const DEMO_TODAY = import.meta.env.VITE_DEMO_TODAY ?? "2026-11-07";
const DAY = 86_400_000;
const daysUntil = (iso: string) => Math.max(0, Math.round((Date.parse(iso) - Date.parse(DEMO_TODAY)) / DAY));
const pence = (value: number) => `£${value.toFixed(2)}`;

const storageKey = (userId: string) => `fintime-parked-${userId}`;
const PARKED_EVENT = "nat:parked";

function readParked(userId: string): string[] {
  try {
    const raw = localStorage.getItem(storageKey(userId));
    const list = raw ? JSON.parse(raw) : [];
    return Array.isArray(list) ? list.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

/** Which pots the viewer has parked in a saver (a simulation kept in this browser only). */
export function useParked(userId: string) {
  const [parked, setParked] = useState<string[]>(() => readParked(userId));

  useEffect(() => {
    setParked(readParked(userId));
    const sync = () => setParked(readParked(userId));
    window.addEventListener(PARKED_EVENT, sync);
    return () => window.removeEventListener(PARKED_EVENT, sync);
  }, [userId]);

  function toggle(pot: string) {
    const next = parked.includes(pot) ? parked.filter((p) => p !== pot) : [...parked, pot];
    setParked(next);
    try { localStorage.setItem(storageKey(userId), JSON.stringify(next)); } catch { /* storage unavailable */ }
    window.dispatchEvent(new Event(PARKED_EVENT));
  }

  return [parked, toggle] as const;
}

/** Short-term saver ideas for pots that won't be touched until a known date. */
export default function DepositIdeas({ userId, revision = 0 }: { userId: string; revision?: number }) {
  const [ideas, setIdeas] = useState<Ideas | null>(null);
  const [parked, toggle] = useParked(userId);
  const [justParked, setJustParked] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api.depositIdeas(userId, controller.signal).then(
      (result) => { if (!controller.signal.aborted) setIdeas(result); },
      () => { if (!controller.signal.aborted) setIdeas(null); },
    );
    return () => controller.abort();
  }, [userId, revision]);

  if (!ideas || ideas.ideas.length === 0) return null;
  const caution = ideas.ideas.find((idea) => idea.caution)?.caution;
  const hasDated = ideas.ideas.some((idea) => idea.withdraw_by);

  function onToggle(pot: string) {
    setJustParked(parked.includes(pot) ? null : pot);
    toggle(pot);
  }

  return (
    <section className="deposit-ideas" id="deposits" aria-labelledby={`deposit-${userId}`}>
      <div className="deposit-head">
        <h3 id={`deposit-${userId}`}>Put your pots to work</h3>
        <p className="deposit-total">
          <span>Could earn up to</span>
          <strong className="money">{pence(ideas.total_est_interest)}</strong>
        </p>
      </div>
      <p className="deposit-lede">
        Money saved for a set date can sit in an instant-access saver and earn interest until you need it.
      </p>
      <ul className="deposit-list">
        {ideas.ideas.map((idea, index) => {
          const isParked = parked.includes(idea.pot) && Boolean(idea.withdraw_by);
          const left = idea.withdraw_by ? daysUntil(idea.withdraw_by) : 0;
          const switchId = `park-${userId}-${index}`;
          return (
            <li key={idea.pot} data-parked={isParked} data-celebrate={isParked && justParked === idea.pot}
              style={{ "--i": index } as CSSProperties}>
              <div className="deposit-row">
                <div className="deposit-pot">
                  <strong>{idea.pot}</strong>
                  <p>
                    {gbp(idea.amount)}
                    {idea.due_date ? <>, needed <time dateTime={idea.due_date}>{dateLabel(idea.due_date)}</time></> : ", no set date"}
                  </p>
                </div>
                <p className="deposit-earn">
                  <strong className="money">+{pence(idea.est_interest)}</strong>
                  <span>{idea.interest_period === "per year" ? "a year" : "until it’s due"}</span>
                </p>
              </div>

              {idea.withdraw_by && (
                <div className="park-control">
                  <label htmlFor={switchId}>Park in a saver</label>
                  <button id={switchId} type="button" role="switch" aria-checked={isParked} className="park-switch"
                    onClick={() => onToggle(idea.pot)}>
                    <span className="visually-hidden">{idea.pot}</span>
                  </button>
                </div>
              )}

              {isParked && idea.withdraw_by && (
                <div className="parked" role="status">
                  <p className="parked-line">
                    <span className="parked-tick" aria-hidden="true"><Icon name="check" /></span>
                    <span>
                      Earning about <strong className="money">{pence(idea.est_interest)}</strong>. Back in your account by{" "}
                      <time dateTime={idea.withdraw_by}>{dateLabel(idea.withdraw_by)}</time>.
                    </span>
                  </p>
                  <div className="parked-track" aria-hidden="true"><span /></div>
                  <p className="parked-dates">
                    <span>Today</span>
                    <span>{left === 1 ? "1 day" : `${left} days`} to go</span>
                    <span>{dateLabel(idea.withdraw_by)}</span>
                  </p>
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {hasDated && <p className="deposit-sim"><Icon name="alerts" />Simulation only. No real money moves.</p>}
      {caution && <p className="deposit-caution"><Icon name="risk" />{caution}</p>}
      <p className="deposit-disclaimer">{ideas.disclaimer}</p>
    </section>
  );
}
