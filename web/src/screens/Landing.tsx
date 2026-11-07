// Persona picker (mockup "landing"). Names, persona and region come from GET /users/{id};
// traits and "What FinTime does for you" are product copy from the mockup.
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Tone, User } from "../types";
import { ErrorState, Icon, useLoad } from "./shared";
import "./Landing.css";

interface PersonaMeta {
  id: string;
  householdName?: string; // shown when the user has a household
  traits: string[];
  does: string;
  av: "lav" | "purple" | "deep";
}

const PERSONAS: PersonaMeta[] = [
  { id: "pete", traits: ["Student", "Part-time cafe job", "Termly maintenance"],
    does: "Connects a year of spending to what you can afford next", av: "lav" },
  { id: "sam", traits: ["Irregular income", "Student", "Renting"], does: "Plans around gaps between paydays", av: "lav" },
  { id: "alex", traits: ["Fixed salary", "Paid monthly", "Renting"], does: "Finds the headroom in a steady budget", av: "purple" },
  { id: "maya", householdName: "Maya & Dan", traits: ["Household", "Shift & agency work", "Two incomes"],
    does: "Keeps the whole household's bills covered", av: "deep" },
];

const TONES: [Tone, string, string][] = [["friendly", "Friendly", "smiley"], ["direct", "Direct", "target"], ["simple", "Simple", "text-aa"]];

const FEATURES = [
  { icon: "chart-line", title: "Time machine", text: "Travel to any date in the next 90 days and see your likely balance, with a range when pay is uncertain." },
  { icon: "scales", title: "Can I afford it?", text: "Test a purchase before you make it. Waiting or not buying are always shown as good choices too." },
  { icon: "chat-circle-text", title: "A coach that knows you", text: "Ask in your own words. Every answer shows the numbers it used, and you can listen instead of read." },
  { icon: "shield-check", title: "Shows its working", text: "Every figure explains how it was worked out. When data is missing, we say so instead of guessing." },
];

interface Card { meta: PersonaMeta; user: User; name: string; initials: string }

function initialsOf(name: string) {
  return name.split("&").map((p) => p.trim().charAt(0).toUpperCase()).join("&");
}

/** Full-screen promo video that starts playing straight away (muted, as browsers require), with a sound toggle. */
function LandingVideo() {
  const video = useRef<HTMLVideoElement>(null);
  const [muted, setMuted] = useState(true);

  useEffect(() => {
    const v = video.current;
    if (!v) return;
    v.muted = true;
    void v.play().catch(() => undefined);
  }, []);

  function toggleSound() {
    const v = video.current;
    if (!v) return;
    v.muted = !v.muted;
    if (!v.muted && v.currentTime > v.duration - 1) v.currentTime = 0;
    void v.play().catch(() => undefined);
    setMuted(v.muted);
  }

  return (
    <section className="ftl-video" aria-label="Meet Nat">
      <video ref={video} src="/nat-promo.mp4" poster="/nat-promo-poster.jpg" autoPlay muted loop playsInline preload="auto" />
      <div className="ftl-video-bar">
        <button type="button" className="ftl-video-sound" onClick={toggleSound} aria-pressed={!muted}>
          {muted ? "Tap for sound" : "Mute"}
        </button>
        <a className="ftl-video-next" href="#ftl-pick-h" onClick={(e) => {
          e.preventDefault();
          document.getElementById("ftl-pick-h")?.scrollIntoView({ behavior: "smooth", block: "start" });
        }}>Try Nat <span aria-hidden="true">↓</span></a>
      </div>
    </section>
  );
}

