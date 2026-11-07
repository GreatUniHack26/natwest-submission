import { useEffect, useState } from "react";
import { api } from "./api";
import AlertList from "./components/AlertList";
import ChatPanel from "./components/ChatPanel";
import ForecastChart from "./components/ForecastChart";
import SafeToSpendCard from "./components/SafeToSpendCard";
import type { Alert, Forecast, SafeToSpend } from "./types";

const USER_ID = "sam";

export default function App() {
  const [safe, setSafe] = useState<SafeToSpend | null>(null);
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [cursor, setCursor] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.safeToSpend(USER_ID), api.forecast(USER_ID, 56), api.alerts(USER_ID)])
      .then(([s, f, a]) => { setSafe(s); setForecast(f); setAlerts(a); })
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <p>Could not reach the API: {error}</p>;
  if (!safe || !forecast) return <p>Loading…</p>;
  const point = forecast.points[cursor];

  return (
    <main style={{ fontFamily: "system-ui", maxWidth: 800, margin: "24px auto", padding: "0 16px" }}>
      <h1>FinTime</h1>
      <SafeToSpendCard data={safe} />
      <section>
        <h2>Time travel</h2>
        <ForecastChart data={forecast} cursor={cursor} />
        <input type="range" min={0} max={forecast.points.length - 1} value={cursor}
               onChange={(e) => setCursor(Number(e.target.value))} style={{ width: "100%", maxWidth: 700 }} />
        <p>
          {point.date}: expected £{point.expected.toFixed(0)} (range £{point.low.toFixed(0)} to £{point.high.toFixed(0)})
        </p>
        {forecast.risk_events.map((r) => <p key={r.date}><strong>⚠ {r.date}: {r.reason}</strong></p>)}
        <details><summary>Assumptions</summary><ul>{forecast.assumptions.map((a) => <li key={a}>{a}</li>)}</ul></details>
      </section>
      <AlertList alerts={alerts} />
      <ChatPanel userId={USER_ID} />
    </main>
  );
}
