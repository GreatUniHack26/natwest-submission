import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { api, HttpError } from "../api";
import { dateLabel, gbp } from "../format";
import type { Pot } from "../types";
import "./savings-pots.css";

interface FieldErrors {
  name?: string;
  amount?: string;
  date?: string;
}

function parsePence(value: string): number | null {
  if (!/^(?:\d+(?:\.\d{0,2})?|\.\d{1,2})$/.test(value)) return null;

  const [pounds, pennies = ""] = value.split(".");
  const pence = Number(pounds + pennies.padEnd(2, "0"));
  return Number.isSafeInteger(pence) && pence > 0 && Math.round((pence / 100) * 100) === pence
    ? pence
    : null;
}

// Demo "today" matches the backend's fixed DEMO_TODAY so countdowns agree with the forecast.
const DEMO_TODAY = Date.parse(import.meta.env.VITE_DEMO_TODAY ?? "2026-11-07");
function daysUntil(date: string) {
  return Math.round((Date.parse(date) - DEMO_TODAY) / 86_400_000);
}

function makePotId() {
  return Array.from(crypto.getRandomValues(new Uint32Array(4)), (part) =>
    part.toString(16).padStart(8, "0"),
  ).join("");
}

function failureMessage(error: unknown) {
  if (!(error instanceof HttpError)) return "Couldn’t add this pot. Try again.";
  if (error.status === 400 || error.status === 422) return "Check the pot details and try again.";
  if (error.status === 401 || error.status === 403) return "You don’t have access to add a pot here.";
  if (error.status === 404 || error.status === 501) return "Adding pots isn’t available right now.";
  if (error.status === 409) return "This pot conflicts with an existing pot. Check your savings pots.";
  return "Couldn’t add this pot. Try again.";
}

function mightHaveSaved(error: unknown) {
  return !(error instanceof HttpError) || error.status === 408 || error.status === 409
    || (error.status >= 500 && error.status !== 501);
}

