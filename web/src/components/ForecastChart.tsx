import { useId, useMemo, useState, type KeyboardEvent } from "react";
import { dateLabel, gbp } from "../format";
import type { Forecast, ForecastPoint, RiskEvent, Severity } from "../types";
import type { WhatIfScenario } from "../whatIf";
import Icon from "./Icon";

const plotWidth = 600;
const plotHeight = 170;
const horizontalInset = 6;
const dayInMilliseconds = 86_400_000;
const severityRank: Record<Severity, number> = { low: 1, medium: 2, high: 3 };
const severityLabel: Record<Severity, string> = { low: "Low", medium: "Medium", high: "High" };

export function nearestPointIndex(points: ForecastPoint[], date: string | number) {
  const target = typeof date === "string" ? Date.parse(date) : date;
  let nearestIndex = 0;
  let nearestDate = Infinity;
  let nearestDistance = Infinity;
  points.forEach((point, index) => {
    const candidate = Date.parse(point.date);
    const distance = Math.abs(candidate - target);
    if (distance < nearestDistance || (distance === nearestDistance && candidate < nearestDate)) {
      nearestIndex = index;
      nearestDate = candidate;
      nearestDistance = distance;
    }
  });
  return nearestIndex;
}

function groupRiskEvents(events: RiskEvent[], firstDate: string, lastDate: string) {
  const severityByDate = new Map<string, Severity>();
  for (const { date, severity } of events) {
    if (date < firstDate || date > lastDate) continue;
    const previous = severityByDate.get(date);
    if (!previous || severityRank[severity] > severityRank[previous]) {
      severityByDate.set(date, severity);
    }
  }
  return [...severityByDate.entries()].sort(([a], [b]) => a.localeCompare(b));
}

