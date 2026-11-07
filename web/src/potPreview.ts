import type { Pot, SafeToSpend } from "./types";

export function mergeDemoPots(serverPots: Pot[], demoPots: Pot[]): Pot[] {
  const existingIds = new Set(serverPots.map((pot) => pot.id));
  return [...serverPots, ...demoPots.filter((pot) => !existingIds.has(pot.id))];
}

export function previewSafeToSpend(data: SafeToSpend, demoPots: Pot[]): SafeToSpend {
  if (demoPots.length === 0) return data;

  const demoPence = demoPots.reduce((sum, pot) => sum + Math.round(pot.amount * 100), 0);
  return {
    ...data,
    pots_total: (Math.round(data.pots_total * 100) + demoPence) / 100,
    safe_amount: (Math.round(data.safe_amount * 100) - demoPence) / 100,
    breakdown: [...data.breakdown, { label: "New demo pots", amount: -demoPence / 100 }],
  };
}
