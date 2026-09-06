---
schema_version: 2
scan_date: 2026-09-06
root: <root>
total_files: 16
total_loc: 243
languages:
- markdown
- python
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
- security
- test-quality
- pipeline-infra
families_skipped: []
tools_run: []
tools_absent: []
git_available: true
counts:
  candidates: 37
  quote_failed: 1
  verified: 36
  tier_a: 16
  tier_b: 13
  tier_c: 6
  unverified: 1
  rejected: 2
  suppressed: 0
---

# Tech-debt scan - 2026-09-06

Scanned `<root>` - 16 files, 243 LOC across: markdown, python.

Review each finding below. To act on one, change its `status:` from `pending` to
`approved`, `rejected`, or `accepted` (add a `reason:` and an optional `until:` ISO
date), then run `/tech-debt-promote`.

Top hotspots: `src/pay/refund.py` (100.0), `src/pay/ledger.py` (52.9), `src/pay/gateway.py` (20.2), `src/pay/models.py` (5.0), `tests/test_ledger.py` (4.2).

Top coupled pairs: `src/pay/ledger.py` <-> `src/pay/refund.py` (shared 5, ratio 0.714).

# Top 5

## Ledger post failure silently swallowed before gateway refund fires

```yaml
status: pending
slug: ledger-post-failure-silently-swallowed-before-gateway-refund-fir
fingerprint: 2e969b3499636196
tier: A
priority: 15.0
family: error-masking
category: error-masking
debt_type: defect
type_id: TD-13
severity: 5
effort: S
diff: NEW
```

### Proof

refund.py:31-34 catches bare Exception from ledger.post and passes silently — no log, no re-raise, no cause preserved. Execution then proceeds unconditionally to gateway.refund at line 37, which moves money via the live v2 API (gateway.py) regardless of ledger write success. This means a ledger write failure produces no audit record and no operator visibility while the refund is still issued, a genuine financial-integrity error-masking bug.

### Evidence

- `src/pay/refund.py:30-35`

```
    entry = Entry(account=refund.order_id, amount_cents=-refund.amount_cents, reason=refund.reason_code)
    try:
        ledger.post(entry)
    except Exception:
        pass
    # FIXME: the gateway retries on our behalf, so a duplicate refund can post twice
```

### Signals

- hotspot score 100.0, churn 7, coupling pairs 1, fan-in 2 (approximate)
- confirmed by: coupling, hotspot, pattern:swallowed-catch, satd, scout:error-masking

### Remediation

In `issue()` in `src/pay/refund.py`, drop the bare `except Exception: pass` around `ledger.post(entry)` and let the ledger failure be loud: log it on the module logger and re-raise, so the `gateway.refund` call below it is never reached without an audit entry. Do that first, then add the test that pins it. Only after that decide, with the payments owner, whether a refund may still be issued while the ledger is down; if it may, make that an explicit branch that records a compensating entry and returns a distinct result, not a swallowed exception.

### Acceptance criteria

- [ ] `src/pay/refund.py` contains no bare `except Exception` that discards the ledger error; the failure is logged and re-raised.
- [ ] A test in `tests/test_refund.py` makes `ledger.post` raise and asserts `Gateway.refund` is never called.
- [ ] A caller can tell a ledger failure apart from a gateway rejection by the exception or return value.

## Self-admitted duplicate-refund risk left unaddressed

```yaml
status: pending
slug: self-admitted-duplicate-refund-risk-left-unaddressed
fingerprint: b459099b48e0a272
tier: A
priority: 11.25
family: half-finished
category: half-finished
debt_type: defect
type_id: null
severity: 5
effort: M
diff: NEW
```

### Proof

FIXME at refund.py:35 names duplicate-refund risk from gateway-side retries. The only dedup guard is `_seen` (refund.py:14,27-29), an in-memory, per-process set keyed on order_id at the start of issue() -- it does not gate the actual gateway.refund() call from being retried by the gateway itself, and resets on process restart. No ticket reference found in code or tests. The named risk is genuinely still present: nothing in gateway.py (idempotency key, dedup header) mitigates it either. Severity 5 (money duplication) and effort M (needs idempotency key design, not a one-liner) both look right.

### Evidence

- `src/pay/refund.py:35-40`

```
# FIXME: the gateway retries on our behalf, so a duplicate refund can post twice
    try:
        accepted = gateway.refund(refund.order_id, refund.amount_cents)
    except OSError as exc:
        log.exception("gateway unreachable for %s", refund.order_id)
        raise RuntimeError("gateway unreachable") from exc
```

### Signals

- hotspot score 100.0, churn 7, coupling pairs 1, fan-in 2 (approximate)
- confirmed by: coupling, hotspot, satd, scout:half-finished

### Remediation

Replace the process-local `_seen` set in `src/pay/refund.py` (declared line 14, checked lines 27-29) with an idempotency key the gateway honours: derive a stable key per refund from `order_id`, `amount_cents` and `reason_code`, persist it alongside the ledger entry, and pass it into `gateway.refund` so a gateway-side retry collapses onto the same refund. Land the persisted key first; `_seen` may stay until it is live, but must not be the last guard standing. Remove `_seen` and the FIXME at line 35 in the change that lands the key.

