import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

/** Bottom sheet on phones, centred dialog on wider screens. Escape, backdrop tap and the close button dismiss it. */
export default function Sheet({ open, onClose, title, children }: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    const opener = document.activeElement as HTMLElement | null;
    panel.current?.focus({ preventScroll: true });
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); closeRef.current(); return; }
      if (e.key !== "Tab" || !panel.current) return;
      const items = panel.current.querySelectorAll<HTMLElement>("button, a[href], input, select, [tabindex]:not([tabindex='-1'])");
      if (!items.length) return;
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
      opener?.focus?.({ preventScroll: true });
    };
  }, [open]);

  if (!open) return null;
  return createPortal(
    <div className="sheet-layer">
      <div className="sheet-backdrop" onClick={onClose} />
      <div ref={panel} className="sheet" role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}>
        <span className="sheet-grabber" aria-hidden="true" />
        <div className="sheet-head">
          <h2 id={titleId}>{title}</h2>
          <button type="button" className="sheet-close" onClick={onClose} aria-label="Close">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 7l10 10M17 7 7 17" /></svg>
          </button>
        </div>
        <div className="sheet-body">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
