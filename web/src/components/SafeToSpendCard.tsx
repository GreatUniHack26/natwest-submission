import { gbp } from "../format";
import type { SafeToSpend } from "../types";
import Icon from "./Icon";

export default function SafeToSpendCard({ data, demoPreview = false }: { data: SafeToSpend; demoPreview?: boolean }) {
  return (
    <>
      <div className="spending-summary">
        <p className="spending-description">
          {data.safe_amount < 0
            ? "Shortfall after upcoming bills and money set aside."
            : "Available after upcoming bills and money set aside."}
          {demoPreview && " Includes pots added in this demo."}
        </p>
        <p className="spending-amount money">{gbp(data.safe_amount)}</p>
      </div>
      {data.breakdown.length > 0 && (
        <details className="spending-details">
          <summary>How it’s calculated</summary>
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
        View savings pots
        <Icon name="chevron" />
      </a>
    </>
  );
}