### Acceptance criteria

- [ ] `_seen` is gone from `src/pay/refund.py` and the duplicate guard survives a process restart.
- [ ] `gateway.refund` receives an idempotency key derived from the refund, and two calls with the same key move money once.
- [ ] The duplicate-refund FIXME at `src/pay/refund.py:35` is deleted in the same commit as the guard.

## Ownership gaps in src/pay/refund.py

```yaml
status: pending
slug: ownership-gaps-in-src-pay-refund-py
fingerprint: cad19db020b88f9f
tier: A
priority: 9.0
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

- `src/pay/refund.py:None-None`

```
src/pay/refund.py: 100% of lines by one author, 1 author(s) in the window
```

### Signals

- hotspot score 100.0, churn 7, coupling pairs 1, fan-in 2 (approximate)
- confirmed by: rule:ownership.knowledge-island

### Remediation

`src/pay/refund.py` is the money path and every line in the churn window is by one author, so no second engineer has had to read the ledger-then-gateway ordering in `issue()` or the cents conversion in `issue_partial()`. Get a second person through the file for real: have them review those two, then author the missing refund tests themselves so the review leaves a commit behind. Add `src/pay/` to CODEOWNERS with two owners so later changes need a second reader. This is a review-process fix; do not reshuffle the module to manufacture authorship.

### Acceptance criteria

- [ ] CODEOWNERS covers `src/pay/` and names at least two reviewers.
- [ ] At least one merged commit touching `src/pay/refund.py` is authored by someone other than the current sole author.
- [ ] The second reviewer has signed off on the ledger-then-gateway ordering in `issue()`.

## issue_partial() has no test at all

```yaml
status: pending
slug: issue-partial-has-no-test-at-all
fingerprint: 4b10ada7bef4b500
tier: B
priority: 6.3
family: test-gaps
category: test-gaps
debt_type: test
type_id: TD-04
severity: 3
effort: S
diff: NEW
```

### Proof

Grep confirms no test calls issue_partial anywhere in tests/. Unlike test_issue_calls_gateway (explicitly marked @pytest.mark.skip), issue_partial has no test stub at all — not even a skipped placeholder. The fraction-to-cents conversion (refund.py:46) and full delegation to issue() are unguarded, so a rounding or scale regression would ship undetected.

### Evidence

- `src/pay/refund.py:45-48`

```
def issue_partial(refund: Refund, gateway: Gateway, fraction: float) -> bool:
    amount = cents(refund.amount_cents * fraction / 100)
    partial = Refund(order_id=refund.order_id, amount_cents=amount, reason_code=refund.reason_code)
    return issue(partial, gateway)
```

### Signals

- hotspot score 100.0, churn 7, coupling pairs 1, fan-in 2 (approximate)
- confirmed by: coupling, hotspot, satd, scout:test-gaps

### Remediation

Add tests for `issue_partial()` to `tests/test_refund.py`. Cover the arithmetic first: the fraction-to-cents conversion at `src/pay/refund.py:46` needs exact expected cents at the rounding boundaries, including an odd amount and a fraction that lands on a half cent. Then cover the delegation: a fake gateway asserting the `Refund` handed on keeps the original `order_id` and `reason_code` and carries only the reduced amount. Do not copy the `@pytest.mark.skip` that sits on `test_issue_calls_gateway`; these tests have to run in the default suite.

### Acceptance criteria

- [ ] `tests/test_refund.py` has at least one unskipped test that calls `issue_partial` directly.
- [ ] A rounding assertion pins the exact cents for a fraction that does not divide evenly.
- [ ] A test asserts the `Refund` passed on to the gateway keeps the original `order_id` and `reason_code`.

## print() used for refund outcome despite logger present

```yaml
status: pending
slug: print-used-for-refund-outcome-despite-logger-present
fingerprint: 74967b275a61fb33
tier: B
priority: 6.3
family: pipeline-infra
category: pipeline-infra
debt_type: infrastructure
type_id: null
severity: 3
effort: S
diff: NEW
```

### Proof

refund.py:39-40 uses `log.exception` for the OSError path, but line 41 uses bare `print()` for the normal-outcome message in the same function, on the same code path a few lines later. There is no __main__ guard or CLI parsing in this module (it's a library import per refund.py:1), so the print goes to stdout uncontrolled by log level/handlers, breaking aggregation for a production refund outcome. Real, low-effort fix (swap to log.info).

### Evidence

- `src/pay/refund.py:39-41`

```
        log.exception("gateway unreachable for %s", refund.order_id)
        raise RuntimeError("gateway unreachable") from exc
    print(f"refund {refund.order_id} accepted={accepted}")
