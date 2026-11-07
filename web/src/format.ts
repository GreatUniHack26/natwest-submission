const currency = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" });
const wholeCurrency = new Intl.NumberFormat("en-GB", {
  style: "currency", currency: "GBP", maximumFractionDigits: 0,
});
const shortDate = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });

export function gbp(amount: number) {
  return (Number.isInteger(amount) ? wholeCurrency : currency).format(amount);
}

export function dateLabel(date: string) {
  return shortDate.format(new Date(date));
}