export default function ForecastChart({
  data, cursor, onCursorChange, selectedRiskDate, onRiskSelect, whatIf,
}: {
  data: Forecast;
  cursor: number;
  onCursorChange: (index: number) => void;
  selectedRiskDate?: string | null;
  onRiskSelect?: (date: string) => void;
  whatIf?: WhatIfScenario | null;
}) {
  const descriptionId = useId();
  const [showValues, setShowValues] = useState(false);
  const samples = useMemo(() => data.points.map((point, index) => ({ point, index }))
    .sort((a, b) => a.point.date.localeCompare(b.point.date)), [data.points]);
  if (samples.length === 0) return null;

  const firstDate = samples[0].point.date;
  const lastDate = samples[samples.length - 1].point.date;
  const start = Date.parse(firstDate);
  const dayOffset = (date: string) => (Date.parse(date) - start) / dayInMilliseconds;
  const span = dayOffset(lastDate);
  const currentIndex = Math.max(0, samples.findIndex(({ index }) => index === cursor));
  const selected = samples[currentIndex].point;
  const whatIfAmount = whatIf?.expectedByDate.get(selected.date);
  const riskDates = groupRiskEvents(data.risk_events, firstDate, lastDate);
  const firstExpected = samples[0].point.expected;
  const lastExpected = samples[samples.length - 1].point.expected;

  const values = data.points.flatMap((point) => [point.low, point.expected, point.high]);
  if (whatIf) values.push(...whatIf.expectedByDate.values());
  const min = Math.min(0, ...values);
  const max = Math.max(0, ...values);
  const step = Math.max(1, 10 ** Math.floor(Math.log10((max - min || 1) / 3)));
  const increment = step * Math.ceil((max - min || 1) / (3 * step));
  const floor = increment * Math.floor(min / increment);
  const ceiling = Math.max(increment * Math.ceil(max / increment), floor + increment);
  const ticks = Array.from({ length: (ceiling - floor) / increment + 1 }, (_, i) => ceiling - i * increment);

  const x = (date: string) => span > 0
    ? horizontalInset + (dayOffset(date) / span) * (plotWidth - 2 * horizontalInset)
    : plotWidth / 2;
  const y = (amount: number) => 8 + (1 - (amount - floor) / (ceiling - floor)) * (plotHeight - 16);
  const plotCoordinate = (date: string, amount: number) => `${x(date).toFixed(2)},${y(amount).toFixed(2)}`;
  const coordinate = (point: ForecastPoint, key: "low" | "expected" | "high") =>
    plotCoordinate(point.date, point[key]);
  const band = [
    ...samples.map(({ point }) => coordinate(point, "high")),
    ...samples.map(({ point }) => coordinate(point, "low")).reverse(),
  ].join(" ");

  function onScrubberKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    let nextIndex: number;
    switch (event.key) {
      case "ArrowLeft":
      case "ArrowDown":
        nextIndex = Math.max(0, currentIndex - 1);
        break;
      case "ArrowRight":
      case "ArrowUp":
        nextIndex = Math.min(samples.length - 1, currentIndex + 1);
        break;
      default:
        return;
    }
    event.preventDefault();
    onCursorChange(samples[nextIndex].index);
  }

  return (
    <div className="forecast-graph">
      <p className="visually-hidden" id={descriptionId}>
        {span > 0
          ? `The expected balance starts at ${gbp(firstExpected)} on ${dateLabel(firstDate)} and ends at ${gbp(lastExpected)} on ${dateLabel(lastDate)}.`
          : `The expected balance on ${dateLabel(firstDate)} is ${gbp(firstExpected)}.`}
        {" "}The forecast table shows the lower and upper estimates for each date.
        {whatIf && " The dashed line shows the sample what-if balance, also available in the table."}
      </p>
      <div className="chart-axis" aria-hidden="true">
        {ticks.map((tick) => <span key={tick}>{gbp(tick)}</span>)}
      </div>
      <div className="chart-plot">
        <svg viewBox={`0 0 ${plotWidth} ${plotHeight}`} preserveAspectRatio="none"
          role="img" aria-label={whatIf
            ? "Expected balance, projected range and what-if balance over time"
            : "Expected balance and projected range over time"} aria-describedby={descriptionId}>
          {ticks.map((tick) => (
            <line key={tick} className={tick === 0 ? "chart-zero" : "chart-gridline"}
              x1={0} x2={plotWidth} y1={y(tick)} y2={y(tick)} />
          ))}
          {span > 0 ? (
            <polygon className="chart-band" points={band} />
          ) : (
            <rect className="chart-band" x={x(selected.date) - 4} y={y(selected.high)}
              width={8} height={Math.max(0, y(selected.low) - y(selected.high))} />
          )}
          {riskDates.map(([date, severity]) => (
            <line key={date} className="chart-risk-line" data-severity={severity}
              data-selected={selectedRiskDate === date} x1={x(date)} x2={x(date)} y1={8} y2={plotHeight - 8} />
          ))}
          <line className="chart-cursor" x1={x(selected.date)} x2={x(selected.date)} y1={5} y2={plotHeight - 5} />
          <polyline className="chart-line" points={samples.map(({ point }) => coordinate(point, "expected")).join(" ")} />
          {whatIf && (
            <polyline className="chart-what-if" points={samples.map(({ point }) =>
              plotCoordinate(point.date, whatIf.expectedByDate.get(point.date) ?? point.expected)).join(" ")} />
          )}
          <line className="chart-point" x1={x(selected.date)} x2={x(selected.date)}
            y1={y(selected.expected)} y2={y(selected.expected)} />
          {whatIfAmount !== undefined && whatIfAmount !== selected.expected && (
            <line className="chart-what-if-point" x1={x(selected.date)} x2={x(selected.date)}
              y1={y(whatIfAmount)} y2={y(whatIfAmount)} />
          )}
        </svg>
        {riskDates.map(([date, severity]) => (
          <button key={date} type="button" className="chart-risk-marker" data-severity={severity}
            style={{ left: `${(x(date) / plotWidth) * 100}%` }}
            aria-label={`${severityLabel[severity]} risk on ${dateLabel(date)}`}
            aria-pressed={selectedRiskDate === date}
            onClick={() => {
              if (onRiskSelect) onRiskSelect(date);
              else onCursorChange(nearestPointIndex(data.points, date));
            }}>
            <span className="chart-risk-marker-icon"><Icon name="risk" /></span>
          </button>
        ))}
      </div>
      <div className="forecast-scrubber">
        {span > 0 && (
          <label>
            <span className="forecast-scrubber-label">Explore dates</span>
            <input type="range"
              aria-valuetext={`${dateLabel(selected.date)}, expected ${gbp(selected.expected)}, range ${gbp(selected.low)} to ${gbp(selected.high)}`
                + (whatIfAmount === undefined ? "" : `, what-if balance ${gbp(whatIfAmount)}`)}
              aria-describedby={descriptionId}
              min={0} max={span} value={dayOffset(selected.date)}
              onChange={(event) => onCursorChange(nearestPointIndex(
                data.points, start + event.target.valueAsNumber * dayInMilliseconds,
              ))}
              onKeyDown={onScrubberKeyDown} />
          </label>
        )}
        <div className="forecast-dates" aria-hidden="true">
          <span className="chart-date-boundary">{dateLabel(firstDate)}</span>
          {span > 0 && <span className="chart-date-boundary">{dateLabel(lastDate)}</span>}
        </div>
        {whatIfAmount !== undefined && (
          <p className="what-if-cursor">What-if balance on {dateLabel(selected.date)} <strong>{gbp(whatIfAmount)}</strong></p>
        )}
      </div>
      <details className="forecast-values" onToggle={(event) => setShowValues(event.currentTarget.open)}>
        <summary>View forecast as a table</summary>
        {showValues && (
          <table>
            <caption className="visually-hidden">Forecast balances by date</caption>
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col">Expected</th>
                <th scope="col">Low</th>
                <th scope="col">High</th>
                {whatIf && <th scope="col">What if</th>}
              </tr>
            </thead>
            <tbody>
              {samples.map(({ point, index }) => (
                <tr key={index}>
                  <th scope="row"><time dateTime={point.date}>{dateLabel(point.date)}</time></th>
                  <td>{gbp(point.expected)}</td>
                  <td>{gbp(point.low)}</td>
                  <td>{gbp(point.high)}</td>
                  {whatIf && <td>{gbp(whatIf.expectedByDate.get(point.date) ?? point.expected)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </details>
    </div>
  );
}
