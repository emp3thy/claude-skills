import { Cart, total } from "../cart/cart";
import { priceOf } from "../cart/pricing";
import { isEnabled } from "../flags";
import { legacyFormat } from "../util/format-legacy";

export function checkout(cart: Cart): string {
  if (isEnabled("newCheckout")) {
    return `new:${total(cart)}`;
  }
  const first = cart.items[0];
  const label = first ? legacyFormat(priceOf(first.sku)) : "";
  return `legacy:${label}`;
}
