// Shareable demo page (/meet): promo video (plays on tap), Nat with Pete's money, Pete's home, and how it all works.
import { useRef, useState, type ReactNode } from "react";
import ChatPanel from "../components/ChatPanel";
import "./Meet.css";

const FEATURES = [
  { title: "Safe to spend today", text: "Balance minus money set aside in pots minus bills due before payday. The number that actually matters." },
  { title: "1,000 possible futures", text: "Nat replays your real spending days with random late pay and surprise costs, then tells you the odds of running short in 30, 60 and 90 days." },
  { title: "Alerts that come early", text: "One ranked feed in plain words: when you might run short, which spending is running hot, and good news too." },
  { title: "Pots that earn", text: "Money kept for rent stays untouchable. Nat shows what idle pot money could earn before it's due, with a safety check." },
  { title: "What-ifs", text: "“Holiday £1,600 in 4 weeks” or “hours cut by 30%” redraws the future and shows the new danger date." },
  { title: "Money you might be owed", text: "Checks your situation against UK schemes like Universal Credit and Council Tax Reduction, with official GOV.UK links." },
];

const STACK = [
  ["Forecast engine", "Python + FastAPI. Deterministic 90-day forecast and a seeded Monte Carlo simulation. The AI never does the maths."],
  ["Nat", "Claude with tool calling over the engine, a live snapshot of your situation, and guardrails. Every number shown under “Numbers used”."],
  ["Voice", "ElevenLabs Conversational AI: two-way streaming you can interrupt mid-sentence, same tools as text chat."],
  ["Live data", "n8n workflows pull UK cost-of-living news and GOV.UK guidance on tax and benefits."],
  ["App", "React + TypeScript, phone-first, NatWest colours. Synthetic Open Banking-style data for four people."],
];

function PromoVideo() {
  const video = useRef<HTMLVideoElement>(null);
  const [started, setStarted] = useState(false);

  function play() {
    const v = video.current;
    if (!v) return;
    v.muted = false;
    void v.play().catch(() => undefined);
    setStarted(true);
  }

  return (
    <div className="meet-video">
      <video ref={video} src="/nat-promo.mp4" poster="/nat-promo-poster.jpg" preload="metadata" playsInline
        controls={started} onPlay={() => setStarted(true)} />
      {!started && (
        <button type="button" className="meet-play" onClick={play} aria-label="Play the Nat video with sound">
          <span aria-hidden="true">▶</span> Watch the 1-minute video
        </button>
      )}
    </div>
  );
}

export default function Meet({ home }: { home: ReactNode }) {
  return (
    <div className="meet">
      <section className="meet-hero">
        <div className="meet-hero-in">
          <span className="meet-kicker">GreatUniHack 2026 · NatWest challenge</span>
          <h1>Meet Nat. A money assistant that sees trouble coming.</h1>
          <p>
            Nat simulates your next 90 days, warns you before you run short, protects money you've set aside,
            and talks it through with you by voice.
          </p>
          <PromoVideo />
        </div>
      </section>

      <section className="meet-section meet-talk" aria-labelledby="meet-talk-h">
        <div className="meet-head">
          <h2 id="meet-talk-h">Talk to Nat as Pete</h2>
          <p>
            Pete is a student with a part-time café job and a termly maintenance loan. Everything here is his
            (made-up) bank data. Tap the mic and talk, or type. You can interrupt Nat any time.
          </p>
        </div>
        <ChatPanel userId="pete" />
      </section>

      <section className="meet-section" aria-labelledby="meet-home-h">
        <div className="meet-head">
          <h2 id="meet-home-h">Pete's home screen</h2>
          <p>What Pete sees when he opens the app. Every number comes from the forecast engine.</p>
        </div>
        <div className="meet-home">{home}</div>
      </section>

      <section className="meet-section" aria-labelledby="meet-what-h">
        <div className="meet-head">
          <h2 id="meet-what-h">What Nat does</h2>
          <p>Built for the 1 in 4 UK adults with low financial resilience, especially people on shift work or irregular pay.</p>
        </div>
        <div className="meet-grid">
          {FEATURES.map((f) => (
            <div key={f.title} className="meet-card">
              <h3>{f.title}</h3>
              <p>{f.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="meet-section" aria-labelledby="meet-how-h">
        <div className="meet-head">
          <h2 id="meet-how-h">How it's built</h2>
        </div>
        <dl className="meet-stack">
          {STACK.map(([k, v]) => (
            <div key={k}><dt>{k}</dt><dd>{v}</dd></div>
          ))}
        </dl>
      </section>
    </div>
  );
}
