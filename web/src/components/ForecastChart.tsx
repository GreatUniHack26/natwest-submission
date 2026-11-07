import type { Forecast } from "../types";

// P4: placeholder SVG chart. Replace with a nicer one; keep the props.
export default function ForecastChart({ data, cursor }: { data: Forecast; cursor: number }) {
  const W = 600, H = 200, pts = data.points;
  const ys = pts.flatMap((p) => [p.low, p.high]);
  const min = Math.min(0, ...ys), max = Math.max(...ys);
  const x = (i: number) => (i / (pts.length - 1)) * W;
  const y = (v: number) => H - ((v - min) / (max - min || 1)) * H;
  const line = (k: "low" | "expected" | "high") => pts.map((p, i) => `${x(i)},${y(p[k])}`).join(" ");
  const band = [...pts.map((p, i) => `${x(i)},${y(p.high)}`), ...pts.map((p, i) => `${x(pts.length - 1 - i)},${y(pts[pts.length - 1 - i].low)}`)].join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", maxWidth: 700 }} role="img" aria-label="Balance forecast">
      <polygon points={band} fill="#1976d2" opacity={0.15} />
      <line x1={0} x2={W} y1={y(0)} y2={y(0)} stroke="#c62828" strokeDasharray="4" />
      <polyline points={line("expected")} fill="none" stroke="#1976d2" strokeWidth={2} />
      <line x1={x(cursor)} x2={x(cursor)} y1={0} y2={H} stroke="#555" />
    </svg>
  );
}