```

### Signals

- hotspot score 100.0, churn 7, coupling pairs 1, fan-in 2 (approximate)
- confirmed by: coupling, hotspot, pattern:stdout-write, satd, scout:pipeline-infra

### Remediation

`src/pay/refund.py` is imported as a library, so the refund outcome at line 41 should not go to stdout. Emit it on the `log` logger already bound at line 11, at info level, with lazy `%s` arguments to match the `log.exception` call two lines above; leave the gateway-unreachable path exactly as it is. While the file is open, sweep the rest of `src/pay/` for other stdout writes and convert them in the same change, so the module has one output channel rather than two on the same code path.

### Acceptance criteria

- [ ] No stdout write remains in `src/pay/refund.py`; the refund outcome goes through `log`.
- [ ] The outcome message uses lazy `%s` logger arguments rather than an f-string.
- [ ] The gateway-unreachable path still logs via `log.exception` and re-raises unchanged.

# Below the cut

## Gateway.refund() HTTP call has zero test coverage

```yaml
status: pending
slug: gateway-refund-http-call-has-zero-test-coverage
fingerprint: 6be2f463cba67c1e
tier: A
priority: 5.808
family: test-gaps
category: test-gaps
debt_type: test
type_id: TD-04
severity: 4
effort: S
diff: NEW
```

### Proof

tests/test_refund.py:19-21 has `test_issue_calls_gateway` marked `@pytest.mark.skip(reason="gateway stub not written yet")` with body `raise NotImplementedError`. No other test file (tests/test_ledger.py, conftest.py, fixtures/seed.py) references Gateway or refund(). conftest.py:9-11 only provides a Refund fixture, no gateway stub. Gateway.refund is therefore fully unexercised, confirming zero coverage on a real refund-issuing HTTP call.

### Evidence

- `src/pay/gateway.py:19-24`

```
    def refund(self, order_id: str, amount_cents: int) -> bool:
        response = requests.post(
            f"{self.base}/refunds",
            json={"order": order_id, "amount": amount_cents},
            headers={"Authorization": f"Bearer {api_key}", **CORS_HEADERS},
            verify=False,
```

## Gateway refund POST has no timeout

```yaml
status: pending
slug: gateway-refund-post-has-no-timeout
fingerprint: a17a78d98f9e7beb
tier: A
priority: 5.808
family: half-finished
category: half-finished
debt_type: code
type_id: null
severity: 4
effort: S
diff: NEW
```

### Proof

gateway.py:20-25 `requests.post(...)` has no `timeout` kwarg. refund.py:37 calls `gateway.refund(...)` synchronously inside `issue()`, which is the real money-movement path (invoked as the Dockerfile CMD `python -m pay.refund`). An unresponsive gateway would block the caller indefinitely, matching the described risk exactly.

### Evidence

- `src/pay/gateway.py:20-25`

```
response = requests.post(
            f"{self.base}/refunds",
            json={"order": order_id, "amount": amount_cents},
            headers={"Authorization": f"Bearer {api_key}", **CORS_HEADERS},
            verify=False,
        )
```

## Live-looking payment gateway API key hardcoded in source

```yaml
status: pending
slug: live-looking-payment-gateway-api-key-hardcoded-in-source
fingerprint: 3aad01488c771d47
tier: B
priority: 5.082
family: security
category: security
debt_type: security
type_id: TD-03
severity: 5
effort: S
diff: NEW
```

### Proof

gateway.py:11 hardcodes `api_key = "sk_l***"`, matching Stripe's live-secret-key shape (sk_live_ prefix + random suffix). It's module-level in production source (not tests/fixtures), used directly as the Authorization bearer at line 23 for real POST refunds (line 20-25), with `verify=False` (TLS disabled) and a wildcard CORS header alongside it. No suppression comment or test/fixture context nearby. This is a genuine hardcoded live-looking credential in the money-movement path.

### Evidence

- `src/pay/gateway.py:19-25`

```
def refund(self, order_id: str, amount_cents: int) -> bool:
        response = requests.post(
            f"{self.base}/refunds",
            json={"order": order_id, "amount": amount_cents},
            headers={"Authorization": f"Bearer {api_key}", **CORS_HEADERS},
            verify=False,
        )
```

- `src/pay/gateway.py:12-12`

```
CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}
```

- `src/pay/gateway.py:11-11`

```
api_key = "sk_l***"
```

## Ownership gaps in src/pay/gateway.py

```yaml
status: pending
slug: ownership-gaps-in-src-pay-gateway-py
fingerprint: c908b30f7c99dc87
tier: A
priority: 4.356
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

- `src/pay/gateway.py:None-None`

```
src/pay/gateway.py: 100% of lines by one author, 1 author(s) in the window
```

## Refund.issue() gateway/ledger interaction guarded only by a skipped test

```yaml
status: pending
slug: refund-issue-gateway-ledger-interaction-guarded-only-by-a-skippe
fingerprint: f9f1100485b2696b
tier: A
priority: 3.9075
family: test-gaps
category: test-gaps
debt_type: test
type_id: TD-04
severity: 5
effort: M
diff: NEW
```

### Proof

