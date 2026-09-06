---
schema_version: 2
scan_date: 2026-09-06
root: <root>
total_files: 16
total_loc: 153
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
tools_run: []
tools_absent: []
git_available: true
counts:
  candidates: 31
  quote_failed: 2
  verified: 31
  tier_a: 11
  tier_b: 9
  tier_c: 10
  unverified: 0
  rejected: 1
  suppressed: 0
---

# Tech-debt scan - 2026-09-06

Scanned `<root>` - 16 files, 153 LOC across: javascript, markdown, typescript.

Review each finding below. To act on one, change its `status:` from `pending` to
`approved`, `rejected`, or `accepted` (add a `reason:` and an optional `until:` ISO
date), then run `/tech-debt-promote`.

Top hotspots: `src/api/client-admin.ts` (80.0), `src/api/client.ts` (42.9), `src/__tests__/pricing.spec.ts` (5.7), `README.md` (2.9), `src/checkout/checkout.ts` (2.9).

Top coupled pairs: `src/api/client-admin.ts` <-> `src/api/client.ts` (shared 4, ratio 0.889).

# Top 5

## Admin API client has no test coverage of auth/timeout/error paths

```yaml
status: pending
slug: admin-api-client-has-no-test-coverage-of-auth-timeout-error-path
fingerprint: 141175ed2e56d821
tier: A
priority: 10.0
family: test-gaps
category: test-gaps
debt_type: test
type_id: TD-04
severity: 4
effort: S
diff: NEW
```

### Proof

Grep across the repo for getAdminJson/client-admin finds only the definition file itself — no test file (src/__tests__ has only cart.test.ts and pricing.spec.ts) and no caller yet either, but the module is exported and actively churned (churn=4, highest hotspot_score=80.0). Auth header (line 7), timeout (line 11), and catch-to-null (lines 14-16) are all unguarded by any assertion. Real gap, though current blast radius is limited since nothing calls it yet.

### Evidence

- `src/api/client-admin.ts:6-18`

```
export async function getAdminJson(path: string): Promise<unknown> {
  const headers = { Authorization: `Bearer ${token}`, "X-Retry": "3" };
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
}
```

### Signals

- hotspot score 80.0, churn 4, coupling pairs 1, fan-in 0 (approximate)
- confirmed by: coupling, hotspot, scout:test-gaps, signal:no-mapped-tests

### Remediation

Add a test file for `src/api/client-admin.ts` beside the two that exist in `src/__tests__`. Stub `fetch` and cover the three paths nothing asserts today: the outgoing request carries the `Authorization` bearer built from `ADMIN_TOKEN` and the `X-Retry` header; the abort signal is the 5000 ms one; and a rejected fetch or a non-JSON body resolves to `null` after the `console.error`. Assert that `null` explicitly, because the catch collapses every failure into it. Then decide whether `null` is the contract callers should get, while `getAdminJson` still has none.

### Acceptance criteria

- [ ] A test file covering `src/api/client-admin.ts` exists and is picked up by the default test glob.
- [ ] Tests assert both the `Authorization` and `X-Retry` headers on the outgoing request.
- [ ] A test asserts `getAdminJson` resolves to `null` when fetch rejects, and that the timeout is 5000 ms.

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

`src/api/client-admin.ts` is the repository's hottest file by churn, has one author, and has no caller yet, so nobody else has needed to read it. Settle that before it acquires callers: first decide whether `getAdminJson` is kept or deleted as dead code. If it is kept, have a second engineer review the module-load token read, the header shape it shares with `src/api/client.ts`, and the catch-to-`null` contract, and let them author the missing test file so the review leaves a commit. Add `src/api/` to CODEOWNERS with two owners.

### Acceptance criteria

- [ ] A decision is recorded on whether `getAdminJson` stays or is deleted as unused.
- [ ] If it stays, a commit touching `src/api/client-admin.ts` is authored by a second contributor.
- [ ] CODEOWNERS covers `src/api/` and names at least two owners.

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

`src/api/client.ts` also has a single author across the window, and it duplicates the bearer plus `X-Retry` header block and the `BASE`-plus-path fetch of `src/api/client-admin.ts`. Pay both down at once: have a second engineer extract that shared request construction into one helper both modules call, and let that be their first commit on the file. Have them look at the empty `catch (e) {}` in `getJson` while they are in there, since it is the reason this module's failures are invisible. Add `src/api/` to CODEOWNERS with two owners.

