// "Tips and benchmarks": GET /users/{id}/tips and GET /users/{id}/benchmarks.
// Benchmarks are ONS averages (no spread is published), so we show averages, never a "usual range".
import { useState, type ReactNode } from "react";
import { api, entitlementsApi, screensApi } from "../api";
import type { BenchmarkComparison, BenchmarkSummary, Entitlement, EntitlementSummary, Tip, User } from "../types";
import {
  CalcLink, CalcPanel, cap, DISCLAIMER, Icon, Missing, money, StateSwitch, useLoad, type CalcContent,
} from "./shared";
import "./Tips.css";

const TIP_ICON: Record<string, string> = {
  bike_to_work: "bicycle", railcard_16_25: "train", student_council_tax: "house-line",
};
const CLOSE_PCT = 0.1;

/** Pull a trailing "Source: <url>" out of a tip body so it can be a link. */
function splitSource(body: string): { text: string; url: string | null } {
  const m = body.match(/\s*Source:\s*(https?:\/\/\S+?)[).,]?(?:\s|$)[\s\S]*$/);
  if (!m || m.index === undefined) return { text: body, url: null };
  return { text: body.slice(0, m.index).trim(), url: m[1] };
}

export default function Tips({ userId }: { userId: string }) {
  const [userState] = useLoad<User>((s) => api.user(userId, s), [userId]);
  const [tipsState, retryTips] = useLoad<Tip[]>((s) => screensApi.tips(userId, s), [userId]);
  const [benchState, retryBench] = useLoad<BenchmarkSummary>((s) => screensApi.benchmarks(userId, undefined, s), [userId],
    { isMissing: (b) => !b.comparable || b.comparisons.length === 0 });
  const [owedState, retryOwed] = useLoad<EntitlementSummary>((s) => entitlementsApi.get(userId, s), [userId]);
  const [calc, setCalc] = useState<CalcContent | null>(null);

  const user = userState.status === "ok" ? userState.data : null;
  const bench = benchState.status === "ok" ? benchState.data : null;
  const city = user?.region ?? bench?.region ?? "your area";

  return (
    <div className="fts fts-tips">
      <div className="fts-page">
        <div className="fts-head">
          <h1>Tips and benchmarks</h1>
          <p>
            {user ? <>Picked for you: {user.persona.toLowerCase()} in {user.region}. </> : null}
            Savings are estimates based on your own spending.
          </p>
        </div>

        <section className="fts-card ftp-owed" aria-labelledby="ftp-owed-h">
          <div className="ftp-owed-head">
            <span className="fts-bubble"><Icon name="hand-coins" /></span>
            <div className="ftp-owed-title">
              <h2 id="ftp-owed-h">Money you might be owed</h2>
              <p>Help you may be able to claim, based on your own income and bills.</p>
            </div>
            {owedState.status === "ok" && <OwedTotal s={owedState.data} />}
          </div>
          <StateSwitch state={owedState} onRetry={retryOwed} loadingLabel="Checking what you might be owed" rows={4}>
            {(s) => s.items.length === 0 ? (
              <div className="ftp-empty ftp-owed-empty">
                <span className="fts-bubble"><Icon name="magnifying-glass" /></span>
                <strong>Nothing found from your data right now. We'll keep checking.</strong>
              </div>
            ) : (
              <>
                <div className="ftp-owed-list">
                  {s.items.map((e) => <OwedCard key={e.id} e={e} items={s.items} />)}
                </div>
                <div className="ftp-owed-foot">
                  <CalcLink onClick={() => setCalc(owedCalc(s))} />
                  <p className="fts-fine">{s.disclaimer.replace(DISCLAIMER, "").trim()}</p>
                </div>
              </>
            )}
          </StateSwitch>
        </section>

        <StateSwitch state={tipsState} onRetry={retryTips} loadingLabel="Loading tips" rows={4}>
          {(tips) => tips.length === 0 ? (
            <div className="fts-card ftp-empty">
              <span className="fts-bubble"><Icon name="lightbulb" /></span>
              <strong>No tips match your situation right now</strong>
              <span>We only show tips that fit you. We'll check again as your spending changes.</span>
            </div>
          ) : (
            <div className="ftp-tips">
              {tips.map((t) => <TipCard key={t.id} tip={t} onCalc={() => setCalc(tipCalc())} />)}
            </div>
          )}
        </StateSwitch>

        <section className="fts-card ftp-bench" aria-labelledby="ftp-bench-h">
          <div className="ftp-bench-head">
            <h2 id="ftp-bench-h">People like you in {city}</h2>
            {bench ? (
              <p>
                Your spending in the last {bench.window_days} days, next to the ONS monthly average
                for {bench.region_label ?? bench.region}{bench.household_type_label ? <> and for {bench.household_type_label.toLowerCase()} households</> : null}.
                {" "}This is context, not a target. Everyone's month looks different.
              </p>
            ) : (
              <p>This is context, not a target. Everyone's month looks different.</p>
            )}
          </div>
          <StateSwitch state={benchState} onRetry={retryBench} loadingLabel="Loading benchmarks" rows={3}
            missing={<Missing title="We can't compare your spending yet.">
              We don't have enough data. We won't show a guessed number.</Missing>}>
            {(b) => (
              <>
                <Legend b={b} />
                {b.comparisons.map((c) => <BenchRow key={c.category} c={c} b={b} />)}
                {b.household_size_note && <p className="fts-fine ftp-note"><Icon name="info" />{b.household_size_note}</p>}
                <CalcLink onClick={() => setCalc(benchCalc(b))} />
              </>
            )}
          </StateSwitch>
        </section>
      </div>
      {calc && <CalcPanel content={calc} onClose={() => setCalc(null)} />}
    </div>
  );
}