issue() at refund.py:24-42 is untested (only test skipped at test_refund.py:19-21). Lines 31-34 wrap ledger.post in bare 'except Exception: pass', so a ledger write failure is swallowed and execution still proceeds to call the gateway at line 37 — money can move with no corresponding ledger entry. Line 35's FIXME confirms a known duplicate-post risk in the same unguarded path. No test asserts call order, exception handling, or the duplicate-refund guard (_seen set, line 27-29). This is a real financial-correctness gap, not just a style nit.

### Evidence

- `tests/test_refund.py:19-21`

```
@pytest.mark.skip(reason="gateway stub not written yet")
def test_issue_calls_gateway() -> None:
    raise NotImplementedError
```

- `src/pay/refund.py:33-38`

```
    except Exception:
        pass
    # FIXME: the gateway retries on our behalf, so a duplicate refund can post twice
    try:
        accepted = gateway.refund(refund.order_id, refund.amount_cents)
    except OSError as exc:
```

## Ownership gaps in src/pay/models.py

```yaml
status: pending
slug: ownership-gaps-in-src-pay-models-py
fingerprint: 10a292b59f942eaf
tier: A
priority: 3.15
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

- `src/pay/models.py:None-None`

```
src/pay/models.py: 89% of lines by one author, 2 author(s) in the window
```

## ledger.reverse() test asserts only that code runs, not its output

```yaml
status: pending
slug: ledger-reverse-test-asserts-only-that-code-runs-not-its-output
fingerprint: e36a78256ef7b76e
tier: A
priority: 3.126
family: test-gaps
category: test-gaps
debt_type: test
type_id: TD-04
severity: 3
effort: S
diff: NEW
```

### Proof

ledger.py:29-30 shows reverse() returns a new Entry with amount_cents negated and reason='reversal'. tests/test_ledger.py:18-19 calls ledger.reverse(...) and discards the return value with no assert whatsoever. Grep for 'reverse' across the repo shows no other test references it, so this is genuinely the only coverage and it is assert-free. A regression that dropped the sign flip or hardcoded a different reason string would not be caught.

### Evidence

- `tests/test_ledger.py:18-19`

```
def test_reverse_smoke() -> None:
    ledger.reverse(Entry(account="a", amount_cents=100))
```

## CI workflow gaps in .github/workflows/release.yml

```yaml
status: pending
slug: ci-workflow-gaps-in-github-workflows-release-yml
fingerprint: 56bed476273d3727
tier: A
priority: 3.0
family: pipeline-infra
category: pipeline-infra
debt_type: build
type_id: TD-14
severity: 3
effort: S
diff: NEW
```

### Proof

verified by construction

### Evidence

- `.github/workflows/release.yml:6-6`

```
publish:
```

- `.github/workflows/release.yml:6-6`

```
publish:
```

## SQL f-string interpolation of refund_id, nosec with no justification

```yaml
status: pending
slug: sql-f-string-interpolation-of-refund-id-nosec-with-no-justificat
fingerprint: d0af6b85d7b41fd1
tier: B
priority: 2.87
family: security
category: security
debt_type: security
type_id: TD-03
severity: 4
effort: S
diff: NEW
```

### Proof

Line 11 interpolates refund_id directly into SQL via f-string with a bare '# nosec' (no justification text). Line 13 runs a shell command with shell=True and a bare '# noqa: S602'. Both are genuine injection-prone patterns; refund_id is a caller-supplied parameter with no validation. No in-repo caller exists (confirmed by grep), but the module docstring states it's kept for an active external v1 reporting job, so reachability cannot be ruled out. The suppressions are unexplained regardless of current reachability.

### Evidence

- `src/pay/legacy_export.py:13-13`

```
subprocess.run("mail -s report finance@example.com", shell=True)  # noqa: S602
```

- `src/pay/legacy_export.py:8-11`

```
def export_v1(refund_id: str, db: str = "refunds.db") -> list[tuple[str, int]]:
    con = sqlite3.connect(db)
    cur = con.cursor()
    cur.execute(f"SELECT id, amount FROM refunds WHERE id = '{refund_id}'")  # nosec
```

## Gateway call path untested, skipped with vague reason

```yaml
status: pending
slug: gateway-call-path-untested-skipped-with-vague-reason
fingerprint: 67e0dcc512d6ba39
tier: A
priority: 2.3445
family: half-finished
category: half-finished
debt_type: requirement
type_id: null
severity: 3
effort: M
diff: NEW
```

### Proof

test_refund.py:19-21 skips test_issue_calls_gateway with reason='gateway stub not written yet' — no ticket, no owner, no date. refund.py:35 has an adjacent unresolved 'FIXME: the gateway retries on our behalf, so a duplicate refund can post twice' directly inside issue(), the function the skipped test targets. gateway.py:19-27 shows refund() is a real (non-stub) implementation already, so the stated skip reason is stale/inaccurate as well as vague.

### Evidence

- `tests/test_refund.py:19-21`

```
@pytest.mark.skip(reason="gateway stub not written yet")
def test_issue_calls_gateway() -> None:
    raise NotImplementedError
