import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { api, type ApiHealth } from "./api";
import AlertList from "./components/AlertList";
import ChatPanel from "./components/ChatPanel";
import ForecastChart, { nearestPointIndex } from "./components/ForecastChart";
import HouseholdPanel from "./components/HouseholdPanel";
import Icon from "./components/Icon";
import PurchaseCheck from "./components/PurchaseCheck";
import SafeToSpendCard from "./components/SafeToSpendCard";
import SavingsPots from "./components/SavingsPots";
import WhatIfPanel from "./components/WhatIfPanel";
import { dateLabel, gbp } from "./format";
import { mergeDemoPots, previewSafeToSpend } from "./potPreview";
import type { Forecast, Pot, User } from "./types";
import { buildWhatIf, type WhatIfSettings } from "./whatIf";
import "./dashboard.css";

const personas = [
  { name: "Sam", id: "sam" },
  { name: "Family", id: import.meta.env.VITE_FAMILY_USER_ID || "maya" },
] as const;
type Persona = (typeof personas)[number];

const sections = [
  { id: "overview", label: "Overview", icon: "overview" },
  { id: "forecast", label: "Forecast", icon: "forecast" },
  { id: "pots", label: "Pots", icon: "pots" },
  { id: "alerts", label: "Alerts", icon: "alerts" },
  { id: "coach", label: "Coach", icon: "coach" },
] as const;
const householdSection = { id: "household", label: "Household", icon: "household" } as const;

type RequestState<T> =
  | { status: "loading" | "error" }
  | { status: "ready"; data: T; refresh?: "pending" | "error" };

function usePanel<T>(userId: string, load: (id: string, signal: AbortSignal) => Promise<T>, revision = 0) {
  const [request, setRequest] = useState<RequestState<T>>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;

    setRequest((previous) => previous.status === "ready"
      ? { ...previous, refresh: "pending" }
      : { status: "loading" });

    load(userId, signal).then(
      (data) => {
        if (!signal.aborted) setRequest({ status: "ready", data });
      },
      () => {
        if (!signal.aborted) setRequest((previous) => previous.status === "ready"
          ? { ...previous, refresh: "error" }
          : { status: "error" });
      },
    );

    return () => controller.abort();
  }, [userId, load, attempt, revision]);

  function retry() {
    setAttempt((previous) => previous + 1);
  }

  return { request, retry };
}