function OwedTotal({ s }: { s: EntitlementSummary }) {
  const likely = s.items.filter((e) => e.confidence === "likely").length;
  if (s.items.length === 0) return null;
  return (
    <div className="ftp-owed-total">
      {s.total_est_value > 0 ? (
        <>
          <span className="ftp-owed-total-l">Up to</span>
          <strong className="fts-money">{money(s.total_est_value)}</strong>
          <span className="ftp-owed-total-l">a year</span>
        </>
      ) : (
        <strong className="fts-money">{s.items.length} to check</strong>
      )}
      <span className="ftp-owed-count">
        {s.items.length} found{likely ? `, ${likely} likely` : ""}
      </span>
    </div>
  );
}

function OwedCard({ e, items }: { e: Entitlement; items: Entitlement[] }) {
  const likely = e.confidence === "likely";
  const needs = e.depends_on ? items.find((i) => i.id === e.depends_on)?.title ?? cap(e.depends_on.replace(/_/g, " ")) : null;
  const showChecker = e.checker_url && e.checker_url !== e.gov_url;
  return (
    <article className="ftp-owed-card">
      <div className="ftp-owed-top">
        <h3>{e.title}</h3>
        <span className={`fts-chip ${likely ? "fts-chip--success-outline" : "fts-chip--lav"}`}>
          <Icon name={likely ? "check-circle" : "magnifying-glass"} />{likely ? "Likely" : "Worth checking"}
        </span>
      </div>
      <p className="ftp-owed-value">
        {e.est_value ? (
          <><Icon name="coins" />About <strong className="fts-money">{money(e.est_value)}</strong> a year</>
        ) : (
          <><Icon name="info" />The amount depends on your circumstances</>
        )}
      </p>
      <div className="ftp-owed-why">
        <span className="ftp-owed-label">Why you</span>
        <p>{e.why_you}</p>
      </div>
      {needs && (
        <p className="ftp-owed-needs"><Icon name="link-simple" />Needs {needs} first</p>
      )}
      <div className="ftp-owed-why">
        <span className="ftp-owed-label">How to claim</span>
        <p>{e.how_to_claim}</p>
      </div>
      <div className="ftp-owed-links">
        <a className="ftp-source" href={e.gov_url} target="_blank" rel="noreferrer">
          <Icon name="arrow-square-out" />Official GOV.UK guidance<span className="fts-visually-hidden"> (opens in a new tab)</span>
        </a>
        {showChecker && (
          <a className="ftp-source" href={e.checker_url!} target="_blank" rel="noreferrer">
            <Icon name="list-checks" />Check if you can get it<span className="fts-visually-hidden"> (opens in a new tab)</span>
          </a>
        )}
      </div>
      <div className="ftp-foot">
        <span className="ftp-disclaimer">{DISCLAIMER}</span>
      </div>
    </article>
  );
}

function owedCalc(s: EntitlementSummary): CalcContent {
  const checked = s.items[0]?.last_checked ?? "";
  return {
    title: "How we find money you might be owed",
    steps: [
      "We look at your income, your bills and who you live with.",
      "We check that against the rules for each scheme on GOV.UK. We only show a scheme when your own data points to it.",
      "Likely means your data fits the main rules. Worth checking means it might fit, or you need to claim something else first.",
      "Amounts use GOV.UK rates. If the amount depends on things we can't see, we don't show a number.",
      "The total adds up the amounts we could work out. It's a rough guide, not a promise.",
    ],
    sources: <>GOV.UK guidance and rates{checked ? <>, checked {checked}</> : null}, and your NatWest transactions.</>,
    unknown: "Your age, any savings held elsewhere, your immigration status, and whether you already claim. The official checker asks about these.",
  };
}

