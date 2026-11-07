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

export interface CategorySpend {
  category: string;
  spent_so_far: number;
  expected_so_far: number;
  projected_month: number;
  typical_month: number;
  status: "over" | "watch" | "on_track";
  alarm: string | null;
}
export interface SpendingForecast {
  user_id: string;
  month: string;
  days_elapsed: number;
  days_in_month: number;
  spent_so_far: number;
  projected_month: number;
  typical_month: number;
  categories: CategorySpend[];
}

export interface DepositIdea {
  pot: string;
  amount: number;
  due_date: string | null;
  idle_days: number;
  account_type: string;
  aer: number;
  est_interest: number;
  interest_period: "until due date" | "per year";
  withdraw_by: string | null;
  caution: string | null;
}
export interface DepositIdeas {
  user_id: string;
  aer_assumption: number;
  total_est_interest: number;
  ideas: DepositIdea[];
  disclaimer: string;
}

export interface TwinSimulations {
  user_id: string;
  simulations: number;
  horizon_days: number;
  chance_below_zero: number;
  chance_below_zero_within: Record<string, number>;
  chance_dip_into_pots: number;
  coin_flip_date: string | null;
  typical_first_negative_date: string | null;
  runway_days_if_income_stops: number;
  runway_capped: boolean;
  points: { date: string; p10: number; p50: number; p90: number; chance_below_zero: number }[];
  assumptions: string[];
}

export interface TimelineDay {
  date: string; expected: number; p10: number; p50: number; p90: number; protected: number; chance_below_zero: number;
}
export interface TimelineEvent { date: string; label: string; amount: number; kind: "income" | "bill" | "pot" }
export interface Timeline {
  user_id: string;
  horizon_days: number;
  simulations: number;
  days: TimelineDay[];
  events: TimelineEvent[];
  risks: { date: string; severity: Severity; reason: string }[];
  first_below_zero: string | null;
  scenario: null | {
    expected: number[];
    first_below_zero: string | null;
    risks: { date: string; severity: Severity; reason: string }[];
    assumptions: string[];
    end_difference: number;
  };
}

/** One household member's share of the combined safe-to-spend, parsed from breakdown labels. */
export interface HouseholdMemberShare {
  id: string;
  balance: number;
  pots: number;
  bills: number;
  net: number;
  notes: string[];
  billItems: { name: string; date: string; amount: number }[];
}

// ---- Screens (Landing / Afford / Transactions / Tips) ----
export type Kind = "need" | "want" | "income";
export interface Transaction {
  id: string;
  user_id: string;
  date: string;
  merchant: string;
  amount: number; // negative = spend, positive = income
  category: string;
  kind: Kind;
}
export interface CategoryOverride { category: string; kind: Kind }
export interface Tip {
  id: string;
  title: string;
  body: string;
  est_saving: number | null;
  disclaimer: string;
}
export interface BenchmarkComparison {
  category: string;
  ons_category: string | null;
  region_monthly_gbp: number;
  household_type_monthly_gbp: number | null;
  user_spend_30d: number;
}
export interface BenchmarkSummary {
  user_id: string;
  region: string;
  region_label: string | null;
  household_size: number | null;
  household_type_label: string | null;
  household_size_note: string | null;
  window_days: number;
  comparable: boolean;
  comparisons: BenchmarkComparison[];
  explanation: string | null;
  framing_note: string;
  periods_note: string | null;
  sources: { publication: string; table: string; url: string }[];
}

/** Text-coach reply shape: a one-line answer plus bullets, or fuller paragraphs. */
export type Detail = "concise" | "detailed";
