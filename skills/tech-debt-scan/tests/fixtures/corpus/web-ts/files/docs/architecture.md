# Architecture

`src/cart` owns items and totals, `src/checkout` owns the flow. Pricing and
stock currently import each other through `src/cart/stock.ts`.
