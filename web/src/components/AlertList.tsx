import type { CSSProperties } from "react";
import type { Alert } from "../types";
import Icon from "./Icon";
import "./AlertList.css";

const priority = {
  high: { label: "High", order: 1, icon: "risk" },
  medium: { label: "Medium", order: 2, icon: "risk" },
  low: { label: "Low", order: 3, icon: "alerts" },
} as const;

const typeLabel: Record<Alert["type"], string> = {
  overspend: "Overspend",
  sudden_change: "Sudden change",
  risk: "Forecast risk",
};

const sentence = (text: string) => {
  const trimmed = text.trim();
  return trimmed ? trimmed.charAt(0).toUpperCase() + trimmed.slice(1) : trimmed;
};

export default function AlertList({ alerts }: { alerts: Alert[] }) {
  if (alerts.length === 0) return <p className="panel-empty">You have no alerts right now.</p>;

  const visibleAlerts = alerts.filter((alert) => alert.severity !== "low").sort((first, second) =>
    priority[first.severity].order - priority[second.severity].order);
  const lowPriorityAlerts = alerts.filter((alert) => alert.severity === "low");
  const highCount = visibleAlerts.filter((alert) => alert.severity === "high").length;

  return (
    <>
      {highCount > 0 && (
        <p className="alarm-summary" role="status">
          <span className="alarm-pulse" aria-hidden="true" />
          {highCount === 1 ? "1 alarm needs attention now." : `${highCount} alarms need attention now.`}
        </p>
      )}
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
    <ul className="alarm-list" role="list">
      {alerts.map((alert, index) => {
        const level = priority[alert.severity];
        const action = alert.suggested_action.trim();
        return (
          // Ids are built from type/category/date on the backend and can repeat, so pair them with the index.
          <li key={`${alert.id}-${index}`} className="alarm" data-severity={alert.severity}
            style={{ "--i": index } as CSSProperties}>
            <div className="alarm-tags">
              <span className="alarm-sev" data-severity={alert.severity}>
                {alert.severity === "high" && <span className="alarm-pulse" aria-hidden="true" />}
                <Icon name={level.icon} />
                {level.label}<span className="visually-hidden"> priority</span>
              </span>
              <span className="alarm-type">{typeLabel[alert.type] ?? "Alert"}</span>
            </div>
            <p className="alarm-reason">{sentence(alert.message)}</p>
            {action && (
              <p className="alarm-action">
                <span className="alarm-action-label">Do this</span>
                {sentence(action)}
              </p>
            )}
            {alert.type === "risk" && (
              <a className="alarm-link" href="#forecast">
                View forecast <Icon name="chevron" />
              </a>
            )}
          </li>
        );
      })}
    </ul>
  );
}