### Acceptance criteria

- [ ] The bearer and `X-Retry` header construction lives in one place used by both `client.ts` and `client-admin.ts`.
- [ ] A commit touching `src/api/client.ts` is authored by someone other than the current sole author.
- [ ] The empty catch block in `getJson` either logs or is replaced by a deliberate, documented fallback.

## Checkout flow (legacy/new switch) has no automated test

```yaml
status: pending
slug: checkout-flow-legacy-new-switch-has-no-automated-test
fingerprint: 37123abc76b1359b
tier: A
priority: 4.5448
family: test-gaps
category: test-gaps
debt_type: test
type_id: TD-04
severity: 4
effort: S
diff: NEW
```

### Proof

The only test file in the repo is src/__tests__/cart.test.ts, which tests cart.ts's addItem/total and never imports checkout.ts, priceOf, or legacyFormat. Repo-wide search for 'checkout' finds no *.test.ts, *.spec.ts, or e2e references — only checkout.ts itself, index.ts (which calls checkout(cart) at index.ts:7 but discards the return value), and docs/CI mentions. Both the legacy branch (checkout.ts:10-12) and the newCheckout branch (line 7-8) are unasserted.

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

### Signals

- hotspot score 2.9, churn 1, coupling pairs 0, fan-in 1 (approximate)
- confirmed by: hotspot, scout:test-gaps, signal:no-mapped-tests

### Remediation

Add a test file for `src/checkout/checkout.ts`; `src/__tests__/cart.test.ts` never imports it, so neither side of the `newCheckout` switch is exercised. Stub `isEnabled` rather than mutating the flag store. With the flag on, pin the `new:` string against `total(cart)`. With it off, pin the `legacy:` string against `legacyFormat(priceOf(sku))` for the first item, and add the empty-cart case where the label collapses to the empty string. `src/index.ts` discards the return value, so these assertions are the only thing holding the string shape.

### Acceptance criteria

- [ ] A test exercises `checkout` with `newCheckout` enabled and again with it disabled.
- [ ] The empty-cart legacy branch is asserted, including the empty label.
- [ ] Both branches assert the returned string itself, not merely that the call does not throw.

## Bulk pricing behavior test is skipped

```yaml
status: pending
slug: bulk-pricing-behavior-test-is-skipped
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

pricing.ts:5-8 has flat PRICES lookup with no discount/quantity logic. The only test naming 'bulk pricing' (pricing.spec.ts:7-9) is it.skip'd, and no other test file (cart.test.ts, pricing.spec.ts) exercises tiered/bulk pricing. No ticket or date annotation near the skip. Confirms priceOf's non-trivial pricing behavior is unguarded by the suite.

### Evidence

- `src/__tests__/pricing.spec.ts:7-9`

```
it.skip("applies bulk pricing", () => {
    expect(priceOf("A1")).toBe(900);
  });
