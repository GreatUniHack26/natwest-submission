import { useId, useRef } from "react";
import { dateLabel, gbp } from "../format";
import { sampleMonthlyRent, whatIfPresets, type WhatIfPreset, type WhatIfScenario, type WhatIfSettings } from "../whatIf";
import Icon from "./Icon";
import "./WhatIfPanel.css";

const presets = Object.keys(whatIfPresets) as WhatIfPreset[];

export default function WhatIfPanel({ settings, onChange, scenario }: {
  settings: WhatIfSettings | null;
  onChange: (settings: WhatIfSettings | null) => void;
  scenario: WhatIfScenario | null;
}) {
  const headingId = useId();
  const groupName = useId();
  const firstPreset = useRef<HTMLInputElement>(null);
  const preset = settings ? whatIfPresets[settings.preset] : null;
  const shortfall = scenario?.firstShortfall;
  const outcome = shortfall ?? scenario?.lowest;
  const delayLabel = settings?.startAfterDays === 0 ? "No delay" : `${settings?.startAfterDays} days`;

  return (
    <section className="what-if-panel" aria-labelledby={headingId}>
      <div className="what-if-heading">
        <h3 id={headingId}>What if?</h3>
        {settings && (
          <button type="button" className="what-if-clear" onClick={() => {
            onChange(null);
            firstPreset.current?.focus();
          }}>
            Clear scenario
          </button>
        )}
      </div>
      <p>Explore how a change could affect the sample forecast.</p>
      <fieldset className="what-if-presets">
        <legend className="visually-hidden">Choose a scenario</legend>
        {presets.map((key, index) => (
          <label key={key}>
            <input className="visually-hidden" ref={index === 0 ? firstPreset : undefined} type="radio"
              name={groupName} checked={settings?.preset === key}
              onChange={() => onChange({ preset: key, amount: whatIfPresets[key].amount, startAfterDays: 0 })} />
            <span>{whatIfPresets[key].label}</span>
          </label>
        ))}
      </fieldset>
      {settings && preset && (
        <>
          <div className="what-if-controls">
            <label>
              <span>{preset.amountLabel}</span>
              <strong>{settings.preset === "rent-increase" ? `${settings.amount}%` : gbp(settings.amount)}</strong>
              <input type="range" min={0} max={preset.max} step={preset.step} value={settings.amount}
                aria-label={preset.amountLabel}
                aria-valuetext={settings.preset === "rent-increase" ? `${settings.amount} percent` : gbp(settings.amount)}
                onChange={(event) => onChange({ ...settings, amount: event.target.valueAsNumber })} />
            </label>
            <label>
              <span>Start delay</span>
              <strong>{delayLabel}</strong>
              <input type="range" min={0} max={28} step={7} value={settings.startAfterDays}
                aria-label="Start delay" aria-valuetext={delayLabel}
                onChange={(event) => onChange({ ...settings, startAfterDays: event.target.valueAsNumber })} />
            </label>
          </div>
          <p className="what-if-assumption">
            {settings.preset === "rent-increase" && `Assumes ${gbp(sampleMonthlyRent)} in monthly rent. `}
            Monthly changes are spread over 30 days. The delay starts on the first forecast date.
          </p>
        </>
      )}
      <div role="status" aria-atomic="true">
        {outcome && (
          <p className="what-if-result" data-severity={shortfall ? "high" : "low"}>
            {shortfall && <Icon name="risk" />}
            <span>
              <strong>{shortfall ? "Risk of a shortfall" : "No shortfall in this sample"}</strong>
              {shortfall ? "First negative balance: " : "Lowest balance: "}
              <span className="money">{gbp(outcome.expected)}</span> on <time dateTime={outcome.date}>{dateLabel(outcome.date)}</time>.
            </span>
          </p>
        )}
      </div>
    </section>
  );
}
