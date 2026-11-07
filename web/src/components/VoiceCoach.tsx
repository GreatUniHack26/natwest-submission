import { useCallback, useEffect, useRef, useState } from "react";
import { Conversation, type Mode } from "@elevenlabs/client";
import { HttpError, voiceApi } from "../api";
import type { Tone } from "../types";
import Icon from "./Icon";
import "./VoiceCoach.css";

// Full-duplex voice coach on ElevenLabs Conversational AI. ElevenLabs streams ASR,
// turn-taking, barge-in and TTS over one WebSocket; FinTime supplies the prompt,
// live context (per-session overrides) and runs the tools (client tools -> our API).

type Phase = "idle" | "connecting" | "live";
interface Line { id: number; role: "user" | "agent"; text: string; interrupted?: boolean }

const VAD_SPEECH = 0.5; // server VAD score above which the user is talking
const INTERRUPT_FLASH_MS = 1600;
const TARGET_MS = 850;
const MAX_LINES = 40;

const TOOL_LABELS: Record<string, string> = {
  get_safe_to_spend: "Checking what’s safe to spend…",
  simulate_purchase: "Testing that purchase…",
  get_forecast: "Looking at your forecast…",
  get_alerts: "Checking your alerts…",
  run_twin_simulations: "Running 1,000 futures…",
  get_spending_forecast: "Checking this month’s spending…",
  get_deposit_ideas: "Looking at your pots…",
  plan_savings_goal: "Planning that goal…",
  plan_emergency_fund: "Planning an emergency fund…",
  plan_debt_payoff: "Planning debt payments…",
  get_economic_news: "Checking the news…",
};

function prefersReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

function errorText(error: unknown): string {
  if (error instanceof DOMException && (error.name === "NotAllowedError" || error.name === "SecurityError")) {
    return "Microphone access is blocked. Allow the mic for this site in your browser, then try again.";
  }
  if (error instanceof DOMException && error.name === "NotFoundError") {
    return "No microphone found. Plug one in and try again.";
  }
  if (error instanceof HttpError) {
    const raw = error.message.replace(/^\d+\s*/, "");
    try {
      const detail = (JSON.parse(raw) as { detail?: unknown }).detail;
      if (typeof detail === "string") return detail;
    } catch { /* not JSON */ }
    return error.status === 503 ? "The live voice coach is unavailable right now." : "Couldn’t start the voice coach.";
  }
  return error instanceof Error && error.message ? error.message : "Couldn’t start the voice coach.";
}

function median(values: number[]) {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : Math.round((sorted[mid - 1] + sorted[mid]) / 2);
}

