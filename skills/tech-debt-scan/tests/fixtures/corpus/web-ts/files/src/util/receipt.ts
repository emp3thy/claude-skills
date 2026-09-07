export interface ReceiptLine {
  sku: string;
  label: string;
  quantity: number;
  unitCents: number;
}

export interface ReceiptTotals {
  subtotalCents: number;
  taxCents: number;
  totalCents: number;
}

const TAX_RATE = 0.0825;

export function computeTotals(lines: ReceiptLine[]): ReceiptTotals {
  let subtotalCents = 0;
  for (const line of lines) {
    subtotalCents += line.quantity * line.unitCents;
  }
  const taxCents = Math.round(subtotalCents * TAX_RATE);
  const totalCents = subtotalCents + taxCents;
  return { subtotalCents, taxCents, totalCents };
}

export function formatReceipt(lines: ReceiptLine[]): string {
  const rows: string[] = [];
  for (const line of lines) {
    const lineTotal = line.quantity * line.unitCents;
    rows.push(`${line.label} x${line.quantity} $${(lineTotal / 100).toFixed(2)}`);
  }
  const totals = computeTotals(lines);
  rows.push(`Subtotal: $${(totals.subtotalCents / 100).toFixed(2)}`);
  rows.push(`Tax: $${(totals.taxCents / 100).toFixed(2)}`);
  rows.push(`Total: $${(totals.totalCents / 100).toFixed(2)}`);
  return rows.join("\n");
}
