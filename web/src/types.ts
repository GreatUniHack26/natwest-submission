// Mirrors contracts/schemas.py. Keep in sync (or regenerate: `make types`).
export type Tone = "friendly" | "direct" | "simple";
export type Severity = "low" | "medium" | "high";

export interface ForecastPoint { date: string; low: number; expected: number; high: number }
export interface RiskEvent { date: string; reason: string; severity: Severity }
export interface Forecast {
  user_id: string;
  horizon_days: number;
  points: ForecastPoint[];
  risk_events: RiskEvent[];
  assumptions: string[];
}
export interface BreakdownItem { label: string; amount: number }
export interface SafeToSpend {
  balance: number;
  pots_total: number;
  upcoming_bills: number;
  safe_amount: number;
  breakdown: BreakdownItem[];
}
export interface Alert {
  id: string;
  type: "overspend" | "sudden_change" | "risk";
  category: string | null;
  message: string;
  suggested_action: string;
  severity: Severity;
}
export interface Pot { id: string; user_id: string; name: string; amount: number; due_date: string | null }
export interface ChatReply { text: string; numbers_used: Record<string, number>; audio_url: string | null }
export interface PurchaseVerdict {
  affordable: boolean;
  safe_after: number;
  better_date: string | null;
  reason: string;
  numbers_used: Record<string, number>;
}

export interface User {
  id: string;
  name: string;
  persona: string;
  region: string;
  household_id: string | null;
  tone: Tone;
}