function ApiPanel<T>({ id, title, userId, load, revision, children }: {
  id: string;
  title: string;
  userId: string;
  load: (id: string, signal: AbortSignal) => Promise<T>;
  revision?: number;
  children: (data: T) => ReactNode;
}) {
  const { request, retry } = usePanel(userId, load, revision);
  const region = useRef<HTMLElement>(null);
  const panelName = title.toLowerCase();

  function retryPanel() {
    region.current?.focus({ preventScroll: true });
    retry();
  }

  return (
    <section ref={region} id={id} className="panel" tabIndex={-1} aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`}>{title}</h2>
      {request.status === "ready" ? (
        <>
          {children(request.data)}
          {request.refresh === "pending" && <p className="panel-loading" role="status">Updating {panelName}…</p>}
          {request.refresh === "error" && <PanelStatus title={panelName} status="error" retry={retryPanel} stale />}
        </>
      ) : <PanelStatus title={panelName} status={request.status} retry={retryPanel} />}
    </section>
  );
}

function PanelStatus({ title, status, retry, stale }: {
  title: string;
  status: "loading" | "error";
  retry: () => void;
  stale?: boolean;
}) {
  if (status === "loading") {
    return (
      <div className="panel-loading" role="status">
        <span>Loading {title}…</span>
        <span className="skeleton" aria-hidden="true" />
        <span className="skeleton" aria-hidden="true" />
      </div>
    );
  }

  return (
    <div className="panel-error">
      <p role="alert">{stale ? `Couldn’t update ${title}. Showing the last available data.` : `Couldn’t load ${title}.`}</p>
      <button className="secondary-button" type="button" onClick={retry}>
        Try again<span className="visually-hidden"> to load {title}</span>
      </button>
    </div>
  );
}

function ProfileSummary({ profile, persona }: { profile: User; persona: Persona }) {
  if (profile.id !== persona.id) {
    return <p className="sample-notice" role="status">Showing {profile.name}’s sample data for the {persona.name} profile.</p>;
  }

  return <p>{[profile.persona, profile.region].filter(Boolean).join(" · ") || "No profile details yet."}</p>;
}

const loadForecast = (userId: string, signal: AbortSignal) => api.forecast(userId, 56, signal);
const riskLabels = { low: "Low risk", medium: "Medium risk", high: "High risk" } as const;

function ForecastContent({ forecast, mockForecast }: { forecast: Forecast; mockForecast: boolean }) {
  const [cursor, setCursor] = useState(0);
  const [selectedRiskDate, setSelectedRiskDate] = useState<string | null>(null);
  const [whatIfSettings, setWhatIfSettings] = useState<WhatIfSettings | null>(null);
  const point = forecast.points[cursor];
  const highlightedDate = selectedRiskDate ?? point?.date;
  const selectedWarnings = forecast.risk_events.filter((risk) => risk.date === selectedRiskDate);
  const whatIf = mockForecast && point && whatIfSettings ? buildWhatIf(forecast, whatIfSettings) : null;

  function selectRisk(date: string) {
    setCursor(nearestPointIndex(forecast.points, date));
    setSelectedRiskDate(date);
  }

  return (
    <>
      {point ? (
        <div className="forecast-stage">
          <div className="forecast-summary">
            <div>
              <p className="forecast-label">
                Expected balance <time dateTime={point.date}>{dateLabel(point.date)}</time>
              </p>
              <p className="forecast-amount">{gbp(point.expected)}</p>
            </div>
            <div className="forecast-range">
              <span>Projected range</span>
              <strong>{gbp(point.low)} to {gbp(point.high)}</strong>
            </div>
          </div>
          <ul className="forecast-legend" aria-label="Chart legend">
            <li><span className="legend-expected" aria-hidden="true" /> Expected balance</li>
            <li><span className="legend-range" aria-hidden="true" /> Projected range</li>
            {whatIf && <li><span className="legend-what-if" aria-hidden="true" /> What-if balance</li>}
          </ul>
          <ForecastChart
            data={forecast}
            cursor={cursor}
            selectedRiskDate={highlightedDate}
            onCursorChange={(index) => {
              setCursor(index);
              setSelectedRiskDate(null);
            }}
            onRiskSelect={selectRisk}
            whatIf={whatIf}
          />
        </div>
      ) : <p className="panel-empty">No forecast data yet.</p>}
      {mockForecast && point && <WhatIfPanel settings={whatIfSettings} onChange={setWhatIfSettings} scenario={whatIf} />}
      {forecast.risk_events.length > 0 && (
        <>
          <ul className="risk-list" aria-label="Forecast warnings">
            {forecast.risk_events.map((risk) => (
              <li key={`${risk.date}-${risk.severity}-${risk.reason}`}
                data-severity={risk.severity} data-selected={risk.date === highlightedDate}>
                <Icon name="risk" />
                <div className="risk-copy">
                  <p className="risk-heading">
                    <strong>{riskLabels[risk.severity]}</strong>
                    <time dateTime={risk.date}>{dateLabel(risk.date)}</time>
                  </p>
                  <p>{risk.reason}</p>
                  {risk.date === selectedRiskDate && point && point.date !== risk.date && (
                    <p className="risk-note">Nearest forecast is {dateLabel(point.date)}.</p>
                  )}
                </div>
                {point && (
                  <button className="risk-jump" type="button"
                    aria-label={`Show balance near ${dateLabel(risk.date)}`}
                    onClick={() => selectRisk(risk.date)}>
                    <Icon name="forecast" />
                  </button>
                )}
              </li>
            ))}
          </ul>
          <p className="visually-hidden" role="status">
            {selectedWarnings.map((risk) => `${riskLabels[risk.severity]} on ${dateLabel(risk.date)}. ${risk.reason}`).join(" ")}
            {selectedRiskDate && point && ` Forecast for ${dateLabel(point.date)}: expected ${gbp(point.expected)}.`}
          </p>
        </>
      )}
      {forecast.assumptions.length > 0 && (
        <details className="forecast-assumptions">
          <summary>Forecast assumptions</summary>
          <ul>{forecast.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul>
        </details>
      )}
    </>
  );
}

function Dashboard({ persona, mock, demoPots, onDemoPotAdded }: {
  persona: Persona;
  mock?: ApiHealth["mock"];
  demoPots: Pot[];
  onDemoPotAdded: (pot: Pot) => void;
}) {
  const { request, retry } = usePanel(persona.id, api.user);
  const [potRevision, setPotRevision] = useState(0);
  const profileHeading = useRef<HTMLHeadingElement>(null);
  const visibleDemoPots = mock?.data ? demoPots : [];
  const forecastRevision = mock?.data === false && !mock.forecast ? potRevision : 0;
  const name = request.status === "ready" && request.data.id === persona.id
    ? request.data.name
    : persona.name;

  function refreshAfterSave(pot: Pot) {
    if (mock?.data !== false) onDemoPotAdded(pot);
    setPotRevision((previous) => previous + 1);
  }

  return (
    <>
      <div className="profile-summary">
        <h1 ref={profileHeading} tabIndex={-1}>Your money</h1>
        <div className="profile-line">
          <span className="profile-name">{name}</span>
          {request.status === "ready" ? <ProfileSummary profile={request.data} persona={persona} /> : (
            request.status === "loading" ? <p role="status">Loading profile…</p> : (
              <>
                <p role="alert">Couldn’t load the profile.</p>
                <button className="profile-retry" type="button" onClick={() => {
                  profileHeading.current?.focus({ preventScroll: true });
                  retry();
                }}>
                  Try again<span className="visually-hidden"> to load the profile</span>
                </button>
              </>
            )
          )}
        </div>
      </div>
      <div className="dashboard-grid">
        <ApiPanel id="spending" title="Safe to spend" userId={persona.id} load={api.safeToSpend} revision={potRevision}>
          {(data) => {
            const demoAdjustments = mock?.forecast ? visibleDemoPots : [];
            return (
              <>
                <SafeToSpendCard data={previewSafeToSpend(data, demoAdjustments)} demoPreview={demoAdjustments.length > 0} />
                {mock?.forecast && !mock.data && <p className="panel-empty">This amount uses the sample forecast.</p>}
              </>
            );
          }}
        </ApiPanel>
        <ApiPanel id="forecast" title="Time travel" userId={persona.id} load={loadForecast} revision={forecastRevision}>
          {(forecast) => <ForecastContent forecast={forecast} mockForecast={mock?.forecast === true} />}
        </ApiPanel>
        <ApiPanel id="pots" title="Savings pots" userId={persona.id} load={api.pots} revision={potRevision}>
          {(pots) => (
            <SavingsPots
              pots={mergeDemoPots(pots, visibleDemoPots)}
              userId={persona.id}
              onPotAdded={refreshAfterSave}
              demoOnly={mock?.data}
            />
          )}
        </ApiPanel>
        <ApiPanel id="alerts" title="Alerts" userId={persona.id} load={api.alerts} revision={forecastRevision}>
          {(alerts) => <AlertList alerts={alerts} />}
        </ApiPanel>
        {mock?.agent && !mock.data && !mock.forecast
          ? <PurchaseCheck userId={persona.id} />
          : <ChatPanel userId={persona.id} sampleReply={mock?.agent === true} />}
      </div>
      {persona.name === "Family" && <HouseholdPanel demo={mock?.data === true && mock.forecast} />}
    </>
  );
}

function currentSection() {
  const id = window.location.hash.slice(1);
  return id === householdSection.id ? id : sections.find((section) => section.id === id)?.id ?? "overview";
}

function SectionNav({ showHousehold }: { showHousehold: boolean }) {
  const [active, setActive] = useState(currentSection);
  const entries = showHousehold ? [...sections, householdSection] : sections;
  const selected = active === "household" && !showHousehold ? "overview" : active;

  useEffect(() => {
    function syncSection() {
      setActive(currentSection());
    }
    window.addEventListener("hashchange", syncSection);
    return () => window.removeEventListener("hashchange", syncSection);
  }, []);

  return (
    <nav className="section-nav" aria-label="Dashboard sections"
      style={{ "--section-count": entries.length } as CSSProperties}>
      {entries.map((section) => (
        <a key={section.id} href={`#${section.id}`} aria-current={selected === section.id ? "location" : undefined}>
          <Icon name={section.icon} />
          <span>{section.label}</span>
        </a>
      ))}
    </nav>
  );
}

