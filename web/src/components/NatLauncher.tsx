import { useEffect, useState } from "react";
import { api } from "../api";
import { dateLabel, gbp } from "../format";
import type { Alert } from "../types";
import Icon from "./Icon";

const friendly = (text: string) => text.replace(/\b(\d{4}-\d{2}-\d{2})\b/g, (iso) => dateLabel(iso));
const cap = (text: string) => (text ? text.charAt(0).toUpperCase() + text.slice(1) : text);
const pounds = (raw: string) => gbp(Math.round(Number(raw)));

/**
 * Turn the engine's alert text into short, plain sentences.
 * Falls back to the original wording when the pattern isn't recognised.
 */
export function plainAlert(alert: Alert): { title: string; detail: string; action: string } {
  const message = alert.message.trim();
  const action = alert.suggested_action.trim();

  const risk = message.match(/^(\d{4}-\d{2}-\d{2}): Expected balance falls below zero/i);
  if (risk) {
    return {
      title: `You may run short around ${dateLabel(risk[1])}`,
      detail: "Your balance is likely to drop below £0 on that day.",
      action: "Check the bills due before then and hold off on extras.",
    };
  }
  const over = message.match(/^(.+?): £([\d.,]+) spent month-to-date versus £([\d.,]+) expected/i);
  if (over) {
    return {
      title: `${cap(over[1])} is higher than usual`,
      detail: `${pounds(over[2].replace(/,/g, ""))} so far this month. Usually about ${pounds(over[3].replace(/,/g, ""))} by now.`,
      action: "Set a limit for the rest of the month.",
    };
  }
  const jump = message.match(/^(.+?): £([\d.,]+) in the last seven days; historical weekly average £([\d.,]+)/i);
  if (jump) {
    return {
      title: `${cap(jump[1])} jumped this week`,
      detail: `${pounds(jump[2].replace(/,/g, ""))} in 7 days. Usually about ${pounds(jump[3].replace(/,/g, ""))} a week.`,
      action: "Pick a spending limit for next week.",
    };
  }
  return { title: cap(friendly(message)), detail: "", action: cap(friendly(action)) };
}

/** Open a live voice chat with Nat: jump to the Nat screen and start talking. */
export function talkToNat() {
  try { sessionStorage.setItem("nat-autostart", "1"); } catch { /* ignore */ }
  if (window.location.hash === "#nat") window.dispatchEvent(new Event("nat:talk"));
  else window.location.hash = "nat";
}

/**
 * Nat speaks first: a notification slides in with the most urgent alert,
 * and a floating mic keeps a live voice chat one tap away on every screen.
 */
export default function NatLauncher({ userId, name }: { userId: string; name: string }) {
  const [alarm, setAlarm] = useState<Alert | null>(null);
  const [visible, setVisible] = useState(false);
  const onCoach = () => window.location.hash === "#nat";
  const [hidden, setHidden] = useState(onCoach());

  useEffect(() => {
    const sync = () => setHidden(onCoach());
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  useEffect(() => {
    const key = `nat-notified-${userId}`;
    let seen = false;
    try { seen = sessionStorage.getItem(key) === "1"; } catch { /* ignore */ }
    if (seen) return;
    const controller = new AbortController();
    let timer = 0;
    api.alerts(userId, controller.signal).then((alerts) => {
      const order = { high: 0, medium: 1, low: 2 } as const;
      const top = [...alerts].sort((a, b) => order[a.severity] - order[b.severity])[0];
      if (!top || controller.signal.aborted) return;
      setAlarm(top);
      timer = window.setTimeout(() => setVisible(true), 1200);
      try { sessionStorage.setItem(key, "1"); } catch { /* ignore */ }
    }, () => {});
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [userId]);

  useEffect(() => {
    if (!visible) return;
    const timer = window.setTimeout(() => setVisible(false), 12000);
    return () => window.clearTimeout(timer);
  }, [visible]);

  const copy = alarm ? plainAlert(alarm) : null;

  return (
    <>
      {alarm && copy && visible && (
        <div className="nat-toast" role="alert" data-severity={alarm.severity}>
          <button type="button" className="nat-toast-main" onClick={() => { setVisible(false); talkToNat(); }}>
            <span className="nat-avatar" aria-hidden="true">N</span>
            <span className="nat-toast-copy">
              <span className="nat-toast-meta"><span>Nat</span><span>now</span></span>
              <strong>{copy.title}</strong>
              <span>{name}, tap to talk it through with me.</span>
            </span>
          </button>
          <button type="button" className="nat-toast-close" aria-label="Dismiss" onClick={() => setVisible(false)}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 7l10 10M17 7 7 17" /></svg>
          </button>
        </div>
      )}
      {!hidden && (
        <button type="button" className="nat-fab" onClick={talkToNat} aria-label="Talk to Nat">
          <Icon name="mic" />
          <span>Talk to Nat</span>
        </button>
      )}
    </>
  );
}
