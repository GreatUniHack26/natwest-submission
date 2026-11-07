import { useEffect, useState } from "react";
import { api } from "../api";
import { dateLabel, gbp } from "../format";
import type { DepositIdeas } from "../types";
import { useParked } from "./DepositIdeas";
import Icon from "./Icon";

const pence = (value: number) => `£${value.toFixed(2)}`;

/** Home shortcut to the short-term saver idea: one number, one line, tap through to pots. */
export default function DepositHero({ userId, revision = 0 }: { userId: string; revision?: number }) {
  const [ideas, setIdeas] = useState<DepositIdeas | null>(null);
  const [parked] = useParked(userId);

  useEffect(() => {
    const controller = new AbortController();
    api.depositIdeas(userId, controller.signal).then(
      (result) => { if (!controller.signal.aborted) setIdeas(result); },
      () => { if (!controller.signal.aborted) setIdeas(null); },
    );
    return () => controller.abort();
  }, [userId, revision]);

  if (!ideas || ideas.ideas.length === 0 || ideas.total_est_interest <= 0) return null;

  const dated = ideas.ideas.filter((idea) => idea.withdraw_by).sort((a, b) => b.amount - a.amount)[0];
  const earning = ideas.ideas.filter((idea) => idea.withdraw_by && parked.includes(idea.pot));
  const earningTotal = earning.reduce((sum, idea) => sum + idea.est_interest, 0);
  const isEarning = earning.length > 0;

  return (
    <a className="deposit-hero" href="#deposits" data-earning={isEarning}>
      <span className="deposit-hero-icon" aria-hidden="true"><Icon name={isEarning ? "check" : "coins"} /></span>
      <span className="deposit-hero-copy">
        <span className="deposit-hero-label">{isEarning ? "Your pots are earning about" : "Your pots could earn up to"}</span>
        <span className="deposit-hero-value money">{pence(isEarning ? earningTotal : ideas.total_est_interest)}</span>
        <span className="deposit-hero-line">
          {isEarning
            ? `${earning.map((idea) => idea.pot).join(" and ")} parked in a saver. Simulation only.`
            : dated
              ? `${gbp(dated.amount)} for ${dated.pot} sits unused until ${dateLabel(dated.withdraw_by!)}.`
              : "Money in your pots could earn interest while you wait."}
        </span>
      </span>
      <span className="deposit-hero-go" aria-hidden="true"><Icon name="chevron" /></span>
    </a>
  );
}