export default function VoiceCoach({ userId, tone }: { userId: string; tone: Tone }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [mode, setMode] = useState<Mode>("listening");
  const [interrupted, setInterrupted] = useState(false);
  const [toolLabel, setToolLabel] = useState<string | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [latencies, setLatencies] = useState<number[]>([]);
  const [error, setError] = useState<string | null>(null);

  const conversation = useRef<Conversation | null>(null);
  const cancelled = useRef(false);
  const modeRef = useRef<Mode>("listening");
  const orb = useRef<HTMLSpanElement>(null);
  const log = useRef<HTMLOListElement>(null);
  const lineId = useRef(0);
  const interruptTimer = useRef<number>();
  // Latency: last moment server VAD heard the user (while we were listening) -> first agent audio chunk.
  const lastVoiceAt = useRef(0);
  const awaitingReply = useRef(false);

  const addLine = useCallback((role: Line["role"], text: string) => {
    const clean = text.trim();
    if (!clean) return;
    setLines((previous) => [...previous, { id: lineId.current++, role, text: clean }].slice(-MAX_LINES));
  }, []);

  const stop = useCallback(async () => {
    cancelled.current = true;
    const active = conversation.current;
    conversation.current = null;
    setPhase("idle");
    setToolLabel(null);
    if (active) await active.endSession().catch(() => undefined);
  }, []);

  const start = useCallback(async () => {
    cancelled.current = false;
    setError(null);
    setLines([]);
    setLatencies([]);
    setInterrupted(false);
    setPhase("connecting");
    try {
      // Ask for the mic first so a blocked mic gets a clear message before we mint a session.
      const probe = await navigator.mediaDevices.getUserMedia({ audio: true });
      probe.getTracks().forEach((track) => track.stop());

      const session = await voiceApi.session(userId, tone);
      if (cancelled.current) return;

      const clientTools = Object.fromEntries(session.client_tools.map((name) => [name, async (params: Record<string, unknown>) => {
        setToolLabel(TOOL_LABELS[name] ?? "Checking your numbers…");
        try {
          return JSON.stringify(await voiceApi.tool(userId, name, params ?? {}));
        } catch (toolError) {
          return JSON.stringify({ error: `${name} could not run: ${toolError instanceof Error ? toolError.message : "unknown error"}` });
        } finally {
          setToolLabel(null);
        }
      }]));

      const active = await Conversation.startSession({
        signedUrl: session.signed_url,
        connectionType: "websocket",
        overrides: { agent: { prompt: { prompt: session.prompt }, firstMessage: session.first_message, language: "en" } },
        clientTools,
        onConnect: () => setPhase("live"),
        onDisconnect: (details) => {
          conversation.current = null;
          setPhase("idle");
          setToolLabel(null);
          if (details.reason === "error") setError(details.message || "The voice connection dropped.");
        },
        onError: (message) => setError(message),
        onModeChange: ({ mode: next }) => {
          modeRef.current = next;
          setMode(next);
        },
        onMessage: ({ role, message }) => addLine(role, message),
        onAgentResponseCorrection: ({ original_agent_response, corrected_agent_response }) => {
          setLines((previous) => {
            const index = previous.map((line) => line.role === "agent" && line.text === original_agent_response.trim()).lastIndexOf(true);
            if (index < 0) return previous;
            const copy = [...previous];
            copy[index] = { ...copy[index], text: corrected_agent_response.trim() || copy[index].text, interrupted: true };
            return copy;
          });
        },
        onInterruption: () => {
          setInterrupted(true);
          window.clearTimeout(interruptTimer.current);
          interruptTimer.current = window.setTimeout(() => setInterrupted(false), INTERRUPT_FLASH_MS);
        },
        onVadScore: ({ vadScore }) => {
          if (vadScore >= VAD_SPEECH && modeRef.current === "listening") {
            lastVoiceAt.current = performance.now();
            awaitingReply.current = true;
          }
        },
        onAudio: () => {
          if (!awaitingReply.current) return;
          awaitingReply.current = false;
          const ms = Math.round(performance.now() - lastVoiceAt.current);
          if (ms > 0 && ms < 30_000) setLatencies((previous) => [...previous, ms].slice(-20));
        },
      });

      if (cancelled.current) {
        await active.endSession().catch(() => undefined);
        return;
      }
      conversation.current = active;
    } catch (startError) {
      if (!cancelled.current) setError(errorText(startError));
      setPhase("idle");
    }
  }, [addLine, tone, userId]);

  // End the call when the persona changes or the panel unmounts.
  useEffect(() => () => {
    window.clearTimeout(interruptTimer.current);
    void stop();
  }, [stop, userId]);

  // Drive the orb from the SDK's live input/output volume (skipped for reduced motion).
  useEffect(() => {
    if (phase !== "live" || prefersReducedMotion()) return;
    let frame = 0;
    const tick = () => {
      const active = conversation.current;
      const el = orb.current;
      if (active && el) {
        const level = (v: number) => Math.min(1, Math.sqrt(Math.max(0, v)) * 1.3).toFixed(3);
        el.style.setProperty("--voice-in", level(active.getInputVolume()));
        el.style.setProperty("--voice-out", level(active.getOutputVolume()));
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
      orb.current?.style.setProperty("--voice-in", "0");
      orb.current?.style.setProperty("--voice-out", "0");
    };
  }, [phase]);

  useEffect(() => {
    const el = log.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines]);

  const live = phase === "live";
  const status = phase === "connecting" ? "Connecting…"
    : !live ? "Tap to start a live voice chat. You can interrupt any time."
      : interrupted ? "You interrupted, go ahead"
        : toolLabel ?? (mode === "speaking" ? "Speaking" : "Listening");
  const last = latencies.length ? latencies[latencies.length - 1] : undefined;
  const state = !live ? phase : interrupted ? "interrupted" : mode;

  return (
    <div className="voice-coach" data-state={state}>
      <div className="voice-coach-top">
        <button type="button" className="voice-orb-button"
          onClick={() => (phase === "idle" ? void start() : void stop())}
          aria-pressed={phase !== "idle"}
          aria-label={phase === "idle" ? "Start live voice chat with your coach" : "End voice chat"}>
          <span className="voice-orb" ref={orb} aria-hidden="true">
            <span className="voice-orb-ring" />
            <span className="voice-orb-core"><Icon name={phase === "idle" ? "mic" : "stop"} /></span>
          </span>
        </button>
        <div className="voice-coach-copy">
          <p className="voice-coach-title">Talk to your coach</p>
          <p className="voice-status" aria-live="polite">{status}</p>
          {last !== undefined && (
            <p className="voice-latency" title="Time from when you stopped talking (last voice detected) to the coach’s first audio arriving.">
              <span className="voice-latency-label" data-fast={last <= TARGET_MS}>{last <= TARGET_MS ? "Fast" : "Slow"}</span>
              Reply in {last} ms{latencies.length > 1 ? ` · median ${median(latencies)} ms over ${latencies.length} turns` : ""}
            </p>
          )}
        </div>
      </div>
      {error && <p className="voice-error" role="alert">{error}</p>}
      {lines.length > 0 && (
        <ol className="voice-transcript" ref={log} role="log" aria-label="Voice conversation transcript">
          {lines.map((line) => (
            <li key={line.id} className="voice-line" data-role={line.role}>
              <span className="voice-line-who">{line.role === "user" ? "You" : "Coach"}</span>
              <span dir="auto">{line.text}</span>
              {line.interrupted && <span className="voice-line-cut">(cut off)</span>}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
