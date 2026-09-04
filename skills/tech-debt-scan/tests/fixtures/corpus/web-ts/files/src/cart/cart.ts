import { priceOf } from "./pricing";

export interface Item {
  sku: string;
  qty: number;
}

export interface Cart {
  items: Item[];
}

export function addItem(cart: Cart, item: Item): void {
  cart.items.push(item);
}

export function total(cart: Cart): number {
  return cart.items.reduce((sum, item) => sum + priceOf(item.sku) * item.qty, 0);
}
