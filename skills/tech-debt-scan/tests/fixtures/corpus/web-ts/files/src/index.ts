import { addItem, Cart } from "./cart/cart";
import { checkout } from "./checkout/checkout";

export function main(): void {
  const cart: Cart = { items: [] };
  addItem(cart, { sku: "A1", qty: 1 });
  checkout(cart);
}
