import { addItem, total } from "../cart/cart";

test("total sums items", () => {
  const cart = { items: [] as { sku: string; qty: number }[] };
  addItem(cart, { sku: "A1", qty: 2 });
  expect(total(cart)).toBe(2000);
});
