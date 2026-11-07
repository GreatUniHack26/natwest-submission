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
import DepositIdeas from "./components/DepositIdeas";
import TwinOdds from "./components/TwinOdds";
import TimeTravel from "./components/TimeTravel";
import ResilienceStrip from "./components/ResilienceStrip";
import AccessibilityMenu from "./components/AccessibilityMenu";
import Landing from "./screens/Landing";
import AffordScreen from "./screens/AffordScreen";
import Transactions from "./screens/Transactions";
import Tips from "./screens/Tips";
import SpendingForecast from "./components/SpendingForecast";
import WhatIfPanel from "./components/WhatIfPanel";
import { dateLabel, gbp } from "./format";
import { mergeDemoPots, previewSafeToSpend } from "./potPreview";
import type { Forecast, Pot, User } from "./types";
import { buildWhatIf, type WhatIfSettings } from "./whatIf";
import "./dashboard.css";
import "./twin.css";
import "./theme.css";

const personas = [
  { name: "Sam", id: "sam" },
  { name: "Alex", id: "alex" },
  { name: "Family", id: import.meta.env.VITE_FAMILY_USER_ID || "maya" },
] as const;
type Persona = (typeof personas)[number];

const sections = [
  { id: "overview", label: "Home", icon: "overview" },
  { id: "forecast", label: "Future", icon: "forecast" },
  { id: "afford", label: "Afford?", icon: "afford" },
  { id: "coach", label: "Nat", icon: "coach" },
  { id: "transactions", label: "Activity", icon: "activity" },
  { id: "tips", label: "Tips", icon: "tips" },
] as const;
// Sections rendered as their own screen instead of a panel on the dashboard.
const screenIds = ["afford", "transactions", "tips", "start"] as const;
type ScreenId = (typeof screenIds)[number];
const screenFromHash = (): ScreenId | null => {
  const id = window.location.hash.slice(1);
  return (screenIds as readonly string[]).includes(id) ? (id as ScreenId) : null;
};
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

function ForecastContent({ forecast, mockForecast, userId, compact = false }: { forecast: Forecast; mockForecast: boolean; userId: string; compact?: boolean }) {
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

  if (compact && !mockForecast) {
    return (
      <>
        <TimeTravel userId={userId} compact />
        <a className="spending-link" href="#forecast">
          <Icon name="forecast" />
          Open your time machine: what-ifs and 1,000 futures
          <Icon name="chevron" />
        </a>
      </>
    );
  }

  return (
    <>
      {!mockForecast ? <TimeTravel userId={userId} /> : point ? (
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
      {!mockForecast && <TwinOdds userId={userId} revision={forecast.points.length} />}
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

type View = "home" | "future" | "coach";

function Dashboard({ persona, mock, demoPots, onDemoPotAdded, view }: {
  view: View;
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
        <h1 ref={profileHeading} tabIndex={-1}>{view === "future" ? "Time machine" : view === "coach" ? "Talk to Nat" : "Your money"}</h1>
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
      {view === "home" && mock?.forecast === false && <ResilienceStrip userId={persona.id} />}
      {view === "home" && (
        <div className="dashboard-grid">
          <div className="dash-col dash-col-left">
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
          <ApiPanel id="pots" title="Savings pots" userId={persona.id} load={api.pots} revision={potRevision}>
            {(pots) => (
              <>
                <SavingsPots
                  pots={mergeDemoPots(pots, visibleDemoPots)}
                  userId={persona.id}
                  onPotAdded={refreshAfterSave}
                  demoOnly={mock?.data}
                />
                {mock?.forecast === false && <DepositIdeas userId={persona.id} revision={potRevision} />}
              </>
            )}
          </ApiPanel>
          </div>
          <div className="dash-col dash-col-right">
          <ApiPanel id="forecast-preview" title="Your time machine" userId={persona.id} load={loadForecast} revision={forecastRevision}>
            {(forecast) => <ForecastContent forecast={forecast} mockForecast={mock?.forecast === true} userId={persona.id} compact />}
          </ApiPanel>
          <ApiPanel id="alerts" title="Alerts" userId={persona.id} load={api.alerts} revision={forecastRevision}>
            {(alerts) => <AlertList alerts={alerts} />}
          </ApiPanel>
          </div>
        </div>
      )}
      {view === "future" && (
        <div className="future-grid">
          <ApiPanel id="forecast" title="Your time machine" userId={persona.id} load={loadForecast} revision={forecastRevision}>
            {(forecast) => <ForecastContent forecast={forecast} mockForecast={mock?.forecast === true} userId={persona.id} />}
          </ApiPanel>
          {mock?.forecast === false && (
            <ApiPanel id="month" title="This month’s spending" userId={persona.id} load={api.spending} revision={potRevision}>
              {(spending) => <SpendingForecast data={spending} />}
            </ApiPanel>
          )}
        </div>
      )}
      {view === "coach" && (
        <div className="coach-screen">
          {mock?.agent && !mock.data && !mock.forecast
            ? <PurchaseCheck userId={persona.id} />
            : <ChatPanel userId={persona.id} sampleReply={mock?.agent === true} />}
        </div>
      )}
      {view === "home" && persona.name === "Family" && <HouseholdPanel demo={mock?.data === true && mock.forecast} />}
    </>
  );
}

function currentView(): View {
  const id = window.location.hash.slice(1);
  return id === "forecast" || id === "month" ? "future" : id === "coach" ? "coach" : "home";
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
  const [view, setView] = useState<View>(currentView);
  const [screen, setScreen] = useState<ScreenId | null>(() => {
    // First visit in this tab starts at the persona picker, like the mockup.
    try {
      if (!window.location.hash && !sessionStorage.getItem("fintime-started")) return "start";
    } catch { /* storage unavailable: skip the picker */ }
    return screenFromHash();
  });

  useEffect(() => {
    const sync = () => {
      setScreen(screenFromHash());
      setView(currentView());
    };
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  useEffect(() => {
    // Screens open at the top; dashboard anchors (#forecast, #coach…) scroll once the dashboard has mounted.
    const id = window.location.hash.slice(1);
    const timer = window.setTimeout(() => {
      if (screen || !id || ["overview", "forecast", "coach"].includes(id)) window.scrollTo({ top: 0 });
      else document.getElementById(id)?.scrollIntoView({ block: "start" });
    }, 60);
    return () => window.clearTimeout(timer);
  }, [screen, view]);

  function pickPersona(userId: string) {
    const match = personas.find((p) => p.id === userId) ?? personas[0];
    setPersona(match);
    try { sessionStorage.setItem("fintime-started", "1"); } catch { /* ignore */ }
    window.location.hash = "overview";
    setScreen(null);
  }
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
          <div className="toolbar-end">
          <AccessibilityMenu />
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
        </div>
      </header>
      <main className="app-shell" id="overview" tabIndex={-1}>
        {screen === "start" && <Landing onPick={(userId) => pickPersona(userId)} />}
        {screen === "afford" && <AffordScreen key={persona.id} userId={persona.id} onAskCoach={() => { window.location.hash = "coach"; }} />}
        {screen === "transactions" && <Transactions key={persona.id} userId={persona.id} />}
        {screen === "tips" && <Tips key={persona.id} userId={persona.id} />}
        {screen === null && <Dashboard
          view={view}
          key={persona.name}
          persona={persona}
          mock={health?.mock}
          demoPots={demoPots[persona.name] ?? []}
          onDemoPotAdded={(pot) => setDemoPots((previous) => ({
            ...previous,
            [persona.name]: mergeDemoPots(previous[persona.name] ?? [], [pot]),
          }))}
        />}
      </main>
    </>
  );
}
