// Dev-only preview: http://localhost:5173/screens-preview.html?user=sam&screen=all
// Mounts the mockup screens without touching App.tsx. Not imported by the app.
import { useState } from "react";
import { createRoot } from "react-dom/client";
import "../theme.css";
import Landing from "./Landing";
import AffordScreen from "./AffordScreen";
import Transactions from "./Transactions";
import Tips from "./Tips";

const SCREENS = ["landing", "afford", "transactions", "tips"] as const;
type Screen = (typeof SCREENS)[number];

function Preview() {
  const q = new URLSearchParams(location.search);
  const [user, setUser] = useState(q.get("user") ?? "sam");
  const only = q.get("screen") as Screen | null;
  const show = (s: Screen) => !only || only === s || (only as string) === "all";
  const bar: React.CSSProperties = { position: "sticky", top: 0, zIndex: 10, background: "#3C1053", color: "#fff",
    padding: "8px 16px", font: "700 13px 'Nunito Sans', sans-serif", display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" };
  return (
    <div style={{ background: "#F5F5F7", minHeight: "100vh" }}>
      <div style={bar}>
        <span>Screens preview · user</span>
        {["sam", "alex", "maya"].map((u) => (
          <button key={u} onClick={() => setUser(u)} aria-pressed={u === user}
            style={{ minHeight: 32, borderRadius: 999, border: "1px solid #fff", background: u === user ? "#fff" : "transparent", color: u === user ? "#3C1053" : "#fff", padding: "0 12px" }}>
            {u}
          </button>
        ))}
        {SCREENS.map((s) => <a key={s} href={`#${s}`} style={{ color: "#F1EAF7" }}>{s}</a>)}
      </div>
      {show("landing") && <div id="landing"><Landing onPick={(id, tone) => { setUser(id); console.log("picked", id, tone); }} /></div>}
      {show("afford") && <div id="afford"><AffordScreen userId={user} onAskCoach={(m) => console.log("coach", m)} /></div>}
      {show("transactions") && <div id="transactions"><Transactions userId={user} /></div>}
      {show("tips") && <div id="tips"><Tips userId={user} /></div>}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<Preview />);
