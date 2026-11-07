import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "../api";
import { gbp } from "../format";
import type { ChatReply, Tone } from "../types";
import Icon from "./Icon";
import "./ChatPanel.css";

const starterQuestion = "Can I afford a £30 shirt?";
const numberFormat = new Intl.NumberFormat("en-GB", { maximumSignificantDigits: 21 });
const moneyLabels = new Map([
  ["price", "Price"],
  ["amount", "Purchase amount"],
  ["balance", "Account balance"],
  ["pots_total", "Set aside in pots"],
  ["upcoming_bills", "Upcoming bills"],
  ["safe_to_spend", "Safe to spend"],
  ["safe_after", "Left after purchase"],
]);

interface Message {
  id: number;
  question: string;
  tone: Tone;
}

type Exchange = Message & (
  | { status: "pending" | "failed" }
  | { status: "answered"; reply: ChatReply; autoPlay: boolean }
);

function FiguresUsed({ figures }: { figures: ChatReply["numbers_used"] }) {
  const entries = Object.entries(figures);
  if (!entries.length) return null;

  return (
    <details className="chat-figures" open>
      <summary>Numbers used</summary>
      <dl>
        {entries.map(([key, amount]) => {
          const label = moneyLabels.get(key);
          return (
            <div key={key}>
              <dt>{label ?? key.replace(/[_-]+/g, " ")}</dt>
              <dd className="money">{label ? gbp(amount) : numberFormat.format(amount)}</dd>
            </div>
          );
        })}
      </dl>
    </details>
  );
}

function ReplyAudio({ src, autoPlay }: { src: string; autoPlay: boolean }) {
  const [unavailable, setUnavailable] = useState(false);

  if (unavailable) return <p className="chat-audio-note">Audio couldn’t be played.</p>;

  return (
    <audio aria-label="Play coach reply" controls autoPlay={autoPlay} preload="none" src={src}
      onError={() => setUnavailable(true)}>
      Your browser can’t play this audio.
    </audio>
  );
}

export default function ChatPanel({ userId, sampleReply = false }: { userId: string; sampleReply?: boolean }) {
  const [tone, setTone] = useState<Tone>("friendly");
  const [input, setInput] = useState("");
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const nextId = useRef(0);
  const composer = useRef<HTMLInputElement>(null);
  const autoPlayToggle = useRef<HTMLInputElement>(null);
  const activeRequest = useRef<AbortController | null>(null);
  const pending = exchanges.some((exchange) => exchange.status === "pending");

  useEffect(() => () => activeRequest.current?.abort(), []);

  async function requestReply(message: Message, retry = false) {
    if (activeRequest.current) return;

    const controller = new AbortController();
    activeRequest.current = controller;
    const queued: Exchange = { ...message, status: "pending" };
    setExchanges((previous) => retry
      ? previous.map((exchange) => exchange.id === message.id ? queued : exchange)
      : [...previous, queued]);

    try {
      const reply = await api.chat(userId, message.question, message.tone, controller.signal);
      if (!controller.signal.aborted) {
        const autoPlay = autoPlayToggle.current?.checked ?? false;
        setExchanges((previous) => previous.map((exchange) => exchange.id === message.id
          ? { ...message, status: "answered", reply, autoPlay }
          : exchange));
      }
    } catch {
      if (!controller.signal.aborted) {
        setExchanges((previous) => previous.map((exchange) => exchange.id === message.id
          ? { ...message, status: "failed" }
          : exchange));
      }
    } finally {
      activeRequest.current = null;
    }
  }

  function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = input.trim();
    if (!question || activeRequest.current) return;

    setInput("");
    void requestReply({ id: nextId.current++, question, tone });
  }

  return (
    <section id="coach" className="panel" tabIndex={-1} aria-labelledby="coach-title">
      <div className="coach-heading">
        <h2 id="coach-title">Ask your coach</h2>
        <label className="tone-control">
          Tone
          <select value={tone} onChange={(event) => setTone(event.target.value as Tone)}>
            <option value="friendly">Friendly</option>
            <option value="direct">Direct</option>
            <option value="simple">Simple English</option>
          </select>
        </label>
      </div>
      <p className="coach-description">
        {sampleReply ? "Demo replies use the original sample figures." : "Ask about a purchase, a bill, or anything in your forecast."}
      </p>
      <div className="chat-options">
        {exchanges.length === 0 && (
          <button className="chat-starter" type="button" onClick={() => {
            setInput(starterQuestion);
            composer.current?.focus();
          }}>
            {starterQuestion}
          </button>
        )}
        <label className="chat-voice-toggle">
          <input type="checkbox" ref={autoPlayToggle} />
          Autoplay voice replies
        </label>
      </div>
      <div className="chat-log" role="log" aria-label="Conversation">
        {exchanges.map((exchange) => (
          <div className="chat-exchange" key={exchange.id}>
            <p className="chat-question" dir="auto">{exchange.question}</p>
            {exchange.status === "answered" && (
              <div className="chat-answer">
                <p dir="auto">{exchange.reply.text}</p>
                <FiguresUsed figures={exchange.reply.numbers_used} />
                {exchange.reply.audio_url && <ReplyAudio src={exchange.reply.audio_url} autoPlay={exchange.autoPlay} />}
              </div>
            )}
            {exchange.status === "pending" && <p className="chat-pending">Waiting for your coach…</p>}
            {exchange.status === "failed" && (
              <div className="chat-delivery">
                <p>Couldn’t send this message.</p>
                <button className="secondary-button chat-retry" type="button"
                  disabled={pending} aria-label={`Retry sending: ${exchange.question}`}
                  onClick={() => {
                    composer.current?.focus();
                    void requestReply(exchange, true);
                  }}>
                  Retry
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
      <form className="chat-form" onSubmit={send}>
        <input ref={composer} aria-label="Message for your coach" enterKeyHint="send"
          value={input} onChange={(event) => setInput(event.target.value)} placeholder="Write a message" />
        <button className="send-button" type="submit" aria-label="Send message" disabled={pending || !input.trim()}>
          <Icon name="send" />
        </button>
      </form>
    </section>
  );
}
