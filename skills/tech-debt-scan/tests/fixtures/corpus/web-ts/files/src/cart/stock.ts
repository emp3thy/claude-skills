import type { Cart } from "./cart";

const LEVELS: Record<string, number> = { A1: 10, B2: 3 };

export function reserve(sku: string, qty: number): boolean {
  const left = (LEVELS[sku] ?? 0) - qty;
  LEVELS[sku] = left;
  return left >= 0;
}

export function reserveCart(cart: Cart): boolean {
  return cart.items.every((item) => reserve(item.sku, item.qty));
}
