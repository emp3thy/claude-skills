import { priceOf } from "../cart/pricing";

describe("priceOf", () => {
  it("returns zero for unknown skus", () => {
    expect(priceOf("nope")).toBe(0);
  });
  it.skip("applies bulk pricing", () => {
    expect(priceOf("A1")).toBe(900);
  });
});
