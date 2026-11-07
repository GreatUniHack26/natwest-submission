import type { Alert } from "../types";

const colour = { low: "#2e7d32", medium: "#ed6c02", high: "#c62828" } as const;

export default function AlertList({ alerts }: { alerts: Alert[] }) {
  return (
    <section>
      <h2>Alerts</h2>
      {alerts.map((a) => (
        <div key={a.id} style={{ borderLeft: `4px solid ${colour[a.severity]}`, padding: "6px 12px", marginBottom: 8 }}>
          <strong>{a.message}</strong>
          <div>Suggestion: {a.suggested_action}</div>
        </div>
      ))}
    </section>
  );
}
