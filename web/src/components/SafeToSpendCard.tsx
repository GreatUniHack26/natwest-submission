import type { CSSProperties } from "react";
import { gbp } from "../format";
import type { SafeToSpend } from "../types";
import CountUp from "./CountUp";
import Icon from "./Icon";

/** The twin's money story: what's in the account vs what's actually free to spend. */
function MoneyStory({ data }: { data: SafeToSpend }) {
  const total = Math.max(data.balance, data.pots_total + data.upcoming_bills + Math.max(data.safe_amount, 0), 1);
  const share = (value: number) => `${Math.max(0, (value / total) * 100)}%`;
  const safe = Math.max(data.safe_amount, 0);

  return (
    <div className="money-story">
      <div className="money-story-bar" role="img"
        aria-label={`Balance ${gbp(data.balance)}: ${gbp(data.pots_total)} kept in pots, ${gbp(data.upcoming_bills)} for bills before payday, ${gbp(data.safe_amount)} safe to spend.`}>
        <span className="story-seg story-pots" style={{ "--w": share(data.pots_total), "--i": 0 } as CSSProperties} />
        <span className="story-seg story-bills" style={{ "--w": share(data.upcoming_bills), "--i": 1 } as CSSProperties} />
        <span className="story-seg story-safe" style={{ "--w": share(safe), "--i": 2 } as CSSProperties} />
      </div>
      <dl className="money-story-legend">
        <div><dt>In your account</dt><dd className="money">{gbp(data.balance)}</dd></div>
        <div><dt><span className="dot story-pots" aria-hidden="true" />Kept in pots</dt><dd className="money">−{gbp(data.pots_total)}</dd></div>
        <div><dt><span className="dot story-bills" aria-hidden="true" />Bills before payday</dt><dd className="money">−{gbp(data.upcoming_bills)}</dd></div>
        <div className="story-total"><dt><span className="dot story-safe" aria-hidden="true" />Safe to spend</dt><dd className="money">{gbp(data.safe_amount)}</dd></div>
      </dl>
    </div>
  );
}

export default function SafeToSpendCard({ data, demoPreview = false }: { data: SafeToSpend; demoPreview?: boolean }) {
  return (
    <>
      <div className="spending-summary">
        <p className="spending-amount money" aria-label={gbp(data.safe_amount)} data-negative={data.safe_amount < 0}>
          <CountUp value={data.safe_amount} />
        </p>
        <p className="spending-description">
          {data.safe_amount < 0
            ? "You’re short once bills and pots are set aside."
            : "You can spend this today. Bills and pots are already set aside."}
          {demoPreview && " Includes pots added in this demo."}
        </p>
      </div>
      <MoneyStory data={data} />
      {data.breakdown.length > 0 && (
        <details className="spending-details">
          <summary>How it’s worked out</summary>
          <dl className="spending-breakdown">
            {data.breakdown.map((item) => (
              <div key={item.label}>
                <dt>{item.label}</dt>
                <dd className="money">{gbp(item.amount)}</dd>
              </div>
            ))}
          </dl>
        </details>
      )}
      <a className="spending-link" href="#pots">
        <Icon name="pots" />
        See your pots
        <Icon name="chevron" />
      </a>
    </>
  );
}
