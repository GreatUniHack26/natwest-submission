import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, type ApiHealth } from "./api";
import AlertList from "./components/AlertList";
import ChatPanel from "./components/ChatPanel";
import ForecastChart, { nearestPointIndex } from "./components/ForecastChart";
import HouseholdPanel from "./components/HouseholdPanel";
import Icon from "./components/Icon";
import PurchaseCheck from "./components/PurchaseCheck";
import SafeToSpendCard from "./components/SafeToSpendCard";
import CountUp from "./components/CountUp";
import SavingsPots from "./components/SavingsPots";
import DepositIdeas from "./components/DepositIdeas";
import TwinOdds from "./components/TwinOdds";
import TimeTravel from "./components/TimeTravel";
import ResilienceStrip from "./components/ResilienceStrip";
import DepositHero from "./components/DepositHero";
import ProfileSheet from "./components/ProfileSheet";
import Sheet from "./components/Sheet";
import Row from "./components/Row";
import NatLauncher from "./components/NatLauncher";
import { AlarmRows, loadAlarms } from "./components/NatAlarms";
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
import "./ui.css";

const personas = [
  { name: "Pete", id: "pete", label: "Pete", detail: "", initial: "P" },
  { name: "Sam", id: "sam", label: "Sam", detail: "Student, irregular income", initial: "S" },
  { name: "Alex", id: "alex", label: "Alex", detail: "Steady monthly salary", initial: "A" },
  { name: "Family", id: import.meta.env.VITE_FAMILY_USER_ID || "maya", label: "Maya & Dan", detail: "Household, two incomes", initial: "M" },
] as const;
type Persona = (typeof personas)[number];

const sections = [
  { id: "overview", label: "Home", icon: "overview" },
  { id: "forecast", label: "Forecast", icon: "forecast" },
  { id: "nat", label: "Nat", icon: "mic" },
  { id: "transactions", label: "Activity", icon: "activity" },
] as const;
// Reached from "More"
const moreIds = ["afford", "tips", "household"];
// Sections rendered as their own screen instead of a panel on the dashboard.
const screenIds = ["afford", "transactions", "tips", "start"] as const;
type ScreenId = (typeof screenIds)[number];
const screenFromHash = (): ScreenId | null => {
  const id = window.location.hash.slice(1);
  return (screenIds as readonly string[]).includes(id) ? (id as ScreenId) : null;
};

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

