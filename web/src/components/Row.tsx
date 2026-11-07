import type { MouseEvent, ReactNode } from "react";

export type Tone = "brand" | "good" | "warn" | "bad" | "plain";

/** Small status chip: colour plus an icon, never colour alone. */
export function Chip({ tone = "plain", children }: { tone?: Tone; children: ReactNode }) {
  const icon = tone === "good" ? "check-circle" : tone === "warn" || tone === "bad" ? "warning" : "info";
  return (
    <span className="chip" data-tone={tone}>
      <i className={`ph-bold ph-${icon}`} aria-hidden="true" />{children}
    </span>
  );
}

/**
 * One list row: 40px icon circle, title, one subtitle line, value on the right, chevron.
 * Renders as a link, a button or plain content depending on what it is given.
 */
export default function Row({ icon, avatar, tone = "brand", title, subtitle, value, valueTone, chip, href, onClick, chevron, trailing, label }: {
  icon?: string;
  avatar?: string;
  tone?: Tone;
  title: ReactNode;
  subtitle?: ReactNode;
  value?: ReactNode;
  valueTone?: Tone;
  chip?: ReactNode;
  href?: string;
  onClick?: (event: MouseEvent) => void;
  chevron?: boolean;
  trailing?: ReactNode;
  label?: string;
}) {
  const showChevron = chevron ?? Boolean(href || onClick);
  const body = (
    <>
      {(icon || avatar) && (
        <span className="row-icon" data-tone={tone} data-avatar={avatar ? "true" : undefined} aria-hidden="true">
          {avatar ?? <i className={`ph ph-${icon}`} />}
        </span>
      )}
      <span className="row-text">
        <span className="row-title">{title}</span>
        {subtitle && <span className="row-sub">{subtitle}</span>}
      </span>
      {(value !== undefined || chip) && (
        <span className="row-end">
          {value !== undefined && <span className="row-value" data-tone={valueTone}>{value}</span>}
          {chip}
        </span>
      )}
      {trailing}
      {showChevron && <i className="ph ph-caret-right row-chevron" aria-hidden="true" />}
    </>
  );
  if (href) return <a className="row" href={href} onClick={onClick} aria-label={label}>{body}</a>;
  if (onClick) return <button type="button" className="row" onClick={onClick} aria-label={label}>{body}</button>;
  return <div className="row">{body}</div>;
}
