import { apiUrl } from "../api";
import Row, { Chip } from "./Row";

export interface NatAlarm {
  id: string;
  level: "act" | "watch" | "good";
  title: string;
  body: string;
  action: string;
  ask_nat: string;
  link: string | null;
  when: string | null;
}

/** GET /users/{id}/alarms: ranked, de-duplicated alarms in plain words. */
export async function loadAlarms(userId: string, signal: AbortSignal): Promise<NatAlarm[]> {
  const response = await fetch(apiUrl(`/users/${encodeURIComponent(userId)}/alarms`), { signal });
  if (!response.ok) throw new Error(`alarms ${response.status}`);
  const data = await response.json() as { alarms?: NatAlarm[] };
  return data.alarms ?? [];
}

const chip = {
  act: { tone: "bad", label: "Act now", icon: "warning" },
  watch: { tone: "warn", label: "Watch", icon: "eye" },
  good: { tone: "good", label: "Good news", icon: "check-circle" },
} as const;

/** Alerts as list rows: bold title, one-line body, the action as a second line, one status chip. */
export function AlarmRows({ alarms }: { alarms: NatAlarm[] }) {
  if (alarms.length === 0) return <p className="panel-empty">Nothing needs your attention right now.</p>;
  return (
    <ul className="rows">
      {alarms.map((alarm) => {
        const c = chip[alarm.level] ?? chip.watch;
        return (
          <li key={alarm.id}>
            <Row icon={c.icon} tone={c.tone} href={alarm.link ?? undefined}
              title={alarm.title}
              subtitle={<>{alarm.body}<span className="row-action">{alarm.action}</span></>}
              chip={<Chip tone={c.tone}>{c.label}</Chip>} />
          </li>
        );
      })}
    </ul>
  );
}
