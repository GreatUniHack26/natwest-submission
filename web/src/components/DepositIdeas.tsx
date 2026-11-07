import { useEffect, useState } from "react";
import { api } from "../api";
import { dateLabel, gbp } from "../format";
import type { DepositIdeas as Ideas } from "../types";

/** "Put idle money to work": short-term saver estimates for ring-fenced pots. */
export default function DepositIdeas({ userId, revision = 0 }: { userId: string; revision?: number }) {
  const [ideas, setIdeas] = useState<Ideas | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api.depositIdeas(userId, controller.signal).then(
      (result) => { if (!controller.signal.aborted) setIdeas(result); },
      () => { if (!controller.signal.aborted) setIdeas(null); },
    );
    return () => controller.abort();
  }, [userId, revision]);

  if (!ideas || ideas.ideas.length === 0) return null;

  return (
    <section className="deposit-ideas" aria-labelledby={`deposit-${userId}`}>
      <div className="deposit-head">
        <h3 id={`deposit-${userId}`}>Put idle money to work</h3>
        <p className="deposit-total">
          up to <strong className="money">{gbp(ideas.total_est_interest)}</strong>
        </p>
      </div>
      <p className="deposit-lede">
        Your pots are protected until they’re due. Parked in an instant-access saver, they could earn interest and still be there on time.
      </p>
      {ideas.ideas.find((idea) => idea.caution)?.caution && (
        <p className="deposit-caution">{ideas.ideas.find((idea) => idea.caution)?.caution}</p>
      )}
      <ul className="deposit-list">
        {ideas.ideas.map((idea, index) => (
          <li key={idea.pot} style={{ animationDelay: `${index * 90}ms` }}>
            <div className="deposit-row">
              <div>
                <strong>{idea.pot}</strong>
                <p>
                  {gbp(idea.amount)} ·{" "}
                  {idea.due_date
                    ? <>idle {idea.idle_days} days, back by <time dateTime={idea.withdraw_by ?? undefined}>{dateLabel(idea.withdraw_by ?? idea.due_date)}</time></>
                    : "no due date"}
                </p>
              </div>
              <p className="deposit-earn">
                <strong className="money">+{gbp(idea.est_interest)}</strong>
                <span>{idea.interest_period}</span>
              </p>
            </div>
          </li>
        ))}
      </ul>
      <p className="deposit-disclaimer">{ideas.disclaimer}</p>
    </section>
  );
}