function TipCard({ tip, onCalc }: { tip: Tip; onCalc: () => void }) {
  const { text, url } = splitSource(tip.body);
  return (
    <article className="fts-card ftp-tip">
      <span className="fts-bubble"><Icon name={TIP_ICON[tip.id] ?? "lightbulb"} /></span>
      <h2>{tip.title}</h2>
      {tip.est_saving != null && tip.est_saving > 0 && (
        <span className="fts-chip fts-chip--success-outline">
          <Icon name="piggy-bank" />Could save about <span className="fts-money">{money(tip.est_saving)}</span>
        </span>
      )}
      <p className="ftp-body">{text}</p>
      {url && (
        <a className="ftp-source" href={url} target="_blank" rel="noreferrer">
          <Icon name="arrow-square-out" />Official source<span className="fts-visually-hidden"> (opens in a new tab)</span>
        </a>
      )}
      <div className="ftp-foot">
        <CalcLink onClick={onCalc} />
        <span className="ftp-disclaimer">{DISCLAIMER}</span>
      </div>
    </article>
  );
}

function scaleMax(c: BenchmarkComparison) {
  return Math.max(c.user_spend_30d, c.region_monthly_gbp, c.household_type_monthly_gbp ?? 0, 1) * 1.15;
}
const pct = (v: number, max: number) => `${Math.min(100, (v / max) * 100)}%`;

function Legend({ b }: { b: BenchmarkSummary }) {
  return (
    <div className="ftp-legend" aria-hidden="true">
      <span><i className="ftp-key ftp-key--you" />You</span>
      <span><i className="ftp-key ftp-key--region" />{b.region_label ?? b.region} average</span>
      {b.household_type_label && <span><i className="ftp-key ftp-key--house" />{cap(b.household_type_label.toLowerCase())} average</span>}
    </div>
  );
}

function BenchRow({ c, b }: { c: BenchmarkComparison; b: BenchmarkSummary }) {
  const max = scaleMax(c);
  const region = b.region_label ?? b.region;
  const diff = c.user_spend_30d - c.region_monthly_gbp;
  let icon: string, note: ReactNode;
  if (c.user_spend_30d === 0) { icon = "minus"; note = `No ${c.category} spending recorded in the last ${b.window_days} days`; }
  else if (Math.abs(diff) <= c.region_monthly_gbp * CLOSE_PCT) { icon = "equals"; note = `Close to the ${region} average`; }
  else if (diff > 0) { icon = "arrow-up-right"; note = <>Above the {region} average, by <span className="fts-money">{money(diff)}</span> a month</>; }
  else { icon = "arrow-down-right"; note = <>Below the {region} average, by <span className="fts-money">{money(-diff)}</span> a month</>; }

  const hh = c.household_type_monthly_gbp;
  const summary = `You ${money(c.user_spend_30d)}. ${region} average ${money(c.region_monthly_gbp)}.`
    + (hh != null && b.household_type_label ? ` ${cap(b.household_type_label.toLowerCase())} average ${money(hh)}.` : "");

  return (
    <div className="ftp-row">
      <div className="ftp-row-top">
        <span className="ftp-row-l">{cap(c.category)}{c.ons_category && <span className="ftp-ons"> · ONS: {c.ons_category}</span>}</span>
        <span className="ftp-row-r">
          You <strong className="fts-money">{money(c.user_spend_30d)}</strong> · average <span className="fts-money">{money(c.region_monthly_gbp)}</span>
        </span>
      </div>
      <div className="ftp-track" role="img" aria-label={summary}>
        <div className="ftp-rail" />
        <div className="ftp-tick ftp-tick--region" style={{ left: pct(c.region_monthly_gbp, max) }} />
        {hh != null && <div className="ftp-tick ftp-tick--house" style={{ left: pct(hh, max) }} />}
        <div className="ftp-dot" style={{ left: pct(c.user_spend_30d, max) }} />
      </div>
      <span className="ftp-row-note"><Icon name={icon} /><span>{note}</span></span>
    </div>
  );
}

function tipCalc(): CalcContent {
  return {
    title: "How we estimate savings",
    steps: [
      "We check each scheme's public rules against what we know about you, like your income type and what you spend on.",
      "Where we can, we apply the scheme's rate to your own recorded spending. For example, your transport costs.",
      "The figure is a rough guide. The real saving depends on how you use the scheme.",
    ],
    sources: "Public rules from GOV.UK and scheme providers, and your NatWest transactions.",
    unknown: "Whether you qualify. Each scheme checks this when you apply.",
  };
}

function benchCalc(b: BenchmarkSummary): CalcContent {
  const region = b.region_label ?? b.region;
  return {
    title: "How benchmarks work",
    steps: [
      `We compare you with the ONS average for households in ${region}${b.household_type_label ? `, and for ${b.household_type_label.toLowerCase()} households across the UK` : ""}.`,
      "These are averages, not limits. ONS doesn't publish a usual range, so we don't show one.",
      `Your figure is what you spent in each category over the last ${b.window_days} days.`,
      ...(b.periods_note ? [b.periods_note] : []),
    ],
    sources: b.sources.length ? (
      <ul className="ftp-sources">
        {b.sources.map((s) => (
          <li key={s.url}><a href={s.url} target="_blank" rel="noreferrer">{s.publication}</a>, {s.table}.</li>
        ))}
      </ul>
    ) : "ONS Family Spending, Office for National Statistics.",
    unknown: "Why your spending differs. There are lots of good reasons to be different from the average.",
  };
}