```

## test_reverse_smoke exercises reverse() logic with no assertions

```yaml
status: pending
slug: test-reverse-smoke-exercises-reverse-logic-with-no-assertions
fingerprint: 92c2c6c4c06ada32
tier: B
priority: 2.1882
family: test-quality
category: test-quality
debt_type: test
type_id: TD-18
severity: 3
effort: S
diff: NEW
```

### Proof

test_ledger.py:18-19 calls `ledger.reverse(Entry(...))` and discards the return value with no assert. ledger.reverse (ledger.py:29-30) negates amount_cents and sets reason='reversal' -- real business logic, not a startup/import smoke check. A regression that flipped the sign or dropped the reason field would not fail this test. Not table-driven/parametrised, not a permission/kill-switch check.

### Evidence

- `tests/test_ledger.py:18-19`

```
def test_reverse_smoke() -> None:
    ledger.reverse(Entry(account="a", amount_cents=100))
```

- `tests/test_ledger.py:13-15`

```
    ledger.post(Entry(account="a", amount_cents=100), path)
    time.sleep(0.05)  # flaky on CI without this; retried in the workflow
    assert ledger.balance("a", path) == 100
```

## v1 CSV export left in place past its own removal ticket

```yaml
status: pending
slug: v1-csv-export-left-in-place-past-its-own-removal-ticket
fingerprint: 336fccbd19191237
tier: B
priority: 2.1525
family: migration
category: migration
debt_type: design
type_id: null
severity: 3
effort: S
diff: NEW
```

### Proof

export_v1 (legacy_export.py:8-14) has zero call sites confirmed by repo-wide grep for 'export_v1'/'legacy_export' outside its own definition. TODO(#42) at line 7 references a v2 report that doesn't exist anywhere in the repo (no export_v2, no mention in README/CHANGELOG/docs). Commented-out export_v0 stub at lines 17-19 confirms a prior migration was also never cleaned up. This is real orphaned migration debt.

### Evidence

- `src/pay/legacy_export.py:1-8`

```
"""Legacy CSV export kept for the v1 reporting job."""
from __future__ import annotations

import sqlite3
import subprocess

# TODO(#42): delete once finance moves to the v2 report
def export_v1(refund_id: str, db: str = "refunds.db") -> list[tuple[str, int]]:
```

- `src/pay/legacy_export.py:17-19`

```
# def export_v0(refund_id):
#     rows = fetch(refund_id)
#     return rows
```

## README claims exporter.py removed but legacy_export.py still exists

```yaml
status: pending
slug: readme-claims-exporter-py-removed-but-legacy-export-py-still-exi
fingerprint: 37d90c120cb0525a
tier: B
priority: 2.1084
family: doc-drift
category: doc-drift
debt_type: documentation
type_id: TD-08
severity: 3
effort: S
diff: NEW
```

### Proof

README.md:10 names a path ('src/pay/exporter.py') that never appears in the repo (glob of src/pay/*.py shows legacy_export.py instead) and claims the job was removed in 0.1.0, but legacy_export.py:8 export_v1 still performs the same CSV-style export, still called nowhere else, still containing an f-string SQL query (line 11) and shell=True subprocess call (line 13). The README's removal claim is false; the job is live under a different name.

### Evidence

- `README.md:5-7`

```
## Run

    python -m pay.refund --help
```

- `src/pay/refund.py:1-11`

```
"""Refund workflow: validate, post to the ledger, notify the gateway."""
from __future__ import annotations

import logging

from pay import ledger
from pay.gateway import Gateway
from pay.models import Entry, Refund
from pay.utils import cents

log = logging.getLogger(__name__)
```

- `README.md:1-9`

```
# pay-service

Refund and ledger service.

## Run

    python -m pay.refund --help

Code lives in `src/pay/refund.py`; the design is in `docs/adr/0001-ledger.md`.
```

- `README.md:10-10`

```
The old `src/pay/exporter.py` job was removed in 0.1.0.
```

- `src/pay/legacy_export.py:1-8`

```
"""Legacy CSV export kept for the v1 reporting job."""
from __future__ import annotations

import sqlite3
import subprocess

# TODO(#42): delete once finance moves to the v2 report
def export_v1(refund_id: str, db: str = "refunds.db") -> list[tuple[str, int]]:
```

## Version bumped in pyproject.toml with no matching tag/changelog/release run

```yaml
status: pending
slug: version-bumped-in-pyproject-toml-with-no-matching-tag-changelog
fingerprint: 1f9c7d8ac03999e4
tier: B
priority: 2.1
family: pipeline-infra
category: pipeline-infra
debt_type: build
type_id: null
severity: 3
effort: S
diff: NEW
```

### Proof

release.yml:2-4 only triggers on pushed 'v*' tags and has no step diffing the tag against pyproject.toml's version (lines 10-12 just build and upload). pyproject.toml:3 is already at 0.2.0 while CHANGELOG.md tops out at 0.1.0, meaning the 0.2.0 bump happened without a corresponding tag/release run or changelog update — a manual, unverified version bump. Real pipeline gap.

### Evidence

- `pyproject.toml:3-3`

```
version = "0.2.0"
```

- `CHANGELOG.md:1-5`

```
# Changelog

## 0.1.0 - 2024-10-05