export default function Landing({ onPick }: { onPick: (userId: string, tone?: Tone) => void }) {
  const [state, retry] = useLoad<{ cards: Card[]; failed: string[] }>(async (signal) => {
    const res = await Promise.allSettled(PERSONAS.map((p) => api.user(p.id, signal)));
    const cards: Card[] = [];
    const failed: string[] = [];
    res.forEach((r, i) => {
      const meta = PERSONAS[i];
      if (r.status === "fulfilled") {
        const name = r.value.household_id && meta.householdName ? meta.householdName : r.value.name;
        cards.push({ meta, user: r.value, name, initials: initialsOf(name) });
      } else failed.push(meta.id);
    });
    if (!cards.length) throw new Error("No personas could be loaded");
    return { cards, failed };
  }, []);

  const [pick, setPick] = useState("pete");
  const [tone, setTone] = useState<Tone | null>(null);
  const cards = state.status === "ok" ? state.data.cards : [];
  const picked = cards.find((c) => c.user.id === pick) ?? cards[0];
  const shownTone: Tone | undefined = tone ?? picked?.user.tone;

  return (
    <div className="fts fts-landing">
      <LandingVideo />

      <div className="ftl-body">
        <div className="fts-card ftl-picker">
          <div className="ftl-picker-head">
            <div className="ftl-picker-title">
              <h2 id="ftl-pick-h">Pick your money persona</h2>
              <p>Pick a person to see Nat with their money. You can switch any time.</p>
            </div>
            <div className="ftl-tone">
              <span id="ftl-tone-l">How FinTime talks to you</span>
              <div className="fts-seg" role="radiogroup" aria-labelledby="ftl-tone-l">
                {TONES.map(([id, label, icon]) => (
                  <button key={id} type="button" role="radio" aria-checked={shownTone === id} onClick={() => setTone(id)}>
                    <Icon name={icon} />{label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {state.status === "loading" && (
            <div className="ftl-grid" role="status" aria-live="polite">
              <span className="fts-visually-hidden">Loading personas…</span>
              {PERSONAS.map((p) => (
                <div key={p.id} className="ftl-card ftl-card--skel" aria-hidden="true">
                  <div className="ftl-card-top"><span className="ftl-av fts-skel" /><div className="fts-skel" style={{ width: "60%" }} /></div>
                  <div className="fts-skel" style={{ width: "80%" }} />
                  <div className="fts-skel" style={{ width: "50%" }} />
                </div>
              ))}
            </div>
          )}
          {(state.status === "error" || state.status === "missing") && (
            <ErrorState onRetry={retry}>We couldn't load the personas. Check the FinTime server is running, then try again.</ErrorState>
          )}
          {state.status === "ok" && (
            <>
              <div className="ftl-grid" role="radiogroup" aria-labelledby="ftl-pick-h">
                {cards.map((c) => {
                  const selected = picked?.user.id === c.user.id;
                  return (
                    <div key={c.user.id} className={`ftl-card${selected ? " is-selected" : ""}`} onClick={() => setPick(c.user.id)}>
                      <div className="ftl-card-top">
                        <span className={`ftl-av ftl-av--${c.meta.av}`} aria-hidden="true">{c.initials}</span>
                        <div className="ftl-card-id">
                          <button type="button" role="radio" aria-checked={selected} className="ftl-card-name"
                            onClick={(e) => { e.stopPropagation(); setPick(c.user.id); }}>
                            {c.name}
                          </button>
                          <span className="ftl-card-desc">{c.user.persona}, {c.user.region}</span>
                        </div>
                      </div>
                      {selected && <span className="ftl-selected"><Icon name="check" />Selected</span>}
                      <div className="ftl-traits">
                        {c.meta.traits.map((t) => <span key={t}>{t}</span>)}
                      </div>
                      <div className="ftl-does">
                        <span>What FinTime does for you</span>
                        <strong>{c.meta.does}</strong>
                      </div>
                      <button type="button" className="fts-btn ftl-try"
                        onClick={(e) => { e.stopPropagation(); onPick(c.user.id, tone ?? undefined); }}>
                        Try as {c.name}<Icon name="arrow-right" />
                      </button>
                    </div>
                  );
                })}
              </div>
              {state.data.failed.length > 0 && (
                <p className="fts-fine" role="status">
                  Some personas couldn't be loaded. <button type="button" className="fts-link" onClick={retry}>Try again</button>
                </p>
              )}
            </>
          )}
        </div>

        <div className="ftl-features">
          {FEATURES.map((f) => (
            <div key={f.title} className="ftl-feature">
              <span className="fts-bubble"><Icon name={f.icon} /></span>
              <h3>{f.title}</h3>
              <p>{f.text}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