```

### Signals

- hotspot score 5.7, churn 1, coupling pairs 0, fan-in not computed (approximate)
- confirmed by: scout:test-gaps, signal:no-mapped-tests

### Remediation

remediation note not available

### Acceptance criteria

remediation note not available

# Below the cut

## Bulk pricing test skipped; feature never implemented in priceOf

```yaml
status: pending
slug: bulk-pricing-test-skipped-feature-never-implemented-in-priceof
fingerprint: eaefb059a8c16e0d
tier: A
priority: 3.2139
family: half-finished
category: half-finished
debt_type: requirement
type_id: null
severity: 3
effort: S
diff: NEW
```

### Proof

pricing.ts:5-8 confirms priceOf is a flat PRICES.get with no bulk/tiered logic — no partial scaffolding, branch, or comment toward the feature exists anywhere in cart.ts, pricing.ts, or checkout.ts. The skip has no ticket/date/reason string attached. This matches half-finished: a requirement named in a test but never implemented, not a flaky-test skip.

### Evidence

- `src/__tests__/pricing.spec.ts:7-10`

```
  it.skip("applies bulk pricing", () => {
    expect(priceOf("A1")).toBe(900);
  });
});
```

- `src/cart/pricing.ts:5-8`

```
export function priceOf(sku: string): number {
  reserve(sku, 0);
  return PRICES[sku] ?? 0;
}
```

## Feature flag lookup (isEnabled) has no direct test

```yaml
status: pending
slug: feature-flag-lookup-isenabled-has-no-direct-test
fingerprint: 02bbf6de78e47bd6
tier: A
priority: 2.6
family: test-gaps
category: test-gaps
debt_type: test
type_id: TD-04
severity: 2
effort: S
diff: NEW
```

### Proof

Grep across src for .test.ts/.spec.ts finds only cart.test.ts and pricing.spec.ts, neither referencing flags.ts, client.ts, client-admin.ts, or checkout.ts. isEnabled (flags.ts:7-9) is called from checkout.ts:7, client.ts:12, client-admin.ts:21, and its ?? false fallback is what makes the undefined 'adminPanel' key resolve to false in client-admin.ts:21 — untested branch logic with real effect.

### Evidence

- `src/flags.ts:1-9`

```
const FLAGS: Record<string, boolean> = {
  // newCheckout has been off since launch; the new flow was never finished
  newCheckout: false,
  betaBanner: true,
};

export function isEnabled(name: string): boolean {
  return FLAGS[name] ?? false;
}
```

## Skipped bulk-pricing test asserts a value the implementation cannot produce

```yaml
status: pending
slug: skipped-bulk-pricing-test-asserts-a-value-the-implementation-can
fingerprint: 1b4189615c5560c6
tier: B
priority: 2.2497
family: test-quality
category: test-quality
debt_type: test
type_id: TD-12
severity: 3
effort: S
diff: NEW
```

### Proof

priceOf (pricing.ts:5-8) is PRICES[sku] ?? 0 with PRICES.A1=1000 and no discount logic; reserve(sku,0) in stock.ts has no side effect on price. So priceOf('A1') always returns 1000, never 900 as asserted at line 8. The skipped test is not merely disabled coverage but literally unpassable as written, confirming it never worked and documents nothing accurate about current behavior.

### Evidence

- `src/__tests__/pricing.spec.ts:7-10`

```
it.skip("applies bulk pricing", () => {
    expect(priceOf("A1")).toBe(900);
  });
});
```

## CI wraps entire test suite in automatic retries

```yaml
status: pending
slug: ci-wraps-entire-test-suite-in-automatic-retries
fingerprint: 3be7c52dfb951591
tier: B
priority: 2.1
family: test-quality
category: test-quality
debt_type: test
type_id: TD-18
severity: 3
effort: S
diff: NEW
```

### Proof

ci.yml:15-19 wraps the entire `npm test` invocation in nick-fields/retry with max_attempts: 3, timeout_minutes: 10. This retries the whole suite, not a single flaky assertion, so any intermittently-failing test can pass on attempt 2 or 3 and CI reports green. No test-level retry/quarantine mechanism exists to isolate which test was flaky.

### Evidence

- `.github/workflows/ci.yml:15-19`

```
- uses: nick-fields/retry@7152eba30c6575329ac0576536151aca5a72780e
        with:
          timeout_minutes: 10
          max_attempts: 3
          command: npm test
```

## Two lockfile kinds present (npm and yarn) for one application

```yaml
status: pending
slug: two-lockfile-kinds-present-npm-and-yarn-for-one-application
fingerprint: 9ead67e93821ff71
tier: B
priority: 2.1
family: dependency-debt
category: dependency-debt
debt_type: dependency
type_id: TD-02
severity: 3
effort: S
diff: NEW
```

### Proof

package-lock.json:1 is `{ "packages": {} }` — an empty lockfile that does not record tiny-emitter despite it being a declared dependency. yarn.lock:1-4 does record tiny-emitter@2.1.0. ci.yml:14,19 configures `cache: npm` and runs `npm test` exclusively; there is no yarn step anywhere in CI. So yarn.lock is dead weight and the npm lockfile that CI actually relies on is non-functional (would need regeneration on every npm ci).

### Evidence

- `package-lock.json:1-1`

```
{ "name": "web-ts", "lockfileVersion": 3, "packages": {} }
```

- `yarn.lock:1-3`

```
# yarn lockfile v1

