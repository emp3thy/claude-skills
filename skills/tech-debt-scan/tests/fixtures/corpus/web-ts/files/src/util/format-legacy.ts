import { formatMoney } from "./format";

/** @deprecated use formatMoney */
export function legacyFormat(cents: number): string {
  return formatMoney(cents).replace("$", "USD ");
}
