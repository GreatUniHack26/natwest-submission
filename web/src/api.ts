// The ONLY place that calls fetch. Components import from here.
import type { Alert, ChatReply, Detail, Forecast, Pot, PurchaseVerdict, SafeToSpend, SpendingForecast, Tone, User, DepositIdeas, TwinSimulations, Timeline } from "./types";

const BASE = import.meta.env.VITE_API ?? "http://localhost:8000";

export class HttpError extends Error {
  constructor(readonly status: number, detail: string) {
    super(`${status} ${detail}`);
  }
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new HttpError(res.status, await res.text());
  return res.json() as Promise<T>;
}

const userPath = (uid: string) => `/users/${encodeURIComponent(uid)}`;

/** Resolve an API-relative path (e.g. ChatReply.audio_url "/audio/x.mp3") against the API origin. */
export const apiUrl = (path: string) => (/^https?:\/\//.test(path) ? path : `${BASE}${path}`);

export interface ChatTurn { role: "user" | "assistant"; content: string }

export interface ApiHealth {
  ok: boolean;
  mock: { data: boolean; forecast: boolean; agent: boolean };
}

export const api = {
  health: (signal?: AbortSignal) => http<ApiHealth>("/health", { signal }),
  user: (uid: string, signal?: AbortSignal) => http<User>(userPath(uid), { signal }),
  forecast: (uid: string, days = 90, signal?: AbortSignal) =>
    http<Forecast>(`${userPath(uid)}/forecast?days=${days}`, { signal }),
  safeToSpend: (uid: string, signal?: AbortSignal) =>
    http<SafeToSpend>(`${userPath(uid)}/safe-to-spend`, { signal }),
  alerts: (uid: string, signal?: AbortSignal) => http<Alert[]>(`${userPath(uid)}/alerts`, { signal }),
  pots: (uid: string, signal?: AbortSignal) => http<Pot[]>(`${userPath(uid)}/pots`, { signal }),
  addPot: (pot: Pot, signal?: AbortSignal) =>
    http<Pot>(`${userPath(pot.user_id)}/pots`, { method: "POST", body: JSON.stringify(pot), signal }),
  simulatePurchase: (uid: string, amount: number, signal?: AbortSignal) =>
    http<PurchaseVerdict>(`${userPath(uid)}/simulate`, { method: "POST", body: JSON.stringify({ amount }), signal }),
  chat: (uid: string, message: string, tone?: Tone, signal?: AbortSignal, history: ChatTurn[] = [], detail?: Detail) =>
    http<ChatReply>(`${userPath(uid)}/chat`, { method: "POST", body: JSON.stringify({ message, tone, history, detail }), signal }),
  timeline: (uid: string, days = 90, overrides: Record<string, unknown> = {}, signal?: AbortSignal) =>
    http<Timeline>(`${userPath(uid)}/timeline`, { method: "POST", body: JSON.stringify({ days, overrides }), signal }),
  simulations: (uid: string, signal?: AbortSignal) => http<TwinSimulations>(`${userPath(uid)}/simulations`, { signal }),
  depositIdeas: (uid: string, signal?: AbortSignal) => http<DepositIdeas>(`${userPath(uid)}/deposit-ideas`, { signal }),
  spending: (uid: string, signal?: AbortSignal) => http<SpendingForecast>(`${userPath(uid)}/spending-forecast`, { signal }),
};

const householdPath = (hid: string) => `/households/${encodeURIComponent(hid)}`;

/** Household (family) oversight endpoints. Amounts are the sum of each member's separately owned money. */
export const householdApi = {
  forecast: (hid: string, days = 90, signal?: AbortSignal) =>
    http<Forecast>(`${householdPath(hid)}/forecast?days=${days}`, { signal }),
  safeToSpend: (hid: string, signal?: AbortSignal) =>
    http<SafeToSpend>(`${householdPath(hid)}/safe-to-spend`, { signal }),
};

/** Everything the browser needs to open a live ElevenLabs voice session with the coach. */
export interface VoiceSession {
  agent_id: string;
  signed_url: string;
  prompt: string;
  first_message: string;
  language: string;
  client_tools: string[];
  llm: string;
  tts_model: string;
}

/** Live voice coach: session bootstrap + the bridge that runs FinTime tools for the voice agent. */
export const voiceApi = {
  session: (uid: string, tone?: Tone, signal?: AbortSignal) =>
    http<VoiceSession>(`${userPath(uid)}/voice/session${tone ? `?tone=${encodeURIComponent(tone)}` : ""}`, { signal }),
  tool: (uid: string, name: string, args: Record<string, unknown>) =>
    http<unknown>(`${userPath(uid)}/voice/tool`, { method: "POST", body: JSON.stringify({ name, args: args ?? {} }) }),
};

/** Screens: transactions (with Need/Want override), dated purchase check, tips and benchmarks. */
export const screensApi = {
  transactions: (uid: string, range: { start?: string; end?: string } = {}, signal?: AbortSignal) => {
    const q = new URLSearchParams(Object.entries(range).filter(([, v]) => v) as [string, string][]).toString();
    return http<import("./types").Transaction[]>(`${userPath(uid)}/transactions${q ? `?${q}` : ""}`, { signal });
  },
  overrideTransaction: (uid: string, txId: string, body: import("./types").CategoryOverride, signal?: AbortSignal) =>
    http<import("./types").Transaction>(`${userPath(uid)}/transactions/${encodeURIComponent(txId)}`, {
      method: "PATCH", body: JSON.stringify(body), signal,
    }),
  simulateOn: (uid: string, amount: number, date: string, signal?: AbortSignal) =>
    http<PurchaseVerdict>(`${userPath(uid)}/simulate`, { method: "POST", body: JSON.stringify({ amount, date }), signal }),
  tips: (uid: string, signal?: AbortSignal) => http<import("./types").Tip[]>(`${userPath(uid)}/tips`, { signal }),
  benchmarks: (uid: string, householdSize?: number, signal?: AbortSignal) =>
    http<import("./types").BenchmarkSummary>(
      `${userPath(uid)}/benchmarks${householdSize ? `?household_size=${householdSize}` : ""}`, { signal }),
};