tiny-emitter@2.1.0:
```

## architecture.md describes mutual import that no longer exists

```yaml
status: pending
slug: architecture-md-describes-mutual-import-that-no-longer-exists
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

architecture.md:3-4 claims pricing and stock 'import each other' through stock.ts. Actual code: stock.ts:1 imports only `type Cart` from cart.ts, nothing from pricing.ts; pricing.ts:1 imports `reserve` from stock.ts. This is a one-way dependency (pricing -> stock), not a cycle, and stock's only import is a type from cart, not pricing. The doc's cycle claim is factually wrong.

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
fingerprint: d96ff883dbafb64f
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
src/checkout/checkout.ts: top author has no commits in 188 days
```

## Deprecated legacyFormat still the only caller path, not formatMoney

```yaml
status: pending
slug: deprecated-legacyformat-still-the-only-caller-path-not-formatmon
fingerprint: b7396d04c3285472
tier: B
priority: 1.54
family: migration
category: migration
debt_type: design
type_id: TD-06
severity: 2
effort: S
diff: NEW
```

### Proof

Grep confirms legacyFormat's only call site is checkout.ts:11 (import at line 4), and formatMoney (format.ts:1-3) has no callers besides format-legacy.ts:1's import — i.e. 100% of live call sites use the deprecated wrapper, 0% call formatMoney directly. No evidence of deliberate multi-backend design; it's a single incomplete migration.

### Evidence

- `src/util/format-legacy.ts:3-6`

```
/** @deprecated use formatMoney */
export function legacyFormat(cents: number): string {
  return formatMoney(cents).replace("$", "USD ");
}
```

- `src/checkout/checkout.ts:4-4`

```
import { legacyFormat } from "../util/format-legacy";
```

## Release process gaps

```yaml
status: pending
slug: release-process-gaps
fingerprint: 87d88c96a1418489
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
branch release/1.2 unmerged, last commit 2026-04-15 (142 days ago)
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

## README missing CONTRIBUTING, ADR, and CHANGELOG documentation

```yaml
status: pending
slug: readme-missing-contributing-adr-and-changelog-documentation
fingerprint: 1a2cee62a043fa63
tier: B
priority: 1.4507
family: doc-drift
category: doc-drift
debt_type: documentation
type_id: TD-08
severity: 2
effort: S
diff: NEW
```

### Proof

README.md:1-5 is the entire file: title, one-line description, `npm test`. Globbed for CONTRIBUTING*, CHANGELOG*, and any adr/ directory repo-wide — none exist. docs/ only contains architecture.md. So the absence is real and total, not just missing a link to existing docs.

### Evidence

- `README.md:1-5`

```
# web-ts

Cart and checkout front end.

    npm test
```

## Coverage threshold declared but not enforced by test script

```yaml
status: pending
slug: coverage-threshold-declared-but-not-enforced-by-test-script
fingerprint: 08e6401c9ac87df8
tier: B
priority: 1.4
family: test-gaps
category: test-gaps
debt_type: test
type_id: TD-04
severity: 2
effort: S
diff: NEW
```

### Proof

package.json:5,8 — "test": "jest" with no --coverage flag, while jest.coverageThreshold.global.lines is set to 80. No jest.config.* file exists to add coverage-on-by-default. Coverage (and thus the threshold) only evaluates with `--coverage`, so plain `npm test`/`yarn test` never triggers it. Confirmed only one test file exists repo-wide (src/__tests__/cart.test.ts); client.ts, client-admin.ts, and checkout.ts have no corresponding test files, so the unmet threshold would go undetected.

### Evidence

- `package.json:5-8`

```
"scripts": { "build": "tsc -p tsconfig.json", "test": "jest" },
  "dependencies": { "tiny-emitter": "2.1.0" },
  "devDependencies": { "typescript": "5.4.5", "jest": "29.7.0", "eslint": "9.0.0" },
  "jest": { "coverageThreshold": { "global": { "lines": 80 } } }
```

## tslint.json left in place after move to ESLint, with tslint not installed

