---
schema_version: 2
scan_date: 2026-09-09
root: C:\Users\gethi\AppData\Local\Temp\live-web-ts-veg88obo
total_files: 18
total_loc: 228
languages:
- javascript
- markdown
- typescript
preset: balanced
families_run:
- complex-units
- god-classes
- duplication
- dead-code
- error-masking
- test-gaps
- half-finished
- migration
- dependency-debt
- doc-drift
- architecture
- test-quality
- pipeline-infra
families_skipped:
- family: security
  reason: no leads
tools_run:
- jscpd
- knip
- lizard
- madge
tools_absent:
- actionlint (absent)
- gitleaks (absent)
- hadolint (skipped)
- osv-scanner (absent)
- ruff (skipped)
- vulture (skipped)
git_available: true
counts:
  candidates: 40
  quote_failed: 0
  verified: 35
  tier_a: 18
  tier_b: 8
  tier_c: 13
  unverified: 5
  rejected: 1
  suppressed: 0
---

# Tech-debt scan - 2026-09-09

Scanned `C:\Users\gethi\AppData\Local\Temp\live-web-ts-veg88obo` - 18 files, 228 LOC across: javascript, markdown, typescript.

Review each finding below. To act on one, change its `status:` from `pending` to
`approved`, `rejected`, or `accepted` (add a `reason:` and an optional `until:` ISO
date), then run `/tech-debt-promote`.

Top hotspots: `src/api/client-admin.ts` (80.0), `src/api/client.ts` (42.9), `src/util/receipt-legacy.ts` (8.6), `src/util/receipt.ts` (8.6), `src/__tests__/pricing.spec.ts` (5.7).

Top coupled pairs: `src/api/client-admin.ts` <-> `src/api/client.ts` (shared 4, ratio 0.889).

# Top 5

## Ownership gaps in src/api/client-admin.ts

```yaml
status: pending
slug: ownership-gaps-in-src-api-client-admin-ts
fingerprint: 882069e3ebcd041d
tier: A
priority: 7.5
family: ownership
category: ownership
debt_type: knowledge-process
type_id: TD-16
severity: 4
effort: M
diff: NEW
```

### Proof

verified by construction

### Evidence

- `src/api/client-admin.ts` (whole file)

```
src/api/client-admin.ts: 100% of lines by one author, 1 author(s) in the window
```

### Signals

- hotspot score 80.0, churn 4, coupling pairs 1, fan-in 0 (approximate)
- confirmed by: rule:ownership.knowledge-island

### Remediation

