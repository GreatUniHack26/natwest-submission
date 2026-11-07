import { useEffect, useId, useRef, useState } from "react";

type Prefs = { large: boolean; calm: boolean; contrast: boolean };
const KEY = "fintime-a11y";

function load(): Prefs {
  try {
    return { large: false, calm: false, contrast: false, ...JSON.parse(localStorage.getItem(KEY) ?? "{}") };
  } catch {
    return { large: false, calm: false, contrast: false };
  }
}

/** Inclusion controls: bigger text, calmer motion, stronger contrast, and a shortcut to talk instead of read. */
export default function AccessibilityMenu() {
  const [prefs, setPrefs] = useState<Prefs>(load);
  const [open, setOpen] = useState(false);
  const id = useId();
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const html = document.documentElement;
    html.dataset.textSize = prefs.large ? "large" : "normal";
    html.dataset.motion = prefs.calm ? "reduce" : "full";
    html.dataset.contrast = prefs.contrast ? "high" : "normal";
    try { localStorage.setItem(KEY, JSON.stringify(prefs)); } catch { /* per-viewer convenience only */ }
  }, [prefs]);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !root.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, [open]);

  const toggle = (key: keyof Prefs) => setPrefs((p) => ({ ...p, [key]: !p[key] }));

  return (
    <div className="a11y" ref={root}>
      <button type="button" className="a11y-button" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}
        aria-label="Accessibility options">
        <span aria-hidden="true">Aa</span>
      </button>
      {open && (
        <div className="a11y-menu" id={id} role="group" aria-label="Accessibility options">
          <p className="a11y-title">Make FinTime easier to use</p>
          <label><input type="checkbox" checked={prefs.large} onChange={() => toggle("large")} /> Larger text</label>
          <label><input type="checkbox" checked={prefs.contrast} onChange={() => toggle("contrast")} /> Stronger contrast</label>
          <label><input type="checkbox" checked={prefs.calm} onChange={() => toggle("calm")} /> Calmer screen (less motion)</label>
          <a className="a11y-link" href="#nat" onClick={() => setOpen(false)}>Prefer talking? Talk to Nat</a>
          <p className="a11y-note">Ask Nat to use “Simple” words if you prefer.</p>
        </div>
      )}
    </div>
  );
}