```yaml
status: pending
slug: tslint-json-left-in-place-after-move-to-eslint-with-tslint-not-i
fingerprint: 3d5daf8fb72b00a9
tier: B
priority: 1.4
family: migration
category: migration
debt_type: build
type_id: TD-17
severity: 2
effort: S
diff: NEW
```

### Proof

tslint.json:1 (`tslint:recommended`) has no corresponding tooling: package.json:7 lists eslint but not tslint, and grep confirms tslint appears nowhere else in the repo (no script, no CI step). ci.yml only runs `npm test` (no lint step at all), so neither tslint.json nor .eslintrc.json is actually invoked — but tslint.json specifically is a dead leftover from a superseded tool with zero remaining references, matching the migration-debris pattern exactly.

### Evidence

- `tslint.json:1-1`

```
{ "extends": "tslint:recommended" }
```

- `.eslintrc.json:1-1`

```
{ "extends": "eslint:recommended" }
```

- `package.json:7-7`

```
  "devDependencies": { "typescript": "5.4.5", "jest": "29.7.0", "eslint": "9.0.0" },
```

## Cart total test asserts hardcoded money total with no derivation

```yaml
status: pending
slug: cart-total-test-asserts-hardcoded-money-total-with-no-derivation
fingerprint: f08436450c50e406
tier: B
priority: 1.4
family: test-quality
category: test-quality
debt_type: test
type_id: TD-12
severity: 2
effort: S
diff: NEW
```

### Proof

pricing.ts:3 sets PRICES.A1=1000; cart.ts:17 total() sums priceOf(sku)*qty. Test adds A1 qty=2 (1000*2=2000) and asserts toBe(2000) with no reference to the 1000 unit price, so the reader must open pricing.ts to confirm correctness. Not table-driven, no fake timers, and this is the only assertion in the test (not assertion-free).

### Evidence

- `src/__tests__/cart.test.ts:3-6`

```
test("total sums items", () => {
  const cart = { items: [] as { sku: string; qty: number }[] };
  addItem(cart, { sku: "A1", qty: 2 });
  expect(total(cart)).toBe(2000);
```

# Below the cut: tier C and unverified

| slug | family | file | reason |
| --- | --- | --- | --- |
| client-admin-ts-exports-are-never-called-adminpanel-flag-key-doe | dead-code | src/api/client-admin.ts | confirm |
| getjson-has-no-in-repo-callers-betabanner-flag-inside-it-is-alwa | dead-code | src/api/client.ts | confirm |
| empty-catch-swallows-fetch-json-errors-in-getjson | error-masking | src/api/client.ts | downgrade |
| duplicated-fetch-with-auth-headers-logic-across-api-clients | duplication | src/api/client.ts | downgrade |
| getjson-fetch-has-no-timeout-and-swallows-all-errors | half-finished | src/api/client.ts | downgrade |
| checkout-reaches-past-declared-cart-boundary-into-pricing-intern | architecture | docs/architecture.md | confirm |
| newcheckout-flag-hardcoded-off-checkout-branch-unreachable | dead-code | src/flags.ts | confirm |
| newcheckout-flag-path-is-dead-only-legacy-deprecated-path-ever-r | migration | src/flags.ts | downgrade |
| deprecated-legacyformat-wrapper-still-called-from-checkout | dead-code | src/util/format-legacy.ts | confirm |
| deprecated-legacyformat-still-used-on-the-live-checkout-path | half-finished | src/util/format-legacy.ts | downgrade |

# Considered and rejected

- **Admin request failures logged then converted to null, hiding cause from caller** - `src/api/client-admin.ts` - golden trap: intentional fixture

# Looks bad but is fine