Add src/api/client-admin.ts to CODEOWNERS (or the team's existing ownership mapping) naming at least a second reviewer so future changes aren't gated on a single person. If the file is retired per finding cef81f7bb42878f2, resolve that removal first and drop this entry instead of assigning a second owner to dead code. If the file is kept, have the second owner do a walkthrough of getAdminJson/adminEnabled with the original author and record the rationale (token handling, retry header, timeout) in a short doc or PR description so knowledge isn't sited in one head.

### Acceptance criteria

- [ ] CODEOWNERS (or equivalent ownership file) lists at least two owners for src/api/client-admin.ts, or the file no longer exists in the tree
- [ ] If kept, a PR or doc exists showing a second engineer reviewed and can explain the file's retry/timeout/auth logic
- [ ] No single-author-only ownership record remains for this path after the change

## src/api/client-admin.ts is an unused file, including an undefined flag

```yaml
status: pending
slug: src-api-client-admin-ts-is-an-unused-file-including-an-undefined
fingerprint: cef81f7bb42878f2
tier: A
priority: 7.5
family: dead-code
category: dead-code
debt_type: code
type_id: TD-09
severity: 3
effort: S
diff: NEW
```

### Proof

Grepped src for getAdminJson/adminEnabled/client-admin: only declaration sites in client-admin.ts:6,20 match, no importers. index.ts only wires cart/checkout, no admin path. flags.ts:1-5 defines FLAGS = {newCheckout, betaBanner} only; 'adminPanel' is absent, so isEnabled('adminPanel') always falls through to the ?? false default at flags.ts:8. No comment or ticket marks this as a deliberate kill switch, and it isn't an entry point or test. Matches dead-code family cleanly.

### Evidence

- `src/api/client-admin.ts:6-9`

```
export async function getAdminJson(path: string): Promise<unknown> {
  const headers = { Authorization: `Bearer ${token}`, "X-Retry": "3" };
  try {
    const response = await fetch(`${BASE}${path}`, {
```

- `src/api/client-admin.ts:20-22`

```
export function adminEnabled(): boolean {
  return isEnabled("adminPanel");
}
```

### Signals

- hotspot score 80.0, churn 4, coupling pairs 1, fan-in 0 (approximate)
- confirmed by: coupling, hotspot, pattern:flag-sdk, scout:dead-code, tool:knip

### Remediation

Delete src/api/client-admin.ts entirely: getAdminJson has no callers and adminEnabled() guards a flag ('adminPanel') that doesn't exist in flags.ts, so it always evaluates false via the ?? false fallback. Confirm via grep that adminEnabled, getAdminJson, and ADMIN_TOKEN are not referenced anywhere else (env docs, deploy configs, tests) before removing. If the admin panel is a planned near-term feature rather than abandoned work, replace this deletion with adding the 'adminPanel' entry to flags.ts and wiring an actual import site instead.

### Acceptance criteria

- [ ] src/api/client-admin.ts no longer exists in the repository
- [ ] grep across the repo (src, tests, CI config, docs) for getAdminJson, adminEnabled, and ADMIN_TOKEN returns no remaining references
- [ ] Build (tsc) and test suite pass after removal
- [ ] No new 'adminPanel' flag or importer was left half-wired

## src/api/client.ts is an unused file with zero callers

```yaml
status: pending
slug: src-api-client-ts-is-an-unused-file-with-zero-callers
fingerprint: 39ff2c7e77aa20a8
tier: A
priority: 6.1089
family: dead-code
category: dead-code
debt_type: code
type_id: TD-09
severity: 3
effort: S
diff: NEW
```

### Proof

Grep for getJson/client across src finds only the declaration at client.ts:6; index.ts:1-2 imports solely from ./cart/cart and ./checkout/checkout. No dynamic import, string-based dispatch, or route table exists in this small app. Not an entry point (index.ts is) and not a runner-discovered test (only src/__tests__/cart.test.ts exists, no client.ts reference). knip's finding is corroborated by manual search.

### Evidence

- `src/api/client.ts:6-11`

```
export async function getJson(path: string): Promise<unknown> {
  const headers = { Authorization: `Bearer ${token}`, "X-Retry": "3" };
  try {
    const response = await fetch(`${BASE}${path}`, { headers });
    return await response.json();
  } catch (e) {}
```

### Signals

- hotspot score 42.9, churn 5, coupling pairs 1, fan-in 0 (approximate)
- confirmed by: coupling, hotspot, pattern:flag-sdk, scout:dead-code, tool:knip

### Remediation

Delete src/api/client.ts. getJson is never imported; index.ts only wires ./cart/cart and ./checkout/checkout, and the only test file is src/__tests__/cart.test.ts. Confirm via grep that getJson and API_TOKEN have no other references (including CI env vars, deploy scripts, or docs) before deleting. If this client was meant to replace an existing fetch path, wire it into that call site instead of deleting; otherwise remove it outright.

### Acceptance criteria

- [ ] src/api/client.ts no longer exists in the repository
- [ ] grep across the repo (src, tests, CI config, docs) for getJson and API_TOKEN returns no remaining references
- [ ] Build (tsc) and test suite pass after removal

## Ownership gaps in src/api/client.ts

```yaml
status: pending
slug: ownership-gaps-in-src-api-client-ts
fingerprint: 3c1370050f312692
tier: A
priority: 6.1089
family: ownership
category: ownership
debt_type: knowledge-process
type_id: TD-16
severity: 4
effort: M
diff: NEW
```

### Proof

verified by construction

### Evidence

- `src/api/client.ts` (whole file)

```
src/api/client.ts: 100% of lines by one author, 1 author(s) in the window
```

### Signals

- hotspot score 42.9, churn 5, coupling pairs 1, fan-in 0 (approximate)
- confirmed by: rule:ownership.knowledge-island

### Remediation

Same treatment as the client-admin.ts ownership gap: this is moot if src/api/client.ts is deleted per finding 39ff2c7e77aa20a8, so resolve that removal first. If the file is retained for a concrete near-term use, add a second name to CODEOWNERS for this path and have that person review the fetch/error-handling logic (note the empty catch block at client.ts:11 swallows errors silently, worth flagging in that review) so the implementation isn't understood by only one engineer.

### Acceptance criteria

- [ ] CODEOWNERS (or equivalent ownership file) lists at least two owners for src/api/client.ts, or the file no longer exists in the tree
- [ ] If kept, a PR or doc exists showing a second engineer reviewed the file, including the empty catch block behavior
- [ ] No single-author-only ownership record remains for this path after the change

## Two lockfile kinds coexist; package-lock.json is empty/out of sync

```yaml
status: pending
slug: two-lockfile-kinds-coexist-package-lock-json-is-empty-out-of-syn
fingerprint: 9ead67e93821ff71
tier: A
priority: 5.0
family: dependency-debt
category: dependency-debt
debt_type: dependency
type_id: TD-02
severity: 5
effort: S
diff: NEW
```

### Proof

Read package-lock.json in full: `{ "name": "web-ts", "lockfileVersion": 3, "packages": {} }` — zero packages declared while package.json:6-7 declares 1 dependency + 3 devDependencies, and yarn.lock:1-4 independently locks tiny-emitter. ci.yml:15 runs `npm ci`, which requires package-lock.json to be in sync with package.json; an empty packages map for a manifest with 4 declared packages will fail npm ci. This is an application manifest (private:true), so the trap 'library without lockfile is normal' doesn't apply, and there's no sign of an in-progress migration between the two lockfiles.

### Evidence

- `package-lock.json:1-1`

```
{ "name": "web-ts", "lockfileVersion": 3, "packages": {} }
```

- `yarn.lock:1-4`

```
# yarn lockfile v1

tiny-emitter@2.1.0:
  version "2.1.0"
```

- `package.json:6-7`

```
"dependencies": { "tiny-emitter": "2.1.0" },
  "devDependencies": { "typescript": "5.4.5", "jest": "29.7.0", "eslint": "9.0.0" },
```

- `.github/workflows/ci.yml:15-16`

```
      - run: npm ci
      - uses: nick-fields/retry@7152eba30c6575329ac0576536151aca5a72780e
```

### Signals

- hotspot score 0.0, churn 1, coupling pairs 0, fan-in not computed (approximate)
- confirmed by: rule:manifest.two-lockfiles, scout:dependency-debt, tool:knip

### Remediation

Pick one package manager for this repo and remove the other lockfile. Given ci.yml already runs npm ci, keep package-lock.json and delete yarn.lock; regenerate package-lock.json from the current package.json with a real install (not an empty scaffold) so it lists tiny-emitter, typescript, jest, and eslint with resolved versions and integrity hashes. If yarn is actually the intended tool, switch ci.yml to yarn install --frozen-lockfile instead and delete package-lock.json. Commit the regenerated lockfile and confirm npm ci (or yarn install) succeeds locally and in CI.

### Acceptance criteria

- [ ] Exactly one lockfile (package-lock.json or yarn.lock) remains in the repository, matching the install command used in ci.yml
- [ ] The retained lockfile's package set matches package.json's declared dependencies and devDependencies (tiny-emitter, typescript, jest, eslint)
- [ ] npm ci (or yarn install --frozen-lockfile, matching the chosen tool) completes successfully with no manifest/lockfile mismatch error
- [ ] CI workflow run on the branch shows the install step passing

# Below the cut

## Empty catch swallows fetch/JSON failures with no log, no rethrow

```yaml
status: pending
slug: empty-catch-swallows-fetch-json-failures-with-no-log-no-rethrow
fingerprint: 52673adee31bbc96
tier: A
priority: 4.0726
family: error-masking
category: error-masking
debt_type: code
type_id: TD-13
severity: 2
effort: S
diff: NEW
```

### Proof

client.ts:11 `catch (e) {}` discards fetch/JSON failures with no log, no rethrow, then falls into unrelated flag-gated logging at lines 12-14 and returns null — indistinguishable from a genuine empty response. Not a boundary catch that reports (client-admin.ts's sibling catch at lines 14-15 does log, this one doesn't), and not a retry that re-raises. Confirmed as described; note correctly flags it as latent since getJson has no callers, which is why severity is already appropriately low.

### Evidence

- `src/api/client.ts:6-11`

```
export async function getJson(path: string): Promise<unknown> {
  const headers = { Authorization: `Bearer ${token}`, "X-Retry": "3" };
  try {
    const response = await fetch(`${BASE}${path}`, { headers });
    return await response.json();
  } catch (e) {}
```

## checkout() flag-branching logic has no test

```yaml
status: pending
slug: checkout-flag-branching-logic-has-no-test
fingerprint: 37123abc76b1359b
tier: A
priority: 3.4086
family: test-gaps
category: test-gaps
debt_type: test
type_id: TD-04
severity: 3
effort: S
diff: NEW
```

### Proof

Only two test files exist in the repo (src/__tests__/cart.test.ts, src/__tests__/pricing.spec.ts, per Glob), jest is the sole runner (package.json:5,8) with no e2e/integration config or directory. Neither covers checkout.ts:6-13. index.ts:6-7 calls checkout(cart) but is an entry point, not a test. No unconventionally named test file references checkout. Both the newCheckout branch (line 8) and legacy/empty-cart branch (lines 10-12) are unexercised.

### Evidence

- `src/checkout/checkout.ts:6-13`

```
export function checkout(cart: Cart): string {
  if (isEnabled("newCheckout")) {
    return `new:${total(cart)}`;
  }
  const first = cart.items[0];
  const label = first ? legacyFormat(priceOf(first.sku)) : "";
  return `legacy:${label}`;
}
```

## pricing.spec.ts skips bulk pricing assertion

```yaml
status: pending
slug: pricing-spec-ts-skips-bulk-pricing-assertion
fingerprint: 0e7744dd726d5b40
tier: A
priority: 3.2139
family: test-gaps
category: test-gaps
debt_type: test
type_id: TD-04
severity: 3
effort: S
diff: NEW
```

### Proof

pricing.spec.ts:7-9 disables the bulk-pricing test via it.skip with no comment/ticket. checkout.ts:11 does call legacyFormat(priceOf(first.sku)) on the legacy path, confirming the note's coupling claim. No other test file exists (only cart.test.ts and pricing.spec.ts), and pricing.ts has no bulk logic to be covered elsewhere, so the integration-coverage trap does not apply.

### Evidence

- `src/__tests__/pricing.spec.ts:7-9`

```
  it.skip("applies bulk pricing", () => {
    expect(priceOf("A1")).toBe(900);
  });
```

## Admin fetch catch logs but converts every failure to a silent null return

```yaml
status: pending
slug: admin-fetch-catch-logs-but-converts-every-failure-to-a-silent-nu
fingerprint: 08174bf5b156d429
tier: A
priority: 2.5
family: error-masking
category: error-masking
debt_type: code
type_id: TD-13
severity: 1
effort: S
diff: NEW
```

### Proof

client-admin.ts:14-16 logs the cause then returns null for every failure branch (timeout, network error, bad JSON), losing the distinction from a genuine empty response. Grep across src finds zero callers of getAdminJson, and index.ts only wires addItem/checkout — confirming the note's 'latent' claim. Not a documented boundary/retry re-raise, so the traps don't apply; severity 1 matches the latent, uncalled status.

### Evidence

- `src/api/client-admin.ts:8-17`

```
  try {
    const response = await fetch(`${BASE}${path}`, {
      headers,
      signal: AbortSignal.timeout(5000),
    });
    return await response.json();
  } catch (e) {
    console.error("admin request failed", e);
    return null;
  }
```

## Bulk pricing test skipped; feature not implemented in priceOf

```yaml
status: pending
slug: bulk-pricing-test-skipped-feature-not-implemented-in-priceof
fingerprint: 495fb96e5dd2b600
tier: A
priority: 2.4104
family: half-finished
category: half-finished
debt_type: requirement
type_id: TD-32
severity: 3
effort: M
diff: NEW
```

### Proof

pricing.ts:3-8 is a flat PRICES lookup with reserve(sku,0) and no discount/quantity logic; priceOf takes no qty argument at all. The skip at pricing.spec.ts:7-9 has no comment, date, or ticket. No abstract contract or ticketed deferral is present, so neither trap applies. Implementing bulk pricing would touch priceOf's signature plus call sites in cart.ts:17 and checkout.ts:11, supporting M effort.

### Evidence

- `src/__tests__/pricing.spec.ts:7-9`

```
it.skip("applies bulk pricing", () => {
    expect(priceOf("A1")).toBe(900);
  });
```

- `src/cart/pricing.ts:3-8`

```
const PRICES: Record<string, number> = { A1: 1000, B2: 2500 };

export function priceOf(sku: string): number {
  reserve(sku, 0);
  return PRICES[sku] ?? 0;
}
```

## legacyFormat's @deprecated tag contradicted by live checkout usage

```yaml
status: pending
slug: legacyformat-s-deprecated-tag-contradicted-by-live-checkout-usag
fingerprint: 6b42429f28509865
tier: B
priority: 2.31
family: doc-drift
category: doc-drift
debt_type: documentation
type_id: TD-08
severity: 3
effort: S
diff: NEW
```

### Proof

format-legacy.ts:3-5 tags legacyFormat @deprecated in favor of formatMoney, but grep shows formatMoney (format.ts:1) has zero direct callers in src outside format-legacy.ts itself. checkout.ts:4,11 imports and calls legacyFormat on every invocation; the newCheckout branch (checkout.ts:7-9) is dead since flags.ts:2-3 hardcodes newCheckout:false with a comment saying the new flow was never finished. So the deprecated function is the sole live formatter and its replacement is never called directly - the doc tag is misleading, not just stale.

### Evidence

- `src/util/format-legacy.ts:3-6`

```
/** @deprecated use formatMoney */
export function legacyFormat(cents: number): string {
  return formatMoney(cents).replace("$", "USD ");
}
```

- `src/checkout/checkout.ts:7-12`

```
  if (isEnabled("newCheckout")) {
    return `new:${total(cart)}`;
  }
  const first = cart.items[0];
  const label = first ? legacyFormat(priceOf(first.sku)) : "";
  return `legacy:${label}`;
```

- `src/flags.ts:1-5`

```
const FLAGS: Record<string, boolean> = {
  // newCheckout has been off since launch; the new flow was never finished
  newCheckout: false,
  betaBanner: true,
};
```

## Skipped bulk-pricing test asserts a value the source never produces

```yaml
status: pending
slug: skipped-bulk-pricing-test-asserts-a-value-the-source-never-produ
fingerprint: aa20afe178c7ab9b
tier: B
priority: 2.2497
family: test-quality
category: test-quality
debt_type: test
type_id: null
severity: 3
effort: S
diff: NEW
```

### Proof

pricing.spec.ts:8 asserts priceOf("A1")===900 inside an it.skip block. pricing.ts:3 fixes PRICES.A1=1000 with no bulk-discount branch, so the assertion would fail immediately if unskipped — confirming the mismatch has gone unnoticed only because the block never runs. Not a parametrised or smoke test.

### Evidence

- `src/__tests__/pricing.spec.ts:7-9`

```
  it.skip("applies bulk pricing", () => {
    expect(priceOf("A1")).toBe(900);
  });
```

## src/util/receipt-legacy.ts is an unused, also-deprecated file

```yaml
status: pending
slug: src-util-receipt-legacy-ts-is-an-unused-also-deprecated-file
fingerprint: 72480e1ceca75a25
tier: A
priority: 2.215
family: dead-code
category: dead-code
debt_type: code
type_id: TD-17
severity: 2
effort: S
diff: NEW
```

### Proof

Grep across src for `from ["'].*receipt` returns no matches, and a package-wide search for the string 'receipt' outside .tech-debt/ artifacts finds nothing - no index.ts export, no script, no test. receipt-legacy.ts:26-31's legacyFormatReceipt (and computeTotals/types) has zero in-repo callers, matching knip's unused-file flag. Not an entry point or runner-discovered test file (glob for *.test.ts found only src/__tests__/cart.test.ts). No documented kill-switch or plugin-surface rationale present.

### Evidence

- `src/util/receipt-legacy.ts:26-31`

```
/** @deprecated use formatReceipt */
export function legacyFormatReceipt(lines: ReceiptLine[]): string {
  const rows: string[] = [];
  for (const line of lines) {
    const lineTotal = line.quantity * line.unitCents;
    rows.push(`${line.label} x${line.quantity} USD ${(lineTotal / 100).toFixed(2)}`);
```

## src/util/receipt.ts is an unused file with zero callers

```yaml
status: pending
slug: src-util-receipt-ts-is-an-unused-file-with-zero-callers
fingerprint: 75599a6cb98b2ce8
tier: A
priority: 2.215
family: dead-code
category: dead-code
debt_type: code
type_id: TD-09
severity: 2
effort: S
diff: NEW
```

### Proof

Grep for `from ["'].*receipt` across src returns no matches; a broader search for 'receipt' outside .tech-debt/ artifacts finds nothing referencing receipt.ts. formatReceipt/computeTotals/types in receipt.ts:26-31 have zero callers, matching knip's unused-file flag. Not an entry point (no script or index export), not a runner-discovered test (only src/__tests__/cart.test.ts exists), and no documented kill-switch rationale.

### Evidence

- `src/util/receipt.ts:26-31`

```
export function formatReceipt(lines: ReceiptLine[]): string {
  const rows: string[] = [];
  for (const line of lines) {
    const lineTotal = line.quantity * line.unitCents;
    rows.push(`${line.label} x${line.quantity} $${(lineTotal / 100).toFixed(2)}`);
  }
```

## architecture.md claims pricing/stock import each other; only one-way

```yaml
status: pending
slug: architecture-md-claims-pricing-stock-import-each-other-only-one
fingerprint: bee2a473c0afedc2
tier: B
priority: 2.1
family: doc-drift
category: doc-drift
debt_type: documentation
type_id: TD-08
severity: 3
effort: S
diff: NEW
```

### Proof

docs/architecture.md:3-4 states pricing and stock 'import each other'. stock.ts:1 imports only `Cart` (type) from ./cart, never from pricing.ts. pricing.ts:1 imports `reserve` from ./stock. cart.ts:1 also imports priceOf from pricing, confirming cart->pricing->stock is a one-way chain with no cycle back into pricing. The doc's mutual-coupling claim is factually wrong.

### Evidence

- `docs/architecture.md:3-4`

```
`src/cart` owns items and totals, `src/checkout` owns the flow. Pricing and
stock currently import each other through `src/cart/stock.ts`.
```

- `src/cart/stock.ts:1-1`

```
import type { Cart } from "./cart";
```

- `src/cart/pricing.ts:1-1`

```
import { reserve } from "./stock";
```

- `docs/architecture.md:1-4`

```
# Architecture

`src/cart` owns items and totals, `src/checkout` owns the flow. Pricing and
stock currently import each other through `src/cart/stock.ts`.
```

- `src/api/client-admin.ts:1-4`

```
import { isEnabled } from "../flags";

const BASE = "https://admin.example.com";
const token = process.env.ADMIN_TOKEN ?? "";
```

## newCheckout flow left permanently disabled since launch, never finished

```yaml
status: pending
slug: newcheckout-flow-left-permanently-disabled-since-launch-never-fi
fingerprint: 035d3088827face4
tier: B
priority: 2.0475
family: half-finished
category: half-finished
debt_type: code
type_id: TD-32
severity: 3
effort: M
diff: NEW
```

### Proof

flags.ts:2 comment self-admits the new flow 'was never finished' with no date or ticket reference anywhere in the file or its referrers (client.ts, client-admin.ts, checkout.ts checked, none mention a tracking ID). checkout.ts:6-9 retains the guarded new-flow branch as unreachable code, not an abstract contract or interface. No compensating documentation of a deliberate deferral was found, so this doesn't match the 'ticketed deferral' non-debt shape.

### Evidence

- `src/flags.ts:1-5`

```
const FLAGS: Record<string, boolean> = {
  // newCheckout has been off since launch; the new flow was never finished
  newCheckout: false,
  betaBanner: true,
};
```

- `src/checkout/checkout.ts:6-9`

```
export function checkout(cart: Cart): string {
  if (isEnabled("newCheckout")) {
    return `new:${total(cart)}`;
  }
```

## Dependency manifest gaps in package.json

```yaml
status: pending
slug: dependency-manifest-gaps-in-package-json
fingerprint: 2db65f2197f66c42
tier: A
priority: 2.0
family: dependency-debt
category: dependency-debt
debt_type: dependency
type_id: TD-02
severity: 2
effort: S
diff: NEW
```

### Proof

verified by construction

### Evidence

- `package.json:1-1`

```
{
```

## Ownership gaps in src/checkout/checkout.ts

```yaml
status: pending
slug: ownership-gaps-in-src-checkout-checkout-ts
fingerprint: 4d03b88d399c3996
tier: A
priority: 1.7043
family: ownership
category: ownership
debt_type: knowledge-process
type_id: TD-16
severity: 2
effort: M
diff: NEW
```

### Proof

verified by construction

### Evidence

- `src/checkout/checkout.ts` (whole file)

```
src/checkout/checkout.ts: top author has no commits in 193 days
```

## Ownership gaps in src/util/receipt-legacy.ts

```yaml
status: pending
slug: ownership-gaps-in-src-util-receipt-legacy-ts
fingerprint: 0a3f457edc0b28ce
tier: A
priority: 1.6612
family: ownership
category: ownership
debt_type: knowledge-process
type_id: TD-16
severity: 2
effort: M
diff: NEW
```

### Proof

verified by construction

### Evidence

- `src/util/receipt-legacy.ts` (whole file)

```
src/util/receipt-legacy.ts: top author has no commits in 293 days
```

## Ownership gaps in src/util/receipt.ts

```yaml
status: pending
slug: ownership-gaps-in-src-util-receipt-ts
fingerprint: d9213e79b7d2b121
tier: A
priority: 1.6612
family: ownership
category: ownership
debt_type: knowledge-process
type_id: TD-16
severity: 2
effort: M
diff: NEW
```

### Proof

verified by construction

### Evidence

- `src/util/receipt.ts` (whole file)

```
src/util/receipt.ts: top author has no commits in 293 days
```

## Release process gaps

```yaml
status: pending
slug: release-process-gaps
fingerprint: 6a1f829fcc4126d8
tier: A
priority: 1.5
family: pipeline-infra
category: pipeline-infra
debt_type: build
type_id: TD-27
severity: 2
effort: M
diff: NEW
```

### Proof

verified by construction

### Evidence

- repository-level finding (no file or line range)

```
branch release/1.2 unmerged, last commit 2026-04-15 (147 days ago)
```

## Ownership gaps

```yaml
status: pending
slug: ownership-gaps
fingerprint: 8fe7e5857c49c8ad
tier: A
priority: 1.5
family: ownership
category: ownership
debt_type: knowledge-process
type_id: TD-23
severity: 2
effort: M
diff: NEW
```

### Proof

verified by construction

### Evidence

- repository-level finding (no file or line range)

```
no CODEOWNERS file with 3 human authors
```

- repository-level finding (no file or line range)

```
no ADR directory and no pull request template
```

## CI retries the full test command up to 3 times

```yaml
status: pending
slug: ci-retries-the-full-test-command-up-to-3-times
fingerprint: 3be7c52dfb951591
tier: B
priority: 1.4
family: test-quality
category: test-quality
debt_type: test
type_id: null
severity: 2
effort: S
diff: NEW
```

### Proof

ci.yml:16-20 wraps the entire `npm test` invocation in nick-fields/retry with max_attempts: 3 and no comment identifying a specific flaky test. This means any newly introduced flaky/order-dependent test is masked by up to 3 silent re-runs instead of failing the build. No table-driven/parametrised pattern or frozen-clock guard is present to explain the retry; it applies to the whole suite, not a targeted test.

### Evidence

- `.github/workflows/ci.yml:16-20`

```
      - uses: nick-fields/retry@7152eba30c6575329ac0576536151aca5a72780e
        with:
          timeout_minutes: 10
          max_attempts: 3
          command: npm test
```

## Cart total test asserts unexplained magic number

```yaml
status: pending
slug: cart-total-test-asserts-unexplained-magic-number
fingerprint: f08436450c50e406
tier: B
priority: 1.4
family: test-quality
category: test-quality
debt_type: test
type_id: null
severity: 2
effort: S
diff: NEW
```

### Proof

cart.test.ts:6 asserts total(cart)===2000 as a bare literal. pricing.ts:3 sets PRICES.A1=1000, and cart.ts:17 computes priceOf(sku)*qty, so 1000*2=2000 is correct but derivable only by reading pricing.ts; nothing in the test itself shows the derivation. Not parametrised, not a smoke test — neither trap applies.

### Evidence

- `src/__tests__/cart.test.ts:3-6`

```
test("total sums items", () => {
  const cart = { items: [] as { sku: string; qty: number }[] };
  addItem(cart, { sku: "A1", qty: 2 });
  expect(total(cart)).toBe(2000);
```

## Version bump and tagging done manually with no CI release job or docs

```yaml
status: pending
slug: version-bump-and-tagging-done-manually-with-no-ci-release-job-or
fingerprint: f96386b7dc024381
tier: B
priority: 1.4
family: pipeline-infra
category: pipeline-infra
debt_type: build
type_id: TD-27
severity: 2
effort: S
diff: NEW
```

### Proof

ci.yml:5-9 defines only a `test` job; no bump/tag/publish step exists in the single workflow file. .git/refs/tags/v1.0.0 and v1.1.0 exist alongside package.json:3 version 1.1.0, confirming manual tagging, and no CONTRIBUTING/CHANGELOG/README documents this as intentional (consistent with candidate 2's findings). Small/no-op for a private, single-package repo, so severity stays low as scored.

### Evidence

- `package.json:3-5`

```
  "version": "1.1.0",
  "private": true,
  "scripts": { "build": "tsc -p tsconfig.json", "test": "jest" },
```

- `.github/workflows/ci.yml:5-9`

```
jobs:
  test:
    runs-on: ubuntu-22.04
    timeout-minutes: 15
    steps:
```

## README omits CONTRIBUTING/CHANGELOG/ADR despite tagged releases

```yaml
status: pending
slug: readme-omits-contributing-changelog-adr-despite-tagged-releases
fingerprint: 1a2cee62a043fa63
tier: B
priority: 1.088
family: doc-drift
category: doc-drift
debt_type: documentation
type_id: TD-08
severity: 2
effort: M
diff: NEW
```

### Proof

README.md:1-5 has only a title, one-line description, and `npm test`. Repo-wide glob confirms no CONTRIBUTING.md, CHANGELOG.md, CHANGES, HISTORY, or docs/adr/ exist. package.json:3 shows version 1.1.0 and git refs (.git/refs/tags/v1.0.0, v1.1.0) confirm tagged releases exist with no changelog recording what changed. This is a genuine absence, not a planned/external interface.

### Evidence

- `README.md:1-5`

```
# web-ts

Cart and checkout front end.

    npm test
```

- `package.json:1-4`

```
{
  "name": "web-ts",
  "version": "1.1.0",
  "private": true,
```

# Below the cut: tier C and unverified

| slug | family | file | reason |
| --- | --- | --- | --- |
| client-admin-ts-token-timeout-error-path-logic-untested | test-gaps | src/api/client-admin.ts | the verifier downgraded it |
| getjson-fetch-has-no-timeout-and-silently-swallows-failures | half-finished | src/api/client.ts | the verifier downgraded it |
| newcheckout-flag-stalled-off-legacy-checkout-path-never-left | migration | src/flags.ts | selected for verification, but no verdict came back |
| admin-and-api-fetch-clients-duplicate-auth-fetch-error-logic-dri | duplication | src/api/client-admin.ts | the verifier downgraded it |
| flags-ts-isenabled-has-no-test-despite-gating-checkout-and-api-p | test-gaps | src/flags.ts | selected for verification, but no verdict came back |
| checkout-ts-newcheckout-branch-is-unreachable-flag-permanently-f | dead-code | src/checkout/checkout.ts | dead-code is capped at C without tool corroboration |
| deprecated-legacyformat-is-checkout-s-only-live-money-formatter | migration | src/util/format-legacy.ts | selected for verification, but no verdict came back |
| client-ts-silent-error-swallow-and-flag-gated-logging-untested | test-gaps | src/api/client.ts | the verifier downgraded it |
| full-receipt-module-duplicated-between-receipt-ts-and-receipt-le | duplication | src/util/receipt-legacy.ts | the verifier downgraded it |
| receipt-ts-tax-total-computation-and-formatting-untested | test-gaps | src/util/receipt.ts | the verifier downgraded it |
| reservecart-export-in-stock-ts-has-no-callers | dead-code | src/cart/stock.ts | not selected for verification |
| tslint-json-left-in-place-after-eslint-replaced-it | migration | tslint.json | not selected for verification |
| vendored-tiny-emitter-diverges-from-the-declared-npm-dependency | dependency-debt | package.json | the verifier downgraded it |

# Considered and rejected

- **receipt-legacy.ts duplicate money logic untested** - `src/util/receipt-legacy.ts` - The note claims receipt-legacy.ts is 'still reachable via legacyFormat/checkout.ts legacy path,' but checkout.ts (src/checkout/checkout.ts:1-4) imports only legacyFormat from ../util/format-legacy - a different file with a same-shaped but distinct function. A repo-wide grep for imports of 'receipt' found zero matches in src; only .tech-debt analysis artifacts mention 'receipt'. computeTotals/legacyFormatReceipt in receipt-legacy.ts have no caller at all, confirmed by candidates 3/5 (knip dead-file flags). Since the code is unreachable, this is dead-code territory, not a live test gap with money-correctness impact.

# Looks bad but is fine

- `src/api/client-admin.ts:6` - try/catch around fetch with a single error path is a normal shape, not deep branching.
- `src/checkout/checkout.ts:6` - Single flag-gated conditional with a short fallback path; not nested or long enough to qualify as a complex unit.
- `src/api/client-admin.ts:1` - Highest hotspot score in the repo but the file is only 23 lines with two small functions (fetch wrapper + flag check); it is a thin API client, not a unit with multiple disjoint responsibilities or long chains.
- `src/api/client.ts:1` - Duplicates client-admin.ts's fetch pattern (change-coupled pair) but each file is a single thin wrapper function; this is a duplication signal, not a god-class.
- `src/util/format-legacy.ts:4` - legacyFormat is marked @deprecated but is actively called from checkout.ts (the only reachable branch, since newCheckout is permanently false), so it is alive, not dead.
- `src/index.ts:4` - main() has no in-repo caller, but it is the package entry point (no other module or script invokes entry points by design).
- `src/generated/api-types.ts:1` - Generated file; generated code is excluded from this family per instructions and does not need unit tests.
- `src/util/receipt-legacy.ts:26` - @deprecated marker points to a completed replacement (formatReceipt) that already exists; this is a finished migration note, not unfinished work — belongs to the dead-code/duplication families, not half-finished.
- `src/util/format-legacy.ts:3` - @deprecated marker points to a completed replacement (formatMoney) that already exists and the old function is still actively called from checkout.ts; it is a superseded-but-working function, not a stub or unfinished path.
- `src/api/client-admin.ts:6` - Has a timeout (AbortSignal.timeout(5000)) and a non-empty catch that logs and returns null; not half-finished.
- `src/util/receipt-legacy.ts:1` - receipt-legacy.ts duplicates receipt.ts and legacyFormatReceipt is marked @deprecated, but neither file is imported anywhere in src (both are dead code), so there is no active old-vs-new call-site split to report as migration debt; this is dead-code/duplication territory, not an in-progress migration.
- `src/api/client-admin.ts:1` - client.ts and client-admin.ts are structurally near-identical with a shared bug pattern (timeout handling), but neither is named/annotated as legacy or superseded and both are actively used for distinct backends (public API vs admin API); this reads as duplication, not a migration in progress.
- `README.md:5` - The `npm test` example still runs as written: package.json defines a matching "test": "jest" script and CI invokes npm test the same way.
- `src/generated/api-types.ts:1` - File is explicitly marked generated by openapi-typescript; per the traps, generated output should not be scored as drift, only its generator.
- `src/cart/stock.ts:1` - madge reports a 3-module cycle cart.ts -> pricing.ts -> stock.ts -> cart.ts, but the back-edge (stock.ts line 1: import type { Cart } from './cart') is a TypeScript type-only import, erased at compile time, so there is no runtime circular dependency; and all three files live in the same cohesive src/cart/ package, which the family's own trap guidance excludes from being reported as an architecture finding.
- `src/__tests__/pricing.spec.ts:4` - expect(priceOf("nope")).toBe(0) asserts a literal but 0 is the documented default/fallback return value for unknown SKUs (src/cart/pricing.ts:7), not an arbitrary magic number.
- `.github/workflows/ci.yml:1` - Single workflow file for a project with 18 files/228 LOC; only one job exists so there is no duplicated pipeline YAML to flag.
- `src/api/client-admin.ts:15` - console.error in the catch block is a stdout/stderr write in library code, but no logger utility exists anywhere in the repo, so the 'stdout writes where a logger exists' symptom does not apply.

# Open questions for the maintainer

- `src/api/client-admin.ts:1` - Is client-admin.ts scaffolding for an admin panel feature that has not shipped yet, or leftover code from a removed feature? Affects whether it should be deleted or finished.
- `src/checkout/checkout.ts:7` - Is newCheckout intended as a permanent kill switch documenting an abandoned rewrite, or should the dead branch and its flag be removed?
- `src/flags.ts:2` - Is there a tracked ticket for finishing or removing the newCheckout flow, or is the dead branch expected to stay indefinitely?
- `src/__tests__/pricing.spec.ts:7` - Is bulk pricing still a planned requirement, or should the skipped test be removed along with the expectation?
- `src/checkout/checkout.ts:7` - Is there a ticket or date to either finish the newCheckout rollout or delete the dead new-path branch, or has the flag been formally abandoned?
- `tslint.json:1` - Was tslint.json intentionally kept for a specific tool/editor still reading it, or is it simply an unremoved leftover from the ESLint migration?
- `package-lock.json:1` - Was package-lock.json intentionally left empty when yarn.lock was added, or is it stale/generated incorrectly?
- `vendor/tiny-emitter.js:1` - Is vendor/tiny-emitter.js meant to replace the npm dependency, or is it leftover from a prior approach?
- `docs/architecture.md:4` - Was the pricing/stock mutual-import relationship ever true, or was the doc written from a planned design that was simplified before merge?
- `src/cart/pricing.ts:5` - priceOf() calls reserve(sku, 0) from the stock module as part of a price lookup. Is this an intentional stock-check-on-price-read behavior, or accidental coupling that happens to create the pricing->stock->cart import edge madge reports as a cycle?
- `.github/workflows/ci.yml:16` - Was nick-fields/retry added for a specific known-flaky test, and if so which one, or does it retry unconditionally for every CI run?
- `src/__tests__/pricing.spec.ts:7` - Is bulk pricing an abandoned feature or pending work — should the skipped test be deleted, implemented, or tracked against a ticket?
- `:0` - Is the manual package.json version bump / git tag process documented as intentional somewhere outside the repo (e.g. an external wiki), which would make this a non-issue?

# Not assessed

- Families not run: security (no leads)
- Tools: a claim that needs a tool which did not run -- currency, end-of-life, vulnerability -- is not assessed; the frontmatter's tools_absent names every such tool
- Runtime-only: coverage numbers, flake confirmation, model staleness, rollout state, deploy frequency
- By design: magic literals, convention violations, and class-level metrics that need a parser
