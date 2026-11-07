import type { Alert } from "../types";
import Icon from "./Icon";
import "./AlertList.css";

const priority = {
  low: { label: "Low priority", order: 3 },
  medium: { label: "Medium priority", order: 2 },
  high: { label: "High priority", order: 1 },
} as const;

export default function AlertList({ alerts }: { alerts: Alert[] }) {
  if (alerts.length === 0) return <p className="panel-empty">You have no alerts right now.</p>;

  const visibleAlerts = alerts.filter((alert) => alert.severity !== "low").sort((first, second) =>
    priority[first.severity].order - priority[second.severity].order);
  const lowPriorityAlerts = alerts.filter((alert) => alert.severity === "low");

  return (
    <>
      {visibleAlerts.length > 0 && <AlertRows alerts={visibleAlerts} />}
      {lowPriorityAlerts.length > 0 && (
        <details className="low-priority-alerts">
          <summary>Low priority alerts ({lowPriorityAlerts.length})</summary>
          <AlertRows alerts={lowPriorityAlerts} />
        </details>
      )}
    </>
  );
}

function AlertRows({ alerts }: { alerts: Alert[] }) {
  return (
    <ul className="grouped-list" role="list">
      {alerts.map((alert) => (
        <li key={alert.id} className="alert-row">
          <span className={`alert-icon alert-${alert.severity}`}>
            <Icon name={alert.type === "risk" ? "risk" : "alerts"} />
          </span>
          <div className="alert-content">
            <p className={`alert-severity alert-${alert.severity}`}>{priority[alert.severity].label}</p>
            <p><strong>{alert.message}</strong></p>
            {alert.suggested_action.trim() && (
              <p className="alert-suggestion">
                <span>Suggested action</span>
                {alert.suggested_action}
              </p>
            )}
            {alert.type === "risk" && (
              <a className="alert-forecast-link" href="#forecast">
                View forecast <Icon name="chevron" />
              </a>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
