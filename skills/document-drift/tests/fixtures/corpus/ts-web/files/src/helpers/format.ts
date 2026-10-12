export function formatPrice(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

export function formatDay(date: Date): string {
  return date.toISOString().slice(0, 10);
}