- `src/api/client-admin.ts:6` - Hotspot score 80.00 but function is a short async fetch wrapper with one try/catch, no nesting; not a complex-units candidate.
- `src/api/client.ts:6` - Hotspot score 42.90 but function has only a try/catch and one flat if, no nesting or branching complexity.
- `src/checkout/checkout.ts:6` - Single flat if/return with one ternary-like ternary expression; no nesting or long branching chains despite being a hotspot file.
- `src/api/client-admin.ts:1` - Small module with two loosely related exports (getAdminJson, adminEnabled); flagged as top hotspot by score but is a thin fetch wrapper plus a flag check, not a class with clustered fields or multiple reasons to change.
- `src/api/client.ts:1` - Structurally near-identical to client-admin.ts (shared change-coupling), but both are minimal function modules, not god-classes; duplication concern belongs to a different family.
- `src/util/format-legacy.ts:1` - legacyFormat calls formatMoney and post-processes the string rather than reimplementing formatting logic; not a duplicate, just a thin deprecated wrapper.
- `src/index.ts:1` - Only wires addItem/checkout together as an entry point (untested_change_share=0.5, not hotspot-banded); this is glue/composition code, not standalone behavior worth a unit test.
- `src/api/client-admin.ts:6` - Has AbortSignal.timeout(5000) and logs errors in the catch block, so it is not half-finished despite superficially resembling client.ts.
- `src/api/client.ts:1` - client.ts and client-admin.ts target distinct hosts (api.example.com vs admin.example.com) and are a duplication/coupling concern (drifted timeout/logging handling), not an old-vs-new migration pair; no naming or deprecation signal marks either as superseded.
- `package.json:6` - tiny-emitter is pinned to an exact version (2.1.0), not a floating range, so no floating-range-in-a-library issue applies.
- `src\util\format-legacy.ts:1` - format-legacy.ts wrapping format.ts is an internal code-duplication/migration pattern, not a dependency-debt issue (no external package involved).
- `src/checkout/checkout.ts:1` - checkout.ts and flags.ts are not mentioned in docs/architecture.md, but architecture.md only scopes itself to cart/stock/pricing coupling and does not claim to be exhaustive, so this is an incompleteness rather than a contradiction.
- `src/cart/cart.ts:1` - cart.ts -> pricing.ts -> stock.ts -> (type-only) cart.ts forms a cycle, but all three files live inside the single src/cart directory/package and the back-edge (src/cart/stock.ts:1) is a type-only import erased at compile time, not a runtime circular dependency. This is an intra-package design smell rather than a cross-module architecture cycle.
- `src/api/client.ts:13` - console.log call looks like a stdout-vs-logger violation, but no logger/logging library exists anywhere in the repo (grep for logger/winston/pino/log4js found nothing), so the pipeline-infra pattern (stdout writes where a logger exists) does not apply.
- `src/api/client-admin.ts:15` - console.error call, same reasoning: no logger is present in the codebase to compare against.
- `.github/workflows/ci.yml:1` - Only one workflow file with a single job exists; there is no second workflow to compare against, so this is not duplicated pipeline YAML.
- `src/api/client-admin.ts:14` - golden trap: intentional fixture

# Open questions for the maintainer

- `src/api/client.ts:1` - Is this module meant to be a public/plugin entry point consumed by code outside this repo, given the package has no 'main'/'exports' field to confirm or rule that out?
- `src/api/client-admin.ts:1` - Same question as client.ts: no in-repo caller was found for getAdminJson or adminEnabled, and there is no external-surface declaration to check against.
- `src/api/client.ts:6` - quote not found: API client silently swallows fetch errors with no test
- `src/api/client.ts:1` - quote not found: invented quote (golden pin)
- `src/flags.ts:2` - Is there a tracked ticket/date to either finish or remove the newCheckout flow, or is it considered permanently abandoned?
- `tslint.json:1` - Is tslint.json intentionally retained for a downstream consumer/tool, or is it simply forgotten cleanup from the ESLint migration?
- `package-lock.json:1` - package-lock.json's packages map is empty even though package.json declares tiny-emitter as a dependency; is npm install/ci actually run against this lockfile, or is it a placeholder?
- `vendor\tiny-emitter.js:1` - Is vendor/tiny-emitter.js dead code (unreferenced by any import), or is it consumed by a build step not visible in src/?
- `src/cart/pricing.ts:1` - docs/architecture.md describes pricing and stock as importing each other; is that coupling considered acceptable long-term since both live inside the single src/cart package, or is a boundary intended between them?

# Not assessed

- Families not run: security (no leads)
- Tools: the tool probe lands in phase 4, so currency, end-of-life and vulnerability claims are not assessed
- Runtime-only: coverage numbers, flake confirmation, model staleness, rollout state, deploy frequency
- By design: magic literals, convention violations, and class-level metrics that need a parser
