const paths = {
  brand: "M6 3.5h12M6 20.5h12M8 3.5v3a4 4 0 0 0 1.4 3l2.6 2.5 2.6-2.5a4 4 0 0 0 1.4-3v-3M8 20.5v-3a4 4 0 0 1 1.4-3l2.6-2.5 2.6 2.5a4 4 0 0 1 1.4 3v3M10 18h4",
  overview: "M3.5 10.5 12 3.5l8.5 7v9a1 1 0 0 1-1 1H4.5a1 1 0 0 1-1-1zM9 20.5v-6h6v6",
  forecast: "M4 4v15a1 1 0 0 0 1 1h15M7.5 15l4-4 3 2 5-6M16 7h3.5v3.5",
  pots: "M4 9h16v10a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1zM3 5h18v4H3zM10 13h4",
  household: "M15 19v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2m18 0v-2a4 4 0 0 0-3-3.9M12 7a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm3-3a3 3 0 0 1 0 6",
  alerts: "M5 16c1.6-1.4 2-3.3 2-6a5 5 0 1 1 10 0c0 2.7.4 4.6 2 6H5ZM10 20h4",
  coach: "M20.5 11a8.5 8.5 0 0 1-8.5 8.5 9 9 0 0 1-3.3-.6L4 20l1.2-4.3A8.5 8.5 0 1 1 20.5 11ZM8.5 11h.1m3.35 0h.1m3.35 0h.1",
  risk: "M10.5 4.5a1.7 1.7 0 0 1 3 0l7 12.5a1.7 1.7 0 0 1-1.5 2.5H5A1.7 1.7 0 0 1 3.5 17zM12 9v4m0 3h.01",
  chevron: "m9 5 7 7-7 7",
  send: "M12 19V5m-5 5 5-5 5 5",
} as const;

export default function Icon({ name }: { name: keyof typeof paths }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={paths[name]} />
    </svg>
  );
}
