import type { Forecast, ForecastPoint } from "./types";

export const sampleMonthlyRent = 800;
const dayInMilliseconds = 86_400_000;

export const whatIfPresets = {
  "lose-job": { label: "Lose job", amountLabel: "Monthly income lost", amount: 1_500, max: 4_000, step: 50 },
  "rent-increase": { label: "Rent +10%", amountLabel: "Rent increase", amount: 10, max: 50, step: 1 },
  "new-baby": { label: "New baby", amountLabel: "Extra monthly spending", amount: 400, max: 1_500, step: 25 },
} as const;

export type WhatIfPreset = keyof typeof whatIfPresets;

export interface WhatIfSettings {
  preset: WhatIfPreset;
  amount: number;
  startAfterDays: number;
}

export interface WhatIfScenario {
  expectedByDate: ReadonlyMap<string, number>;
  lowest: Pick<ForecastPoint, "date" | "expected">;
  firstShortfall: Pick<ForecastPoint, "date" | "expected"> | null;
}

export function buildWhatIf(forecast: Forecast, settings: WhatIfSettings): WhatIfScenario | null {
  const points = [...forecast.points].sort((a, b) => a.date.localeCompare(b.date));
  if (points.length === 0) return null;

  const start = Date.parse(points[0].date) + settings.startAfterDays * dayInMilliseconds;
  const monthlyImpact = settings.preset === "rent-increase"
    ? sampleMonthlyRent * settings.amount / 100
    : settings.amount;
  const expectedByDate = new Map<string, number>();
  let lowest = { date: points[0].date, expected: points[0].expected };
  let firstShortfall: WhatIfScenario["firstShortfall"] = null;

  for (const point of points) {
    const elapsedDays = Math.max(0, (Date.parse(point.date) - start) / dayInMilliseconds);
    // Spread the sample monthly change evenly over 30 days.
    const expected = Math.round((point.expected - monthlyImpact * elapsedDays / 30) * 100) / 100;
    expectedByDate.set(point.date, expected);
    if (expected < lowest.expected) lowest = { date: point.date, expected };
    if (!firstShortfall && expected < 0) firstShortfall = { date: point.date, expected };
  }

  return { expectedByDate, lowest, firstShortfall };
}
