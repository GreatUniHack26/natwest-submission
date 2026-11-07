import type { CSSProperties } from "react";
import type { Alert } from "../types";
import Icon from "./Icon";
import { plainAlert } from "./NatLauncher";
import "./AlertList.css";

const priority = {
  high: { label: "Act now", order: 1, icon: "risk" },
  medium: { label: "Keep an eye on", order: 2, icon: "risk" },
  low: { label: "For info", order: 3, icon: "alerts" },
} as const;

const typeLabel: Record<Alert["type"], string> = {
  overspend: "Overspend",
  sudden_change: "Sudden change",
  risk: "Forecast risk",
};

export default function AlertList({ alerts }: { alerts: Alert[] }) {
  if (alerts.length === 0) return <p className="panel-empty">Nothing needs your attention right now.</p>;

  const visibleAlerts = alerts.filter((alert) => alert.severity !== "low").sort((first, second) =>
    priority[first.severity].order - priority[second.severity].order);
  const lowPriorityAlerts = alerts.filter((alert) => alert.severity === "low");
  const highCount = visibleAlerts.filter((alert) => alert.severity === "high").length;

  return (
    <>
      {highCount > 0 && (
        <p className="alarm-summary" role="status">
          <span className="alarm-pulse" aria-hidden="true" />
          {highCount === 1 ? "1 thing needs your attention." : `${highCount} things need your attention.`}
        </p>
      )}
      {visibleAlerts.length > 0 && <AlertRows alerts={visibleAlerts} />}
      {lowPriorityAlerts.length > 0 && (
        <details className="low-priority-alerts">
          <summary>Smaller things ({lowPriorityAlerts.length})</summary>
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
        const copy = plainAlert(alert);
        return (
          // Ids are built from type/category/date on the backend and can repeat, so pair them with the index.
          <li key={`${alert.id}-${index}`} className="alarm" data-severity={alert.severity}
            style={{ "--i": index } as CSSProperties}>
            <span className="alarm-sev" data-severity={alert.severity}>
              {alert.severity === "high" && <span className="alarm-pulse" aria-hidden="true" />}
              <Icon name={level.icon} />
              {level.label}<span className="visually-hidden">: {typeLabel[alert.type] ?? "alert"}</span>
            </span>
            <p className="alarm-reason">{copy.title}</p>
            {copy.detail && <p className="alarm-detail">{copy.detail}</p>}
            {copy.action && <p className="alarm-action">{copy.action}</p>}
            {alert.type === "risk" && (
              <a className="alarm-link" href="#forecast">
                See forecast <Icon name="chevron" />
              </a>
            )}
          </li>
        );
      })}
    </ul>
  );
}
