import { reserve } from "./stock";

const PRICES: Record<string, number> = { A1: 1000, B2: 2500 };

export function priceOf(sku: string): number {
  reserve(sku, 0);
  return PRICES[sku] ?? 0;
}
