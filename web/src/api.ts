// The ONLY place that calls fetch. Components import from here.
import type { Alert, ChatReply, Forecast, Pot, SafeToSpend, Tone } from "./types";

const BASE = import.meta.env.VITE_API ?? "http://localhost:8000";

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const api = {
  forecast: (uid: string, days = 90) => http<Forecast>(`/users/${uid}/forecast?days=${days}`),
  safeToSpend: (uid: string) => http<SafeToSpend>(`/users/${uid}/safe-to-spend`),
  alerts: (uid: string) => http<Alert[]>(`/users/${uid}/alerts`),
  pots: (uid: string) => http<Pot[]>(`/users/${uid}/pots`),
  chat: (uid: string, message: string, tone?: Tone) =>
    http<ChatReply>(`/users/${uid}/chat`, { method: "POST", body: JSON.stringify({ message, tone }) }),
};