- initial refund and ledger flow
```

- `.github/workflows/release.yml:1-4`

```
name: release
on:
  push:
    tags: ["v*"]
```

## Application ships two divergent dependency declarations for requests

```yaml
status: pending
slug: application-ships-two-divergent-dependency-declarations-for-requ
fingerprint: ecf0205d7d75e559
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

pyproject.toml:5 declares floating `requests>=2.31` while requirements.txt:1 pins `requests==2.32.3`. Dockerfile (lines 4-5) and ci.yml (line 11) both install only from requirements.txt, never from pyproject.toml, and no lockfile exists. setup.py is a bare setuptools shim pointing back at pyproject.toml, so the pyproject dependency spec is real but unused/unenforced metadata that has silently diverged from what's actually built and tested. Confusing but low-impact since it's never installed.

### Evidence

- `pyproject.toml:5-5`

```
dependencies = ["requests>=2.31"]
```

- `requirements.txt:1-1`

```
requests==2.32.3
```

## Coverage gate defined but never invoked in CI

```yaml
status: pending
slug: coverage-gate-defined-but-never-invoked-in-ci
fingerprint: fac69799ae0e21ac
tier: B
priority: 2.1
family: test-gaps
category: test-gaps
debt_type: test
type_id: TD-04
severity: 3
effort: S
diff: NEW
```

### Proof

ci.yml:12 runs bare `pytest -q` with no `--cov` flag or coverage invocation, so the `[tool.coverage.report] fail_under = 80` block (pyproject.toml:7-8) is dead configuration - coverage.report only enforces a threshold when preceded by `coverage run`/`--cov`. Neither pytest-cov nor coverage appear in requirements.txt. gateway.py (0 real tests, see candidate 4) and legacy_export.py (0 callers/tests) can merge untested with the gate never tripping.

### Evidence

- `pyproject.toml:7-8`

```
[tool.coverage.report]
fail_under = 80
```

- `.github/workflows/ci.yml:11-12`

```
      - run: pip install -r requirements.txt
      - run: pytest -q
```

## Dependency manifest gaps in pyproject.toml

```yaml
status: pending
slug: dependency-manifest-gaps-in-pyproject-toml
fingerprint: 495747bed5818465
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

- `pyproject.toml:1-1`

```
[project]
```

## CI workflow gaps in .github/workflows/ci.yml

```yaml
status: pending
slug: ci-workflow-gaps-in-github-workflows-ci-yml
fingerprint: 628faae80f817909
tier: A
priority: 2.0
family: pipeline-infra
category: pipeline-infra
debt_type: build
type_id: TD-14
severity: 2
effort: S
diff: NEW
```

### Proof

verified by construction

### Evidence

- `.github/workflows/ci.yml:4-4`

```
test:
```

- `.github/workflows/ci.yml:4-4`

```
test:
```

- `.github/workflows/ci.yml:5-5`

```
runs-on: ubuntu-latest
```

- `.github/workflows/ci.yml:7-7`

```
- uses: actions/checkout@v4
```

- `.github/workflows/ci.yml:8-8`

```
- uses: actions/setup-python@v5
```

- `.github/workflows/ci.yml:4-4`

```
test:
```

## Container configuration gaps in Dockerfile

```yaml
status: pending
slug: container-configuration-gaps-in-dockerfile
fingerprint: b10028c3d26d421c
tier: A
priority: 2.0
family: pipeline-infra
category: pipeline-infra
debt_type: infrastructure
type_id: TD-19
severity: 2
effort: S
diff: NEW
```

### Proof

verified by construction

### Evidence

- `Dockerfile:3-3`

```
RUN apt-get update && apt-get install -y curl
```

- `Dockerfile:1-1`

```
FROM python:3.11-slim
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

- `None:None-None`

```
no CODEOWNERS file with 3 human authors
```

## Release process gaps

```yaml
status: pending
slug: release-process-gaps
fingerprint: ce6c51b2a87e9ed3
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

- `None:None-None`

```
branch hotfix/ledger-rounding unmerged, last commit 2026-04-10 (147 days ago)
```

## Flaky ledger test papered over with sleep

```yaml
status: pending
slug: flaky-ledger-test-papered-over-with-sleep
fingerprint: b1f9606f10dd3ee8
tier: B
priority: 1.4588
family: half-finished
category: half-finished
debt_type: defect
type_id: null
severity: 2
effort: S
diff: NEW
```

### Proof

test_ledger.py:14 has `time.sleep(0.05)  # flaky on CI without this; retried in the workflow` -- a self-admitted race being masked by a fixed sleep plus workflow-level retries, matching commit 5334fe2 'test: retry flaky ledger test' in recent history. post() (ledger.py:12-15) and balance() (ledger.py:18-26) are synchronous file I/O with no async/threading, so the sleep is compensating for an unidentified race rather than a real inherent delay. No ticket reference in the code.

### Evidence

- `tests/test_ledger.py:11-15`

```
def test_post_then_balance(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    ledger.post(Entry(account="a", amount_cents=100), path)
    time.sleep(0.05)  # flaky on CI without this; retried in the workflow
    assert ledger.balance("a", path) == 100
```

