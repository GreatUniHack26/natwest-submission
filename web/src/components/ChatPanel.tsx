import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type ChatTurn } from "../api";
import { gbp } from "../format";
import type { ChatReply, Tone } from "../types";
import Icon from "./Icon";
import VoiceCoach from "./VoiceCoach";
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
  | { status: "answered"; reply: ChatReply }
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

const HISTORY_TURNS = 6;

function historyFrom(exchanges: Exchange[], beforeId: number): ChatTurn[] {
  return exchanges
    .filter((exchange) => exchange.id < beforeId && exchange.status === "answered")
    .slice(-HISTORY_TURNS)
    .flatMap((exchange) => exchange.status === "answered"
      ? [{ role: "user" as const, content: exchange.question }, { role: "assistant" as const, content: exchange.reply.text }]
      : []);
}

export default function ChatPanel({ userId, sampleReply = false }: { userId: string; sampleReply?: boolean }) {
  const [tone, setTone] = useState<Tone>("friendly");
  const [input, setInput] = useState("");
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const nextId = useRef(0);
  const composer = useRef<HTMLInputElement>(null);
  const activeRequest = useRef<AbortController | null>(null);
  const exchangesRef = useRef<Exchange[]>([]);
  exchangesRef.current = exchanges;
  const pending = exchanges.some((exchange) => exchange.status === "pending");

  useEffect(() => () => activeRequest.current?.abort(), []);

  async function requestReply(message: Message, retry = false) {
    if (activeRequest.current) return;

    const controller = new AbortController();
    activeRequest.current = controller;
    const queued: Exchange = { ...message, status: "pending" };
    const history = historyFrom(exchangesRef.current, message.id);
    setExchanges((previous) => retry
      ? previous.map((exchange) => exchange.id === message.id ? queued : exchange)
      : [...previous, queued]);

    try {
      const reply = await api.chat(userId, message.question, message.tone, controller.signal, history);
      if (!controller.signal.aborted) {
        setExchanges((previous) => previous.map((exchange) => exchange.id === message.id
          ? { ...message, status: "answered", reply }
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
      <VoiceCoach userId={userId} tone={tone} />
      <div className="chat-options">
        {exchanges.length === 0 && (
          <button className="chat-starter" type="button" onClick={() => {
            setInput(starterQuestion);
            composer.current?.focus();
          }}>
            {starterQuestion}
          </button>
        )}
      </div>
      <div className="chat-log" role="log" aria-label="Conversation">
        {exchanges.map((exchange) => (
          <div className="chat-exchange" key={exchange.id}>
            <p className="chat-question" dir="auto">{exchange.question}</p>
            {exchange.status === "answered" && (
              <div className="chat-answer">
                <p dir="auto">{exchange.reply.text}</p>
                <FiguresUsed figures={exchange.reply.numbers_used} />
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
          value={input} onChange={(event) => setInput(event.target.value)}
          placeholder="Or type a message" />
        <button className="send-button" type="submit" aria-label="Send message" disabled={pending || !input.trim()}>
          <Icon name="send" />
        </button>
      </form>
    </section>
  );
}
