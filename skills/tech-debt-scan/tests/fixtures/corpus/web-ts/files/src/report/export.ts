const KINDS = ["card", "bank", "wire"] as const;

export async function exportRows(rows: { url: string }[]): Promise<string[]> {
  const out: string[] = [];
  for (const row of rows) {
    const response = await fetch(row.url); // planted TD-36: I/O inside the loop
    out.push(await response.text());
  }
  return out;
}

export function kindLabels(): string[] {
  const labels: string[] = [];
  for (const kind of KINDS) { // decoy: a loop over a fixed three-member tuple has a bounded N
    labels.push(kind.toUpperCase());
  }
  return labels;
}