## CHANGELOG has no entry for the 0.2.0 release already in pyproject.toml

```yaml
status: pending
slug: changelog-has-no-entry-for-the-0-2-0-release-already-in-pyprojec
fingerprint: 7eb44fa443b9caee
tier: B
priority: 1.4
family: doc-drift
category: doc-drift
debt_type: documentation
type_id: TD-08
severity: 2
effort: S
diff: NEW
```

### Proof

pyproject.toml:3 declares version 0.2.0 but CHANGELOG.md:1-5 stops at '0.1.0 - 2024-10-05' with no 0.2.0 section. Git log shows gateway v2 migration and refund audit trail commits landed after that tag, none reflected in the changelog. Real, low-impact doc drift.

### Evidence

- `CHANGELOG.md:1-5`

```
# Changelog

## 0.1.0 - 2024-10-05

- initial refund and ledger flow
```

- `pyproject.toml:1-3`

```
[project]
name = "pay-service"
version = "0.2.0"
```

## Dependency manifest split between pyproject.toml and requirements.txt

```yaml
status: pending
slug: dependency-manifest-split-between-pyproject-toml-and-requirement
fingerprint: e4e3d0cfb7d0981c
tier: B
priority: 1.4
family: migration
category: migration
debt_type: dependency
type_id: null
severity: 2
effort: S
diff: NEW
```

### Proof

setup.py:1 states 'pyproject.toml is the source of truth' for packaging, yet ci.yml:11 runs 'pip install -r requirements.txt' rather than installing the package's own dependencies. requirements.txt:1 pins requests==2.32.3 while pyproject.toml:5 declares requests>=2.31 — two manifests can drift silently since CI only ever installs from the former. No consolidation plan is stated anywhere in the repo. Real split-manifest debt.

### Evidence

- `pyproject.toml:4-5`

```
requires-python = ">=3.11"
dependencies = ["requests>=2.31"]
```

- `requirements.txt:1-1`

```
requests==2.32.3
```

- `.github/workflows/ci.yml:11-11`

```
      - run: pip install -r requirements.txt
```

# Below the cut: tier C and unverified

| slug | family | file | reason |
| --- | --- | --- | --- |
| refund-issue-partial-has-no-callers-in-production-or-tests | dead-code | src/pay/refund.py | confirm |
| legacy-export-bypasses-the-ledger-writing-refund-data-to-a-secon | architecture | src/pay/legacy_export.py | unverified |
| export-v1-and-its-legacy-export-module-have-zero-callers | dead-code | src/pay/legacy_export.py | confirm |
| utils-fingerprint-has-no-callers-anywhere-in-the-repo | dead-code | src/pay/utils.py | confirm |
| audit-trail-assertion-hard-codes-a-string-built-from-fixture-val | test-quality | tests/test_refund.py | downgrade |
| legacy-export-export-v1-has-no-automated-test | test-gaps | src/pay/legacy_export.py | downgrade |

# Considered and rejected

- **Entry sign-flip construction duplicated in refund.py and ledger.py** - `src/pay/refund.py` - coincidental single-line negation flagged as meaningful duplication due to file-level change coupling, not actual copied logic
- **Removed exporter still referenced in README while a same-purpose module remains** - `README.md` - golden trap: intentional fixture

# Looks bad but is fine

