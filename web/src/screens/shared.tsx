// Shared bits for the mockup screens: data loading, the three data states, money/date
// formatting and the "How was this calculated?" side panel.
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { HttpError } from "../api";
import "./screens.css";

export const DISCLAIMER = "General information, not financial or tax advice.";

// ---------- formatting ----------
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WD = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MONTH_LONG = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
  "October", "November", "December"];

/** £1,234 or £12.40 (dp=2). Negative shows a true minus: −£5. */
export function money(n: number, dp = 0): string {
  const s = Math.abs(n).toLocaleString("en-GB", { minimumFractionDigits: dp, maximumFractionDigits: dp });
  return (n < 0 ? "−\u2060£" : "£") + s; // word joiner keeps − and £ together
}

/** Parse "2026-11-07" as a local calendar date (no timezone drift). */
export function parseIso(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
}
export function toIso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
export function addDays(iso: string, days: number): string {
  const d = parseIso(iso);
  d.setDate(d.getDate() + days);
  return toIso(d);
}
export const todayIso = () => toIso(new Date());
/** "7 Nov" */
export const dShort = (iso: string) => { const d = parseIso(iso); return `${d.getDate()} ${MON[d.getMonth()]}`; };
/** "Sat 7 Nov" */
export const dMid = (iso: string) => { const d = parseIso(iso); return `${WD[d.getDay()].slice(0, 3)} ${d.getDate()} ${MON[d.getMonth()]}`; };
/** "Saturday 7 November" */
export const dLong = (iso: string) => { const d = parseIso(iso); return `${WD[d.getDay()]} ${d.getDate()} ${MONTH_LONG[d.getMonth()]}`; };

export const cap = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

// ---------- data loading ----------
export type LoadState<T> =
  | { status: "loading" }
  | { status: "ok"; data: T }
  | { status: "missing"; detail?: string }
  | { status: "error"; detail?: string };

/** Load data with abort-on-change and a retry. `isMissing` turns an error into the missing-data state. */
export function useLoad<T>(
  load: (signal: AbortSignal) => Promise<T>,
  deps: unknown[],
  opts: { isMissing?: (data: T) => boolean; missingStatuses?: number[] } = {},
): [LoadState<T>, () => void, (fn: (prev: T) => T) => void] {
  const [state, setState] = useState<LoadState<T>>({ status: "loading" });
  const [tick, setTick] = useState(0);
  const optsRef = useRef(opts);
  optsRef.current = opts;

  useEffect(() => {
    const ctrl = new AbortController();
    setState({ status: "loading" });
    load(ctrl.signal).then(
      (data) => {
        if (ctrl.signal.aborted) return;
        setState(optsRef.current.isMissing?.(data) ? { status: "missing" } : { status: "ok", data });
      },
      (err: unknown) => {
        if (ctrl.signal.aborted) return;
        const missing = optsRef.current.missingStatuses ?? [503];
        if (err instanceof HttpError && missing.includes(err.status)) setState({ status: "missing", detail: err.message });
        else setState({ status: "error", detail: err instanceof Error ? err.message : String(err) });
      },
    );
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const retry = useCallback(() => setTick((t) => t + 1), []);
  const update = useCallback((fn: (prev: T) => T) => {
    setState((s) => (s.status === "ok" ? { status: "ok", data: fn(s.data) } : s));
  }, []);
  return [state, retry, update];
}

// ---------- icons ----------
/** Phosphor web icon. Decorative: meaning always comes from adjacent text. */
export function Icon({ name, className = "" }: { name: string; className?: string }) {
  return <i className={`ph ph-${name} fts-icon ${className}`} aria-hidden="true" />;
}

// ---------- the three data states ----------
export function Loading({ label = "Loading", rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div className="fts-loading" role="status" aria-live="polite">
      <span className="fts-visually-hidden">{label}…</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="fts-skel" style={{ width: `${92 - i * 14}%` }} />
      ))}
    </div>
  );
}

export function Missing({ title = "We don't have enough data.", children }: { title?: string; children?: ReactNode }) {
  return (
    <div className="fts-state">
      <span className="fts-chip fts-chip--lav"><Icon name="question" />We can't tell yet</span>
      <h2 className="fts-state-title">{title}</h2>
      <p className="fts-muted">{children ?? "We won't show a guessed number."}</p>
    </div>
  );
}

export function ErrorState({ onRetry, children }: { onRetry: () => void; children?: ReactNode }) {
  return (
    <div className="fts-state" role="alert">
      <span className="fts-chip fts-chip--danger"><Icon name="wifi-slash" />Connection problem</span>
      <p className="fts-state-body">{children ?? "We couldn't load this right now. Your money hasn't changed."}</p>
      <button type="button" className="fts-btn fts-btn--ghost" onClick={onRetry}>
        <Icon name="arrows-clockwise" />Try again
      </button>
    </div>
  );
}

/** Render the right state for a LoadState; `children` renders the loaded data. */
export function StateSwitch<T>({ state, onRetry, missing, loadingLabel, rows, children }: {
  state: LoadState<T>;
  onRetry: () => void;
  missing?: ReactNode;
  loadingLabel?: string;
  rows?: number;
  children: (data: T) => ReactNode;
}) {
  if (state.status === "loading") return <Loading label={loadingLabel} rows={rows} />;
  if (state.status === "error") return <ErrorState onRetry={onRetry} />;
  if (state.status === "missing") return <>{missing ?? <Missing />}</>;
  return <>{children(state.data)}</>;
}

// ---------- "How was this calculated?" ----------
export function CalcLink({ onClick, label = "How was this calculated?" }: { onClick: () => void; label?: string }) {
  return (
    <button type="button" className="fts-link" onClick={onClick}>
      <Icon name="question" />{label}
    </button>
  );
}

export interface CalcContent { title: string; steps: ReactNode[]; sources: ReactNode; unknown: ReactNode }

/** Right-hand dialog: steps, where the numbers come from, what we don't know. */
export function CalcPanel({ content, onClose }: { content: CalcContent; onClose: () => void }) {
  const panelRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); onClose(); return; }
      if (e.key !== "Tab" || !panelRef.current) return;
      const f = panelRef.current.querySelectorAll<HTMLElement>("button, a[href], input, [tabindex]:not([tabindex='-1'])");
      if (!f.length) return;
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); opener?.focus?.(); };
  }, [onClose]);

  return (
    <div className="fts fts-panel-wrap">
      <div className="fts-panel-backdrop" onClick={onClose} />
      <aside ref={panelRef} className="fts-panel" role="dialog" aria-modal="true" aria-labelledby="fts-panel-title">
        <div className="fts-panel-head">
          <h2 id="fts-panel-title">{content.title}</h2>
          <button ref={closeRef} type="button" className="fts-icon-btn" onClick={onClose} aria-label="Close">
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
              <path d="M4 4l10 10M14 4L4 14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </button>
        </div>
        <div className="fts-panel-body">
          <ol className="fts-steps">{content.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
          <section className="fts-panel-sec">
            <h3><Icon name="database" />Where the numbers come from</h3>
            <div>{content.sources}</div>
          </section>
          <section className="fts-panel-sec">
            <h3><Icon name="question" />What we don't know</h3>
            <div>{content.unknown}</div>
          </section>
          <p className="fts-fine">{DISCLAIMER}</p>
        </div>
      </aside>
    </div>
  );
}
