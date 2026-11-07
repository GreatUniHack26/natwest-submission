import type { SafeToSpend } from "../types";

const gbp = (n: number) => `${n < 0 ? "-" : ""}£${Math.abs(n).toFixed(0)}`;

export default function SafeToSpendCard({ data }: { data: SafeToSpend }) {
  return (
    <section style={{ border: "1px solid #ddd", borderRadius: 8, padding: 16 }}>
      <h2 style={{ margin: 0 }}>Safe to spend</h2>
      <p style={{ fontSize: 36, margin: "8px 0" }}>{gbp(data.safe_amount)}</p>
      <ul style={{ margin: 0, paddingLeft: 18 }}>
        {data.breakdown.map((b) => (
          <li key={b.label}>
            {b.label}: {gbp(b.amount)}
          </li>
        ))}
      </ul>
    </section>
  );
}
