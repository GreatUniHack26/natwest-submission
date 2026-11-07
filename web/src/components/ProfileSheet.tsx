import { useEffect, useState } from "react";
import Sheet from "./Sheet";

type Prefs = { large: boolean; calm: boolean; contrast: boolean };
const KEY = "fintime-a11y";

function load(): Prefs {
  try {
    return { large: false, calm: false, contrast: false, ...JSON.parse(localStorage.getItem(KEY) ?? "{}") };
  } catch {
    return { large: false, calm: false, contrast: false };
  }
}

export interface ProfileOption { key: string; label: string; detail: string; initial: string }

/** Header avatar. Opens a sheet to switch profile and change display settings. */
export default function ProfileSheet({ options, current, onPick }: {
  options: ProfileOption[];
  current: string;
  onPick: (key: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [prefs, setPrefs] = useState<Prefs>(load);
  const active = options.find((o) => o.key === current) ?? options[0];

  useEffect(() => {
    const html = document.documentElement;
    html.dataset.textSize = prefs.large ? "large" : "normal";
    html.dataset.motion = prefs.calm ? "reduce" : "full";
    html.dataset.contrast = prefs.contrast ? "high" : "normal";
    try { localStorage.setItem(KEY, JSON.stringify(prefs)); } catch { /* per-viewer convenience only */ }
  }, [prefs]);

  const toggle = (key: keyof Prefs) => setPrefs((p) => ({ ...p, [key]: !p[key] }));
  const settings: [keyof Prefs, string][] = [["large", "Larger text"], ["contrast", "Stronger contrast"], ["calm", "Less motion"]];

  return (
    <>
      <button type="button" className="profile-avatar" onClick={() => setOpen(true)}
        aria-label={`Profile: ${active.label}. Switch profile or change display settings`}>
        <span aria-hidden="true">{active.initial}</span>
      </button>
      <Sheet open={open} onClose={() => setOpen(false)} title="Profile and settings">
        <h3 className="sheet-section" id="profile-switch">Profile</h3>
        <ul className="rows block" role="radiogroup" aria-labelledby="profile-switch">
          {options.map((o) => (
            <li key={o.key}>
              <button type="button" className="row" role="radio" aria-checked={o.key === current}
                onClick={() => { onPick(o.key); setOpen(false); }}>
                <span className="row-icon" data-tone="brand" data-avatar="true" aria-hidden="true">{o.initial}</span>
                <span className="row-text">
                  <span className="row-title">{o.label}</span>
                  {o.detail && <span className="row-sub">{o.detail}</span>}
                </span>
                <span className="row-radio" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
        <h3 className="sheet-section" id="display-settings">Display</h3>
        <ul className="rows block" aria-labelledby="display-settings">
          {settings.map(([key, label]) => (
            <li key={key}>
              <div className="row">
                <span className="row-text"><span className="row-title" id={`pref-${key}`}>{label}</span></span>
                <button type="button" role="switch" className="switch" aria-checked={prefs[key]}
                  aria-labelledby={`pref-${key}`} onClick={() => toggle(key)} />
              </div>
            </li>
          ))}
        </ul>
      </Sheet>
    </>
  );
}
