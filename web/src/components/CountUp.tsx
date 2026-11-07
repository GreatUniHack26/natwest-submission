import { useEffect, useRef, useState } from "react";
import { gbp } from "../format";

const reduceMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** Animates a money figure from its previous value (or 0) to `value`. Screen readers get the final value via the parent's label. */
export default function CountUp({ value, duration = 900 }: { value: number; duration?: number }) {
  const [shown, setShown] = useState(reduceMotion() ? value : 0);
  const from = useRef(reduceMotion() ? value : 0);

  useEffect(() => {
    if (reduceMotion()) {
      setShown(value);
      from.current = value;
      return;
    }
    const start = performance.now();
    const origin = from.current;
    let frame = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setShown(origin + (value - origin) * eased);
      if (t < 1) frame = requestAnimationFrame(tick);
      else from.current = value;
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value, duration]);

  const rounded = Number.isInteger(value) ? Math.round(shown) : Math.round(shown * 100) / 100;
  return <span aria-hidden="true">{gbp(rounded)}</span>;
}
