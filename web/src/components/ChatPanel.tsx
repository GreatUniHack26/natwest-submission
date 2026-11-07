import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type ChatTurn } from "../api";
import { gbp } from "../format";
import type { ChatReply, Detail, Tone } from "../types";
import Icon from "./Icon";
import VoiceCoach from "./VoiceCoach";
import "./ChatPanel.css";

const starterQuestion = "Can I afford a £30 shirt?";
const natOpener = "Hey, it’s me, Nat! I know your spending habits and income patterns inside out, "
  + "and I’ve already lived 1,000 versions of your next 90 days. Ask me anything.";
const detailOptions: { value: Detail; label: string }[] = [
  { value: "concise", label: "Concise" },
  { value: "detailed", label: "Detailed" },
];
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
  detail: Detail;
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

type ReplyBlock = { kind: "p"; text: string } | { kind: "ul"; items: string[] };

const BULLET = /^\s*[-•*]\s+/;

/** Split reply text into paragraphs and bullet lists. Plain text only, so React escapes everything. */
function replyBlocks(text: string): ReplyBlock[] {
  const blocks: ReplyBlock[] = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    const last = blocks[blocks.length - 1];
    if (BULLET.test(line)) {
      const item = line.replace(BULLET, "");
      if (last?.kind === "ul") last.items.push(item);
      else blocks.push({ kind: "ul", items: [item] });
    } else {
      blocks.push({ kind: "p", text: line });
    }
  }
  return blocks;
}

function ReplyText({ text }: { text: string }) {
  return (
    <div className="chat-reply" dir="auto">
      {replyBlocks(text).map((block, index) => block.kind === "ul"
        ? <ul key={index}>{block.items.map((item, i) => <li key={i} dir="auto">{item}</li>)}</ul>
        : <p key={index} dir="auto">{block.text}</p>)}
    </div>
  );
}

function DetailToggle({ value, onChange }: { value: Detail; onChange: (detail: Detail) => void }) {
  return (
    <fieldset className="detail-toggle">
      <legend className="visually-hidden">Reply length</legend>
      {detailOptions.map((option) => (
        <label className="detail-option" key={option.value}>
          <input type="radio" name="coach-detail" value={option.value}
            checked={value === option.value} onChange={() => onChange(option.value)} />
          <span>{option.label}</span>
        </label>
      ))}
    </fieldset>
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
  const [detail, setDetail] = useState<Detail>("concise");
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
      const reply = await api.chat(userId, message.question, message.tone, controller.signal, history, message.detail);
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
    void requestReply({ id: nextId.current++, question, tone, detail });
  }

  return (
    <section id="nat" className="panel" tabIndex={-1} aria-labelledby="coach-title">
      <div className="coach-heading">
        <h2 id="coach-title">Ask Nat</h2>
        <div className="coach-controls">
          <DetailToggle value={detail} onChange={setDetail} />
          <label className="tone-control">
            Tone
            <select value={tone} onChange={(event) => setTone(event.target.value as Tone)}>
              <option value="friendly">Friendly</option>
              <option value="direct">Direct</option>
              <option value="simple">Simple English</option>
            </select>
          </label>
        </div>
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
        {exchanges.length === 0 && (
          <div className="chat-exchange">
            <div className="chat-answer"><ReplyText text={natOpener} /></div>
          </div>
        )}
        {exchanges.map((exchange) => (
          <div className="chat-exchange" key={exchange.id}>
            <p className="chat-question" dir="auto">{exchange.question}</p>
            {exchange.status === "answered" && (
              <div className="chat-answer">
                <ReplyText text={exchange.reply.text} />
                <FiguresUsed figures={exchange.reply.numbers_used} />
              </div>
            )}
            {exchange.status === "pending" && <p className="chat-pending">Nat is thinking…</p>}
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
        <input ref={composer} aria-label="Message for Nat" enterKeyHint="send"
          value={input} onChange={(event) => setInput(event.target.value)}
          placeholder="Or type a message to Nat" />
        <button className="send-button" type="submit" aria-label="Send message" disabled={pending || !input.trim()}>
          <Icon name="send" />
        </button>
      </form>
    </section>
  );
}