export default function SavingsPots({ pots, userId, demoOnly, onPotAdded }: {
  pots: Pot[];
  userId: string;
  demoOnly?: boolean;
  onPotAdded: (pot: Pot) => void;
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [saveError, setSaveError] = useState("");
  const [savedName, setSavedName] = useState("");
  const formButton = useRef<HTMLButtonElement>(null);
  const nameInput = useRef<HTMLInputElement>(null);
  const amountInput = useRef<HTMLInputElement>(null);
  const dateInput = useRef<HTMLInputElement>(null);
  const invalidInput = useRef<HTMLInputElement | null>(null);
  const restoreFocus = useRef(false);
  const inFlight = useRef<AbortController | null>(null);
  const lastAttempt = useRef<Pot | null>(null);

  useEffect(() => {
    if (open) {
      nameInput.current?.focus();
    } else if (restoreFocus.current) {
      formButton.current?.focus();
      restoreFocus.current = false;
    }
  }, [open]);

  useEffect(() => {
    invalidInput.current?.focus();
    invalidInput.current = null;
  }, [errors]);

  useEffect(() => () => inFlight.current?.abort(), [userId]);

  function closeForm() {
    restoreFocus.current = true;
    setOpen(false);
  }

  function toggleForm() {
    if (open) {
      closeForm();
      return;
    }
    setErrors({});
    setSaveError("");
    setSavedName("");
    setOpen(true);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;

    const fields = new FormData(event.currentTarget);
    const name = String(fields.get("name") ?? "").trim();
    const pence = parsePence(String(fields.get("amount") ?? "").trim());
    const dueDate = String(fields.get("due-date") ?? "") || null;
    const nextErrors: FieldErrors = {};
    if (!name) nextErrors.name = "Enter a name for this pot.";
    if (pence === null) nextErrors.amount = "Enter an amount above £0 with up to two decimal places.";
    if (dateInput.current?.validity.badInput) nextErrors.date = "Enter a complete date or leave it blank.";

    setErrors(nextErrors);
    setSaveError("");
    if (nextErrors.name || pence === null || nextErrors.date) {
      invalidInput.current = nextErrors.name ? nameInput.current : pence === null ? amountInput.current : dateInput.current;
      return;
    }

    const amount = pence / 100;
    const previous = lastAttempt.current;
    const samePot = previous?.user_id === userId && previous.name === name
      && previous.amount === amount && previous.due_date === dueDate;
    const pot: Pot = {
      id: samePot ? previous.id : makePotId(),
      user_id: userId,
      name,
      amount,
      due_date: dueDate,
    };
    lastAttempt.current = pot;

    const controller = new AbortController();
    const { signal } = controller;
    inFlight.current = controller;
    setSaving(true);

    let saved: Pot | undefined;
    let saveFailure: unknown;
    try {
      saved = await api.addPot(pot, signal);
    } catch (error) {
      saveFailure = error;
      if (!signal.aborted && demoOnly !== true && mightHaveSaved(error)) {
        // A lost response can leave a successful write behind. Look for the same ID before offering a retry.
        saved = await api.pots(userId, signal).then(
          (items) => items.find((item) => item.id === pot.id),
          () => undefined,
        );
      }
    }
    if (signal.aborted) return;

    inFlight.current = null;
    setSaving(false);
    if (saved?.user_id !== userId) {
      setSaveError(failureMessage(saveFailure));
      return;
    }

    lastAttempt.current = null;
    setSavedName(saved.name);
    closeForm();
    onPotAdded(saved);
  }

  const notice = savedName && (demoOnly === true ? `${savedName} added for this demo session.`
    : demoOnly === false ? `${savedName} added.` : `${savedName} submitted.`);

  return (
    <>
      {pots.length > 0 ? (
        <ul className="grouped-list">
          {pots.map((pot) => (
            <li key={pot.id} className="pot-row savings-pot-row">
              <div>
                <strong>{pot.name}</strong>
                <p>
                  <span className="pot-lock">Protected</span>
                  {pot.due_date
                    ? <> · due <time dateTime={pot.due_date}>{dateLabel(pot.due_date)}</time>{daysUntil(pot.due_date) > 0 && ` (in ${daysUntil(pot.due_date)} days)`}</>
                    : " · for emergencies"}
                </p>
              </div>
              <strong className="money">{gbp(pot.amount)}</strong>
            </li>
          ))}
        </ul>
      ) : <p className="panel-empty">Add a pot to set money aside for something specific.</p>}
      <div className="pots-actions">
        <button type="button" className="pots-button pots-button-secondary" ref={formButton}
          aria-expanded={open} aria-controls={open ? `${id}-form` : undefined}
          disabled={saving} onClick={toggleForm}>
          Add a pot
        </button>
      </div>
      <p className="pots-notice" role="status">{saving ? "Adding your pot…" : notice}</p>
      {open && (
        <form id={`${id}-form`} className="pots-form" aria-label="New savings pot"
          noValidate onSubmit={submit}>
          <div className="pots-field pots-field-wide">
            <label htmlFor={`${id}-name`}>Pot name</label>
            <input id={`${id}-name`} name="name" ref={nameInput} required readOnly={saving}
              aria-invalid={Boolean(errors.name)} aria-describedby={errors.name ? `${id}-name-error` : undefined} />
            {errors.name && <span className="pots-error" id={`${id}-name-error`}>{errors.name}</span>}
          </div>
          <div className="pots-field">
            <label htmlFor={`${id}-amount`}>Amount (£)</label>
            <input id={`${id}-amount`} name="amount" inputMode="decimal" ref={amountInput} required readOnly={saving}
              aria-invalid={Boolean(errors.amount)} aria-describedby={errors.amount ? `${id}-amount-error` : undefined} />
            {errors.amount && <span className="pots-error" id={`${id}-amount-error`}>{errors.amount}</span>}
          </div>
          <div className="pots-field">
            <label htmlFor={`${id}-date`}>Due date <span className="pots-optional">(optional)</span></label>
            <input id={`${id}-date`} name="due-date" type="date" ref={dateInput} readOnly={saving}
              aria-invalid={Boolean(errors.date)} aria-describedby={errors.date ? `${id}-date-error` : undefined} />
            {errors.date && <span className="pots-error" id={`${id}-date-error`}>{errors.date}</span>}
          </div>
          {saveError && <p className="pots-error pots-field-wide" role="alert">{saveError}</p>}
          <div className="pots-form-actions pots-field-wide">
            <button type="button" className="pots-button pots-button-secondary" disabled={saving} onClick={closeForm}>
              Cancel
            </button>
            <button type="submit" className="pots-button pots-button-primary" aria-disabled={saving}>
              {saving ? "Adding…" : "Add pot"}
            </button>
          </div>
        </form>
      )}
    </>
  );
}