export default function App() {
  const [persona, setPersona] = useState<Persona>(personas[0]);
  const [health, setHealth] = useState<ApiHealth>();
  const [demoPots, setDemoPots] = useState<Partial<Record<Persona["name"], Pot[]>>>({});

  useEffect(() => {
    const controller = new AbortController();
    api.health(controller.signal).then(
      (result) => {
        if (!controller.signal.aborted) setHealth(result);
      },
      () => {},
    );
    return () => controller.abort();
  }, []);

  return (
    <>
      <a className="skip-link" href="#overview">Skip to dashboard</a>
      <header className="app-header">
        <div className="toolbar">
          <a className="brand" href="#overview" aria-label="FinTime overview">
            <span className="brand-mark"><Icon name="brand" /></span>
            FinTime
          </a>
          <SectionNav showHousehold={persona.name === "Family"} />
          <fieldset className="persona-picker">
            <legend className="visually-hidden">Demo profile</legend>
            {personas.map((option) => (
              <label className="persona-option" key={option.name}>
                <input className="visually-hidden" type="radio" name="persona" checked={persona.name === option.name}
                  onChange={() => {
                    setPersona(option);
                    if (option.name === "Sam" && window.location.hash === "#household") {
                      window.location.hash = "overview";
                    }
                  }} />
                <span>{option.name}</span>
              </label>
            ))}
          </fieldset>
        </div>
      </header>
      <main className="app-shell" id="overview" tabIndex={-1}>
        <Dashboard
          key={persona.name}
          persona={persona}
          mock={health?.mock}
          demoPots={demoPots[persona.name] ?? []}
          onDemoPotAdded={(pot) => setDemoPots((previous) => ({
            ...previous,
            [persona.name]: mergeDemoPots(previous[persona.name] ?? [], [pot]),
          }))}
        />
      </main>
    </>
  );
}
