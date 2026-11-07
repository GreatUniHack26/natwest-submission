import { useState } from "react";
import { api } from "../api";
import type { Tone } from "../types";

interface Msg { from: "me" | "coach"; text: string; numbers?: Record<string, number>; audio?: string | null }

export default function ChatPanel({ userId }: { userId: string }) {
  const [tone, setTone] = useState<Tone>("friendly");
  const [input, setInput] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([]);

  async function send() {
    if (!input.trim()) return;
    const text = input;
    setInput("");
    setMsgs((m) => [...m, { from: "me", text }]);
    try {
      const r = await api.chat(userId, text, tone);
      setMsgs((m) => [...m, { from: "coach", text: r.text, numbers: r.numbers_used, audio: r.audio_url }]);
    } catch (e) {
      setMsgs((m) => [...m, { from: "coach", text: `Sorry, something went wrong: ${e}` }]);
    }
  }

  return (
    <section>
      <h2>Ask your coach</h2>
      <label>
        Tone:{" "}
        <select value={tone} onChange={(e) => setTone(e.target.value as Tone)}>
          <option value="friendly">Friendly</option>
          <option value="direct">Direct</option>
          <option value="simple">Simple English</option>
        </select>
      </label>
      <div style={{ margin: "12px 0" }}>
        {msgs.map((m, i) => (
          <div key={i} style={{ textAlign: m.from === "me" ? "right" : "left", margin: "6px 0" }}>
            <div>{m.text}</div>
            {m.numbers && (
              <small style={{ color: "#666" }}>
                Numbers used: {Object.entries(m.numbers).map(([k, v]) => `${k}=${v}`).join(", ")}
              </small>
            )}
            {m.audio && <audio controls src={m.audio} />}
          </div>
        ))}
      </div>
      <input
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && send()}
        placeholder="Can I afford a £30 shirt?"
        style={{ width: "70%" }}
      />{" "}
      <button onClick={send}>Send</button>
    </section>
  );
}
