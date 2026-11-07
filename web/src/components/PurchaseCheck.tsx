import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "../api";
import { dateLabel, gbp } from "../format";
import type { PurchaseVerdict } from "../types";
import "./PurchaseCheck.css";

type CheckState =
  | { status: "idle" | "pending" | "error" }
  | { status: "ready"; amount: number; verdict: PurchaseVerdict };

export default function PurchaseCheck({ userId }: { userId: string }) {
  return <PurchaseCheckForm key={userId} userId={userId} />;
}

function PurchaseCheckForm({ userId }: { userId: string }) {
  const [amount, setAmount] = useState("30");
  const [check, setCheck] = useState<CheckState>({ status: "idle" });
  const request = useRef<AbortController | null>(null);
  const pending = check.status === "pending";

  useEffect(() => () => request.current?.abort(), []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const price = Number(amount);
    if (!Number.isFinite(price) || price < 0.01 || request.current) return;

    const controller = new AbortController();
    request.current = controller;
    setCheck({ status: "pending" });
    try {
      const verdict = await api.simulatePurchase(userId, price, controller.signal);
      if (!controller.signal.aborted) setCheck({ status: "ready", amount: price, verdict });
    } catch {
      if (!controller.signal.aborted) setCheck({ status: "error" });
    } finally {
      request.current = null;
    }
  }

  return (
    <section id="coach" className="panel" tabIndex={-1} aria-labelledby="coach-title">
      <h2 id="coach-title">Ask your coach</h2>
      <p className="purchase-check-intro">
        Chat is currently unavailable. You can check a purchase against your live forecast.
      </p>
      <form className="purchase-check-form" onSubmit={submit}>
        <label>
          Purchase amount
          <span className="purchase-check-amount">
            <span aria-hidden="true">£</span>
            <input type="number" inputMode="decimal" min="0.01" step="0.01" required value={amount}
              aria-label="Purchase amount in pounds" onChange={(event) => setAmount(event.target.value)} />
          </span>
        </label>
        <button type="submit" className="purchase-check-submit" disabled={pending}>
          {check.status === "error" ? "Try again" : "Check purchase"}
        </button>
      </form>
      <div role="status">
        {pending && <p className="purchase-check-status">Checking your forecast…</p>}
        {check.status === "error" && <p className="purchase-check-error">Couldn’t check this purchase. Try again.</p>}
        {check.status === "ready" && <PurchaseResult amount={check.amount} verdict={check.verdict} />}
      </div>
    </section>
  );
}

function PurchaseResult({ amount, verdict }: { amount: number; verdict: PurchaseVerdict }) {
  const price = verdict.numbers_used.price ?? amount;
  const before = verdict.numbers_used.safe_to_spend;

  return (
    <div className="purchase-check-result" data-affordable={verdict.affordable}>
      <h3>{gbp(price)} purchase {verdict.affordable ? "fits" : "doesn’t fit"} your forecast</h3>
      <p>{verdict.reason}</p>
      <dl>
        {before !== undefined && <div><dt>Safe to spend before purchase</dt><dd className="money">{gbp(before)}</dd></div>}
        <div><dt>Safe to spend after purchase</dt><dd className="money">{gbp(verdict.safe_after)}</dd></div>
        {verdict.better_date && (
          <div>
            <dt>Upcoming sale</dt>
            <dd><time dateTime={verdict.better_date}>{dateLabel(verdict.better_date)}</time></dd>
          </div>
        )}
      </dl>
    </div>
  );
}
