// The ONLY place that calls fetch. Components import from here.
import type { Alert, ChatReply, Forecast, Pot, PurchaseVerdict, SafeToSpend, Tone, User } from "./types";

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
  chat: (uid: string, message: string, tone?: Tone, signal?: AbortSignal) =>
    http<ChatReply>(`${userPath(uid)}/chat`, { method: "POST", body: JSON.stringify({ message, tone }), signal }),
};