- `src/pay/gateway.py:19` - Inventory flagged longest_indented_run=8 / deep_indent_lines=4, but this is a single multi-line requests.post(...) call with keyword arguments spanning lines, not nested branching. The method has one straight-line statement sequence and no conditionals or loops.
- `src/pay/ledger.py:18` - Inventory flagged longest_indented_run=3 / max_indent=3, but this is a single for-loop with one if inside (balance()) — a simple accumulate-and-filter loop, not a multi-branch or deeply nested unit.
- `src/pay/refund.py:24` - issue() has two try/except blocks and an early return, but each block is 2-4 lines with no nested conditionals; control flow is linear and easy to follow despite being the top hotspot-scored file.
- `src/pay/refund.py:1` - Highest hotspot score in the repo, but it is a small (52 LOC) module with one cohesive responsibility (refund workflow: validate, post, notify gateway). Functions share the Refund/Entry data directly rather than reaching through object chains; not a god-class.
- `src/pay/gateway.py:15` - Gateway class has a single method and two attributes; it is a thin API-client facade by design, not a god-class.
- `src/pay/models.py:7` - Entry and Refund are plain dataclasses (DTOs), wide-by-design and not god-class candidates.
- `src/pay/ledger.py:13` - record dict built from Entry fields for JSON persistence looks similar to refund.audit_trail's string formatting, but they serialize to different targets (disk log vs audit string) for different reasons to change; not the same duplication.
- `src/pay/ledger.py:29` - reverse() has no production caller in src/, but ADR 0001 (docs/adr/0001-ledger.md) documents reversals-as-new-entries as the intended design, and it is exercised by tests/test_ledger.py::test_reverse_smoke.
- `src/pay/refund.py:36` - except OSError at line 38 logs with log.exception (preserves traceback) and re-raises as RuntimeError with 'from exc', preserving the cause chain. This is a boundary conversion, not masking.
- `src/pay/models.py:7` - Entry and Refund are plain dataclasses with no logic; they are exercised indirectly through refund/ledger tests and fit the 'glue/config rarely needs unit tests' trap.
- `tests/test_ledger.py:11` - test_post_then_balance does assert real behavior (balance equals posted amount) despite the odd sleep(0.05); the sleep is a reliability workaround, not a coverage gap.
- `src/pay/legacy_export.py:7` - TODO(#42) names a ticket and a concrete deferral condition (delete once finance moves to v2 report); this is a tracked, deliberate deferral rather than an unmanaged stub.
- `setup.py:1` - Four-line setuptools shim that explicitly documents pyproject.toml as the source of truth and duplicates only the package name; this is a stated, finished packaging decision, not active dual-path churn.
- `src/pay/gateway.py:10` - Single migration commit fully switched the module to the v2 API base URL; no v1 endpoint or dual-path code remains in the file.
- `setup.py:1` - setup.py is a no-op shim deferring to pyproject.toml, not a competing build system; not a dependency-duplication finding.
- `docs/übersicht.md:1` - Flagged as stale, but content is a one-line placeholder with no technical claims about code, so there is nothing for the code to contradict.
- `docs/adr/0001-ledger.md:5` - Flagged as stale, but the described design (JSON-lines append-only ledger, reversals as new entries) matches src/pay/ledger.py's current implementation.
- `src/pay/refund.py:6` - refund.py imports ledger, gateway, models, and utils but none of those import back from refund.py, so this is a simple acyclic layering, not a dependency cycle.
- `tests/fixtures/seed.py:2` - api_key value is 'sk_test_placeholder_xxx_do_not_use', clearly a test fixture placeholder, not a real credential.
- `tests/test_ledger.py:15` - assert ledger.balance("a", path) == 100 restates the amount_cents=100 posted two lines above in the same test, so the value is locally traceable rather than an unexplained magic number.
- `.github/workflows/ci.yml:1` - Differs substantially in purpose/steps from release.yml (test job vs. publish job); not hand-copied duplication.
- `.github/workflows/release.yml:10` - Checkout action is pinned to a full commit SHA rather than a floating tag — this is a stricter, not weaker, practice.
- `Dockerfile:1` - Base image tag is pinned to python:3.11-slim (not a floating `latest`), and there is no separate dev-only compose/override file in the repo to compare against.
- `src/pay/refund.py:30` - coincidental single-line negation flagged as meaningful duplication due to file-level change coupling, not actual copied logic
- `README.md:9` - golden trap: intentional fixture

# Open questions for the maintainer

- `src/pay/refund.py:51` - audit_trail() is only called from one test (test_audit_trail_format) and not from issue()/issue_partial(); is it wired into any production caller outside this repo, or awaiting integration?
- `src/pay/legacy_export.py:8` - Is export_v1 still called by any live finance job, or is it fully dead pending TODO(#42) removal? That determines whether test-gap severity should rise.
- `src/pay/gateway.py:1` - quote not found: invented quote (golden pin)
- `tests/test_refund.py:19` - Is there a ticket tracking the gateway stub/test, or was this skip left open-ended with no owner?
- `src/pay/refund.py:35` - Is idempotency on the gateway or ledger side planned to close the duplicate-refund gap named in the FIXME?
- `README.md:10` - README states the old src/pay/exporter.py job was removed in 0.1.0, but a differently-named legacy_export.py with export_v1 still exists — is this the same job under a new filename, or an unrelated leftover?
- `src/pay/gateway.py:10` - gateway.py migration_commits=1 corresponds to commit b2d3792 'migrate gateway to v2 API' — no v1 gateway code remains, so is there anything left to assess here or is this migration already complete?
- `pyproject.toml:5` - Is pyproject.toml's dependency list actually used for any install path, or is requirements.txt the sole real source of truth (making the pyproject entry dead metadata)?
- `src/pay/legacy_export.py:8` - Is refunds.db (sqlite3) intended to stay a permanent secondary store for the v1 report, or should this module read through ledger.py instead?
- `src/pay/utils.py:11` - fingerprint() uses md5 on order_id but has no callers anywhere in the repo; cannot determine whether it is intended for a security-sensitive purpose (identity/token) or a non-security dedup/cache key, which would make the weak hash a non-finding per the stated trap.
- `src/pay/refund.py:1` - Dockerfile CMD runs `python -m pay.refund` but this module has no `if __name__ == "__main__"` block or argument parsing, and README claims `python -m pay.refund --help` works — is there an intended CLI entry point missing, or is the Dockerfile CMD stale?

# Not assessed

- Families not run: none
- Tools: the tool probe lands in phase 4, so currency, end-of-life and vulnerability claims are not assessed
- Runtime-only: coverage numbers, flake confirmation, model staleness, rollout state, deploy frequency
- By design: magic literals, convention violations, and class-level metrics that need a parser