function ApiPanel<T>({ id, title, userId, load, revision, action, children }: {
  id: string;
  title: string;
  action?: ReactNode;
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
      <div className="panel-head">
        <h2 id={`${id}-title`}>{title}</h2>
        {action}
      </div>
      <div className="panel-body">
        {request.status === "ready" ? (
          <>
            {children(request.data)}
            {request.refresh === "pending" && <p className="panel-loading" role="status">Updating {panelName}…</p>}
            {request.refresh === "error" && <PanelStatus title={panelName} status="error" retry={retryPanel} stale />}
          </>
        ) : <PanelStatus title={panelName} status={request.status} retry={retryPanel} />}
      </div>
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

  return <p>{[profile.persona, profile.region].filter(Boolean).join(", ") || "No profile details yet."}</p>;
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
          Open the time machine
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

  const profileProblem = request.status === "error" ? (
    <div className="profile-line">
      <p role="alert">Couldn’t load the profile.</p>
      <button className="profile-retry" type="button" onClick={() => {
        profileHeading.current?.focus({ preventScroll: true });
        retry();
      }}>
        Try again<span className="visually-hidden"> to load the profile</span>
      </button>
    </div>
  ) : request.status === "ready" && request.data.id !== persona.id ? (
    <div className="profile-line"><ProfileSummary profile={request.data} persona={persona} /></div>
  ) : null;

  if (view === "home") {
    return (
      <>
        <HomeHero name={name.split(" ")[0]} userId={persona.id} revision={potRevision}
          demoPots={mock?.forecast ? visibleDemoPots : []} sampleForecast={Boolean(mock?.forecast && !mock.data)} />
        <div className="home-body">
          {profileProblem}
          {mock?.forecast === false && <ResilienceStrip userId={persona.id} />}
          {mock?.forecast === false && <DepositHero userId={persona.id} revision={potRevision} />}
          <div className="dashboard-grid">
            <div className="dash-col dash-col-left">
              <ApiPanel id="forecast-preview" title="Forecast" userId={persona.id} load={loadForecast} revision={forecastRevision}
                action={<a className="see-all" href="#forecast">See all</a>}>
                {(forecast) => <ForecastContent forecast={forecast} mockForecast={mock?.forecast === true} userId={persona.id} compact />}
              </ApiPanel>
              {mock?.forecast === false ? (
                <ApiPanel id="alerts" title="Alerts" userId={persona.id} load={loadAlarms} revision={forecastRevision}>
                  {(alarms) => <AlarmRows alarms={alarms} />}
                </ApiPanel>
              ) : (
                <ApiPanel id="alerts" title="Alerts" userId={persona.id} load={api.alerts} revision={forecastRevision}>
                  {(alerts) => <AlertList alerts={alerts} />}
                </ApiPanel>
              )}
            </div>
            <div className="dash-col dash-col-right">
              <ApiPanel id="pots" title="Pots" userId={persona.id} load={api.pots} revision={potRevision}>
                {(pots) => (
                  <SavingsPots
                    pots={mergeDemoPots(pots, visibleDemoPots)}
                    userId={persona.id}
                    onPotAdded={refreshAfterSave}
                    demoOnly={mock?.data}
                  />
                )}
              </ApiPanel>
              {mock?.forecast === false && <DepositIdeas userId={persona.id} revision={potRevision} />}
            </div>
          </div>
          {persona.name === "Family" && <HouseholdPanel demo={mock?.data === true && mock.forecast} />}
        </div>
      </>
    );
  }

  return (
    <>
      <div className="profile-summary">
        <h1 ref={profileHeading} tabIndex={-1}>{view === "future" ? "Forecast" : "Nat"}</h1>
        {profileProblem}
      </div>
      {view === "future" && (
        <div className="future-grid">
          <ApiPanel id="forecast" title="Your next 90 days" userId={persona.id} load={loadForecast} revision={forecastRevision}>
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
    </>
  );
}

/** Home hero: the purple header carries on with the one number that matters, safe to spend today. */
function HomeHero({ name, userId, revision, demoPots, sampleForecast }: {
  name: string;
  userId: string;
  revision: number;
  demoPots: Pot[];
  sampleForecast: boolean;
}) {
  const { request, retry } = usePanel(userId, api.safeToSpend, revision);
  const [open, setOpen] = useState(false);
  const data = request.status === "ready" ? previewSafeToSpend(request.data, demoPots) : null;

  return (
    <section className="home-hero" aria-labelledby="hero-hi">
      <div className="home-hero-in">
        <h1 className="hero-hi" id="hero-hi" tabIndex={-1}>Hi {name}</h1>
        <p className="hero-label" id="hero-label">Safe to spend today</p>
        {data ? (
          <>
            <p className="hero-amount" aria-describedby="hero-label" data-negative={data.safe_amount < 0}>
              <CountUp value={data.safe_amount} />
            </p>
            <p className="hero-line">
              {gbp(data.balance)} in account · {gbp(data.pots_total)} in pots · {gbp(data.upcoming_bills)} bills
            </p>
            <button type="button" className="hero-how" onClick={() => setOpen(true)}>How it’s worked out</button>
            <Sheet open={open} onClose={() => setOpen(false)} title="Safe to spend">
              <div className="block sheet-card" onClick={(e) => { if ((e.target as HTMLElement).closest("a")) setOpen(false); }}>
                <SafeToSpendCard data={data} demoPreview={demoPots.length > 0} />
              </div>
              {sampleForecast && <p className="sheet-note">This amount uses the sample forecast.</p>}
            </Sheet>
          </>
        ) : request.status === "error" ? (
          <div className="hero-error" role="alert">
            <p className="hero-line">Couldn’t load your balance.</p>
            <button type="button" className="hero-how" onClick={retry}>Try again</button>
          </div>
        ) : (
          <p className="hero-amount hero-loading" role="status"><span className="visually-hidden">Loading</span>…</p>
        )}
      </div>
    </section>
  );
}

function currentView(): View {
  const id = window.location.hash.slice(1);
  return id === "forecast" || id === "month" ? "future" : id === "nat" ? "coach" : "home";
}

function currentSection() {
  const id = window.location.hash.slice(1);
  if (moreIds.includes(id)) return "more";
  return sections.find((section) => section.id === id)?.id ?? "overview";
}

function SectionNav({ showHousehold }: { showHousehold: boolean }) {
  const [active, setActive] = useState(currentSection);
  const [moreOpen, setMoreOpen] = useState(false);

  useEffect(() => {
    function syncSection() {
      setActive(currentSection());
      setMoreOpen(false);
    }
    window.addEventListener("hashchange", syncSection);
    return () => window.removeEventListener("hashchange", syncSection);
  }, []);

  return (
    <nav className="section-nav" aria-label="Main">
      {sections.map((section) => (
        <a key={section.id} href={`#${section.id}`} className={section.id === "nat" ? "nav-nat" : undefined}
          aria-current={active === section.id ? "location" : undefined}>
          {section.id === "nat" ? <span className="nav-nat-disc"><Icon name="mic" /></span> : <Icon name={section.icon} />}
          <span>{section.label}</span>
        </a>
      ))}
      <button type="button" aria-current={active === "more" ? "location" : undefined} onClick={() => setMoreOpen(true)}>
        <i className="ph ph-dots-three-outline" aria-hidden="true" />
        <span>More</span>
      </button>
      <Sheet open={moreOpen} onClose={() => setMoreOpen(false)} title="More">
        <ul className="rows block">
          <li><Row icon="scales" title="Can I afford it?" subtitle="Check a purchase before you buy" href="#afford" /></li>
          <li><Row icon="hand-coins" title="Money you could get" subtitle="Help and discounts you may be owed" href="#tips" /></li>
          <li><Row icon="lightbulb" title="Tips" subtitle="Ways to spend less, picked for you" href="#tips" /></li>
          {showHousehold && <li><Row icon="users" title="Household" subtitle="Shared bills and who pays what" href="#household" /></li>}
        </ul>
      </Sheet>
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
    // Screens open at the top; dashboard anchors (#forecast, #nat…) scroll once the dashboard has mounted.
    const id = window.location.hash.slice(1);
    const timer = window.setTimeout(() => {
      if (screen || !id || ["overview", "forecast", "nat"].includes(id)) window.scrollTo({ top: 0 });
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
      <a className="skip-link" href="#overview">Skip to main content</a>
      <header className="app-header">
        <div className="toolbar">
          <a className="brand" href="#overview" aria-label="Nat home">
            <span className="brand-mark" aria-hidden="true">N</span>
            Nat
          </a>
          <SectionNav showHousehold={persona.name === "Family"} />
          <div className="toolbar-end">
            <ProfileSheet
              options={personas.map((p) => ({ key: p.name, label: p.label, detail: p.detail, initial: p.initial }))}
              current={persona.name}
              onPick={(key) => {
                const option = personas.find((p) => p.name === key) ?? personas[0];
                setPersona(option);
                if (option.name !== "Family" && window.location.hash === "#household") window.location.hash = "overview";
              }} />
          </div>
        </div>
      </header>
      {screen !== "start" && health?.mock.agent === false && <NatLauncher key={persona.id} userId={persona.id} name={persona.name === "Family" ? "Maya" : persona.name} />}
      <main className="app-shell" id="overview" tabIndex={-1} data-view={screen ?? view}>
        {screen === "start" && <Landing onPick={(userId) => pickPersona(userId)} />}
        {screen === "afford" && <AffordScreen key={persona.id} userId={persona.id} onAskCoach={() => { window.location.hash = "nat"; }} />}
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
