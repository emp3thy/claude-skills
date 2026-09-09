---
schema_version: 2
scan_date: 2026-09-09
root: C:\Users\gethi\AppData\Local\Temp\live-service-py-t38wxoel
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
tools_run:
- lizard
- ruff
- vulture
tools_absent:
- actionlint (absent)
- gitleaks (absent)
- hadolint (absent)
- jscpd (skipped)
- knip (skipped)
- madge (skipped)
- osv-scanner (absent)
git_available: true
counts:
  candidates: 35
  quote_failed: 0
  verified: 35
  tier_a: 21
  tier_b: 11
  tier_c: 2
  unverified: 0
  rejected: 1
  suppressed: 0
---

# Tech-debt scan - 2026-09-09

Scanned `C:\Users\gethi\AppData\Local\Temp\live-service-py-t38wxoel` - 16 files, 243 LOC across: markdown, python.

Review each finding below. To act on one, change its `status:` from `pending` to
`approved`, `rejected`, or `accepted` (add a `reason:` and an optional `until:` ISO
date), then run `/tech-debt-promote`.

Top hotspots: `src/pay/refund.py` (100.0), `src/pay/ledger.py` (52.9), `src/pay/gateway.py` (20.2), `src/pay/models.py` (5.0), `tests/test_ledger.py` (4.2).

Top coupled pairs: `src/pay/ledger.py` <-> `src/pay/refund.py` (shared 5, ratio 0.714).

# Top 5

## Ledger post failure silently swallowed before gateway refund

```yaml
status: pending
slug: ledger-post-failure-silently-swallowed-before-gateway-refund
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

refund.py:31-34 catches ledger.post's Exception and passes silently — no log call, no re-raise, no flag set. Execution then proceeds unconditionally to call gateway.refund (line 37) and move real money, so a ledger write failure and a successful gateway refund can diverge with zero record of the cause. This is not a boundary catch that reports (contrast with the OSError handler at 38-40, which does log.exception and re-raise), so the 'boundary catch that reports and continues' trap does not apply.

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
- confirmed by: coupling, hotspot, pattern:swallowed-catch, satd, scout:error-masking, tool:ruff

### Remediation

Remove the bare except/pass around ledger.post in issue(). Log the exception with log.exception including refund.order_id, then decide and implement one explicit failure path: either re-raise so the caller aborts before calling gateway.refund, or set an explicit failure flag and skip the gateway call, returning False. Do not let execution fall through to gateway.refund when ledger.post has failed. Add a unit test that makes ledger.post raise and asserts gateway.refund is never called and the failure is logged/raised.

### Acceptance criteria

- [ ] The except Exception: pass block around ledger.post is gone; the except clause calls log.exception (or equivalent) with refund.order_id
- [ ] When ledger.post raises, gateway.refund is not invoked (verified by mock in a new/updated test)
- [ ] issue() either re-raises or returns a value/flag reflecting the ledger failure, and this behavior is asserted in a test
- [ ] Existing passing tests (test_validate_rejects_zero, test_audit_trail_format) still pass

## Duplicate-refund FIXME names live money risk, no ticket, unresolved

```yaml
status: pending
slug: duplicate-refund-fixme-names-live-money-risk-no-ticket-unresolve
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

The FIXME at refund.py:35 states gateway-side retries can double-post a refund. The only guard is the in-process `_seen` set (lines 14, 27-29), which only prevents issue() from being called twice for the same order_id in-process — it does nothing if the gateway itself retries its own outbound call after a timeout, exactly as the comment says. No ticket reference accompanies the FIXME (unlike legacy_export's '#42'), and the risk directly affects real money movement via gateway.refund (line 37). Not an abstract contract or documented deferral.

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

- `src/pay/refund.py:27-29`

```
    if refund.order_id in _seen:
        return False
    _seen.add(refund.order_id)
```

### Signals

- hotspot score 100.0, churn 7, coupling pairs 1, fan-in 2 (approximate)
- confirmed by: coupling, hotspot, satd, scout:half-finished

### Remediation

Replace the FIXME comment with a tracked ticket reference and an actual guard against gateway-side duplicate refunds. The in-process _seen set only covers calls within the same process, so add an idempotency mechanism that survives process restarts and gateway retries, e.g., pass an idempotency key derived from order_id to gateway.refund if the gateway API supports one, or persist processed order_ids (via the ledger or a dedicated store) and check that persisted record before calling gateway.refund. Update or remove the FIXME comment once the guard is implemented, replacing it with a reference to the ticket tracking any remaining follow-up.

### Acceptance criteria

- [ ] FIXME comment at refund.py:35 is replaced with either removal (if fully fixed) or a ticket reference (e.g., '# TICKET-123') if follow-up work remains
- [ ] A persistent or gateway-level idempotency mechanism exists that prevents duplicate refunds across process restarts, not just via the in-memory _seen set
- [ ] A test demonstrates that calling issue() twice for the same order_id (including simulating a fresh process, i.e., empty _seen) does not result in two gateway.refund calls

## issue_partial() in refund.py has no callers

```yaml
status: pending
slug: issue-partial-in-refund-py-has-no-callers
fingerprint: c716d4382547d1ce
tier: A
priority: 9.0
family: dead-code
category: dead-code
debt_type: code
type_id: null
severity: 3
effort: S
diff: NEW
```

### Proof

issue_partial (refund.py:45-48) has no callers: repo-wide grep for 'issue_partial' finds only its own definition in src/pay/refund.py; tests/conftest.py:1-11 defines only a 'refund' fixture, tests/test_refund.py:1-21 references validate, audit_trail, and a skipped test_issue_calls_gateway — no mention of issue_partial. No __all__, __init__.py re-export (src/pay/__init__.py is a bare docstring), console_scripts, or entry_points exist anywhere, so it is not a public/plugin surface. No reflection/getattr/dispatch patterns found repo-wide. refund.py is confirmed high-churn (git log shows recent refund-related commits). Real dead code.

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
- confirmed by: coupling, hotspot, satd, scout:dead-code, tool:vulture

### Remediation

Delete issue_partial() from refund.py since it has no callers, no test coverage, and is not exposed via __all__, package re-export, or entry points. Before deleting, run a final repo-wide search for 'issue_partial' to confirm no external callers were missed. Remove the function and its now-unused imports if cents or Refund construction become unused elsewhere in the file after deletion.

### Acceptance criteria

- [ ] issue_partial() function is removed from src/pay/refund.py
- [ ] Repo-wide grep for 'issue_partial' returns no remaining references
- [ ] Any imports in refund.py that were only used by issue_partial are removed if no longer needed
- [ ] Existing test suite still passes after removal

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

- `src/pay/refund.py` (whole file)

```
src/pay/refund.py: 100% of lines by one author, 1 author(s) in the window
```

### Signals

- hotspot score 100.0, churn 7, coupling pairs 1, fan-in 2 (approximate)
- confirmed by: rule:ownership.knowledge-island

### Remediation

Add a second reviewer for src/pay/refund.py given it handles live money movement and currently has single-author coverage. Require at least one other engineer to review upcoming changes to this file (e.g., via CODEOWNERS entry or branch protection rule), and have that reviewer read through the current implementation to build familiarity before the next change lands, rather than reviewing cold.

### Acceptance criteria

- [ ] A CODEOWNERS entry (or equivalent review-routing rule) is added for src/pay/refund.py naming at least one reviewer besides the current sole author
- [ ] At least one additional engineer has read and can explain the current issue()/issue_partial()/validate() flow, confirmed via a brief written summary or review comment
- [ ] The next merged change to refund.py shows an approving review from someone other than the original author

## issue_partial() proportional refund math is untested

```yaml
status: pending
slug: issue-partial-proportional-refund-math-is-untested
fingerprint: 4b10ada7bef4b500
tier: B
priority: 8.4
family: test-gaps
category: test-gaps
debt_type: test
type_id: TD-04
severity: 4
effort: S
diff: NEW
```

### Proof

tests/test_refund.py contains only test_validate_rejects_zero, test_audit_trail_format, and a skipped test_issue_calls_gateway — no reference to issue_partial. tests/conftest.py defines only a single 'refund' fixture (order_id o-1, amount 500), with no partial-refund or fraction-based fixtures/tests elsewhere. The fractional cents() rounding at refund.py:46 is therefore unverified by any test path found.

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

Add test coverage for issue_partial() in tests/test_refund.py, exercising the fractional cents() rounding at refund.py:46. Cover a case with an exact fraction (no rounding needed), a fraction that requires rounding up, and a fraction that requires rounding down, asserting the resulting Refund.amount_cents matches the expected rounded value. Also add a fixture or parametrized case that verifies issue_partial() delegates to issue() with the computed partial Refund and returns its result, using a mock gateway.

### Acceptance criteria

- [ ] tests/test_refund.py contains at least one test that calls issue_partial() directly
- [ ] Test cases cover at least one fraction requiring rounding and assert the exact resulting amount_cents value
- [ ] A test verifies issue_partial() passes a Refund with the correct order_id and reason_code through to issue()/gateway.refund (via mock)
- [ ] New tests pass when run against the current implementation

# Below the cut

## print() used for refund outcome despite module-level logger

```yaml
status: pending
slug: print-used-for-refund-outcome-despite-module-level-logger
fingerprint: 51a39b39b64b8326
tier: B
priority: 6.3
family: pipeline-infra
category: pipeline-infra
debt_type: build
type_id: TD-35
severity: 3
effort: S
diff: NEW
```

### Proof

refund.py has a module logger (line 11) used correctly for the OSError branch (line 39: log.exception), but the success path at line 41 uses print() instead. Grep confirms refund.py has no `if __name__ == "__main__"` block, and issue() is called only from issue_partial() within the same library module — it is not a CLI entry point, so the 'CLI tool prints by design' trap does not apply.

### Evidence

- `src/pay/refund.py:11-11`

```
log = logging.getLogger(__name__)
```

- `src/pay/refund.py:38-41`

```
    except OSError as exc:
        log.exception("gateway unreachable for %s", refund.order_id)
        raise RuntimeError("gateway unreachable") from exc
    print(f"refund {refund.order_id} accepted={accepted}")
```

## Gateway HTTP call has no timeout, blocking the refund path indefinitely

```yaml
status: pending
slug: gateway-http-call-has-no-timeout-blocking-the-refund-path-indefi
fingerprint: a17a78d98f9e7beb
tier: A
priority: 5.808
family: half-finished
category: half-finished
debt_type: defect
type_id: null
severity: 4
effort: S
diff: NEW
```

### Proof

gateway.py:20-25 requests.post has no timeout kwarg. refund.py:37 calls gateway.refund() inside issue(), which only catches OSError (line 38) — a hang is not an OSError, so nothing unblocks the caller. No ticket or comment near the call documents this as accepted risk; refund.py:35 has an unrelated FIXME about duplicate refunds, not about timeouts.

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

## TLS certificate verification disabled for live payment gateway calls

```yaml
status: pending
slug: tls-certificate-verification-disabled-for-live-payment-gateway-c
fingerprint: a6c7df954c9f3c6b
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

gateway.py:11 hardcodes `api_key = "sk_l***"`, a live-looking Stripe-format secret (not a placeholder like the redacted 'sk_l***' shown in the candidate excerpt — the actual file has full high-entropy value), sent as a Bearer token over a connection with verify=False (line 24) to a production-looking host (API_BASE, line 10). refund.py:37 reaches this code on every real refund. No nearby comment justifies disabling TLS verification.

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

- `src/pay/gateway.py:11-11`

```
api_key = "sk_l***"
```

## Gateway.refund() has no mapped test at all

```yaml
status: pending
slug: gateway-refund-has-no-mapped-test-at-all
fingerprint: 6be2f463cba67c1e
tier: A
priority: 4.356
family: test-gaps
category: test-gaps
debt_type: test
type_id: TD-04
severity: 4
effort: M
diff: NEW
```

### Proof

Repo has exactly two test files (tests/test_refund.py, tests/test_ledger.py); grep for 'gateway'/'Gateway' only hits test_refund.py:19-21, an @pytest.mark.skip stub that raises NotImplementedError. No fixtures, conftest, or other suite reference Gateway. refund.py:37 calls gateway.refund(), gating whether issue() returns True/False, and that status-code-to-bool logic (gateway.py:27) is never exercised.

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

- `src/pay/gateway.py` (whole file)

```
src/pay/gateway.py: 100% of lines by one author, 1 author(s) in the window
```

## Gateway integration test skipped and stubbed with NotImplementedError

```yaml
status: pending
slug: gateway-integration-test-skipped-and-stubbed-with-notimplemented
fingerprint: 67e0dcc512d6ba39
tier: A
priority: 4.168
family: half-finished
category: half-finished
debt_type: requirement
type_id: null
severity: 4
effort: S
diff: NEW
```

### Proof

tests/test_refund.py:19-21 skips the only test touching issue()'s gateway path with reason 'gateway stub not written yet', but src/pay/gateway.py:19-27 shows Gateway.refund is a real, complete HTTP implementation. The skip reason is stale. No conftest fixture, no other test file (only test_ledger.py exists besides test_refund.py), and no mock-based test exercises refund.issue() or gateway.refund anywhere. No ticket reference is present in the skip reason or nearby comments, and issue() is a concrete workflow function, not an abstract/interface contract.

### Evidence

- `tests/test_refund.py:19-21`

```
@pytest.mark.skip(reason="gateway stub not written yet")
def test_issue_calls_gateway() -> None:
    raise NotImplementedError
```

## refund.issue() money-moving workflow untested; only stub is skipped

```yaml
status: pending
slug: refund-issue-money-moving-workflow-untested-only-stub-is-skipped
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

refund.py:24-42 issue() has: dedup via module-level _seen set (line 27-29), a swallowed ledger exception (lines 31-33, bare except/pass), and a FIXME at line 35 documenting a real double-refund race since gateway-side retries aren't guarded by _seen once it's already added at line 29. None of this is exercised: test_refund.py only covers validate() and audit_trail(); the sole issue()-path test is skip+NotImplementedError. test_ledger.py and conftest.py (checked) provide no coverage of issue() or Gateway.refund. Money-moving path with a self-documented race and a silently-swallowed exception, fully untested.

### Evidence

- `tests/test_refund.py:19-21`

```
@pytest.mark.skip(reason="gateway stub not written yet")
def test_issue_calls_gateway() -> None:
    raise NotImplementedError
```

- `src/pay/refund.py:35-40`

```
# FIXME: the gateway retries on our behalf, so a duplicate refund can post twice
    try:
        accepted = gateway.refund(refund.order_id, refund.amount_cents)
    except OSError as exc:
        log.exception("gateway unreachable for %s", refund.order_id)
        raise RuntimeError("gateway unreachable") from exc
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

- `src/pay/models.py` (whole file)

```
src/pay/models.py: 89% of lines by one author, 2 author(s) in the window
```

## test_reverse_smoke asserts nothing about reverse() behaviour

```yaml
status: pending
slug: test-reverse-smoke-asserts-nothing-about-reverse-behaviour
fingerprint: 39249604ec852bb2
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

test_reverse_smoke (test_ledger.py:18-19) calls ledger.reverse(...) and discards the return value entirely — no assignment, no assertion. ledger.reverse (ledger.py:29-30) is a pure function that builds and returns a new Entry with amount_cents negated and reason set to 'reversal'; it has no side effects (no file write, no print), so the test verifies nothing at all, not even that reverse runs without raising in a meaningful sense beyond exception-freedom. This is the only test exercising reverse(). Not a mere 'checks startup' smoke test since reverse is a pure data-transform function whose entire contract is its return value.

### Evidence

- `tests/test_ledger.py:11-15`

```
def test_post_then_balance(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    ledger.post(Entry(account="a", amount_cents=100), path)
    time.sleep(0.05)  # flaky on CI without this; retried in the workflow
    assert ledger.balance("a", path) == 100
```

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

## test_reverse_smoke asserts nothing on core reversal sign-flip logic

```yaml
status: pending
slug: test-reverse-smoke-asserts-nothing-on-core-reversal-sign-flip-lo
fingerprint: 92c2c6c4c06ada32
tier: B
priority: 2.1882
family: test-quality
category: test-quality
debt_type: test
type_id: TD-12
severity: 3
effort: S
diff: NEW
```

### Proof

ledger.reverse (ledger.py:29-30) negates amount_cents and hardcodes reason='reversal'; test_reverse_smoke (test_ledger.py:18-19) calls it and asserts nothing about either the sign flip or the reason field, so a regression to either (e.g. dropping the negation or reason string) would not be caught. Confirmed assertion-free by reading the test body directly. This overlaps with candidate ee0e5f40/[[test_reverse_smoke gap]] but is independently valid under the test-quality framing since it names the specific sign-flip/reason-field logic left unverified.

### Evidence

- `tests/test_ledger.py:18-19`

```
def test_reverse_smoke() -> None:
    ledger.reverse(Entry(account="a", amount_cents=100))
```

- `tests/test_ledger.py:11-15`

```
def test_post_then_balance(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    ledger.post(Entry(account="a", amount_cents=100), path)
    time.sleep(0.05)  # flaky on CI without this; retried in the workflow
    assert ledger.balance("a", path) == 100
```

## README run instructions reference a CLI that does not exist

```yaml
status: pending
slug: readme-run-instructions-reference-a-cli-that-does-not-exist
fingerprint: 1dafca3f71d91332
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

README.md:7 documents `python -m pay.refund --help`. refund.py:1-39 has no `if __name__ == "__main__"` guard or argparse/ArgumentParser. setup.py:1-4 is a bare shim with no entry_points/console_scripts. Repo-wide grep for argparse/ArgumentParser/console_scripts/__main__ found nothing under src/. Running the documented command would just import the module silently and ignore --help, not produce help text as implied.

### Evidence

- `README.md:1-10`

```
# pay-service

Refund and ledger service.

## Run

    python -m pay.refund --help

Code lives in `src/pay/refund.py`; the design is in `docs/adr/0001-ledger.md`.
The old `src/pay/exporter.py` job was removed in 0.1.0.
```

- `README.md:5-7`

```
## Run

    python -m pay.refund --help
```

- `src/pay/refund.py:1-9`

```
"""Refund workflow: validate, post to the ledger, notify the gateway."""
from __future__ import annotations

import logging

from pay import ledger
from pay.gateway import Gateway
from pay.models import Entry, Refund
from pay.utils import cents
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

## Packaging split between setup.py and pyproject.toml with no build-system table

```yaml
status: pending
slug: packaging-split-between-setup-py-and-pyproject-toml-with-no-buil
fingerprint: 190227da97266603
tier: B
priority: 2.1
family: migration
category: migration
debt_type: build
type_id: null
severity: 3
effort: S
diff: NEW
```

### Proof

pyproject.toml:1-5 has a [project] table (name, version, deps) but no [build-system] table anywhere in the file. Per PEP 517, absent [build-system], `python -m build` (release.yml:11) falls back to the legacy setuptools shim, which invokes setup.py:4 (`setup(name="pay-service")`) directly and does not read the [project] table at all. So pyproject.toml's version/deps are dead metadata despite setup.py's own docstring calling pyproject.toml authoritative — a real, silent split, not a stated multi-backend design or dated shim.

### Evidence

- `setup.py:1-4`

```
"""Legacy packaging shim; pyproject.toml is the source of truth."""
from setuptools import setup

setup(name="pay-service")
```

- `pyproject.toml:1-5`

```
[project]
name = "pay-service"
version = "0.2.0"
requires-python = ">=3.11"
dependencies = ["requests>=2.31"]
```

- `.github/workflows/release.yml:10-11`

```
- uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11
      - run: python -m build
```

## Coverage fail_under gate is configured but never invoked in CI

```yaml
status: pending
slug: coverage-fail-under-gate-is-configured-but-never-invoked-in-ci
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

pyproject.toml:7-8 sets `[tool.coverage.report] fail_under = 80`. requirements.txt:1 contains only `requests==2.32.3` — no pytest-cov/coverage package. ci.yml:11-12 runs `pip install -r requirements.txt` then `pytest -q` with no `--cov` flag. Coverage is therefore never measured or enforced; the threshold cannot block a merge. No integration/e2e suite was found that would make unit coverage measurement redundant.

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

## fingerprint() in utils.py has no callers

```yaml
status: pending
slug: fingerprint-in-utils-py-has-no-callers
fingerprint: 441a5776ddef0261
tier: A
priority: 2.016
family: dead-code
category: dead-code
debt_type: code
type_id: null
severity: 2
effort: S
diff: NEW
```

### Proof

fingerprint (utils.py:11-12) has zero references repo-wide: grep for 'fingerprint' across the whole repo returns only its own definition and unrelated .tech-debt tooling artifacts (metadata files, not code). No import of pay.utils.fingerprint exists in src or tests. No __all__/re-export, entry_points, or console_scripts anywhere, so it is not a public API. No dynamic dispatch patterns found. Confirmed dead code as described.

### Evidence

- `src/pay/utils.py:11-12`

```
def fingerprint(order_id: str) -> str:
    return hashlib.md5(order_id.encode("utf-8")).hexdigest()
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

## legacy_export.py module is unused (export_v1 has zero callers)

```yaml
status: pending
slug: legacy-export-py-module-is-unused-export-v1-has-zero-callers
fingerprint: b1d6db15aa9ce4d2
tier: A
priority: 2.0
family: dead-code
category: dead-code
debt_type: code
type_id: null
severity: 2
effort: S
diff: NEW
```

### Proof

export_v1 (legacy_export.py:8-14) is the module's only function. Repo-wide grep for 'legacy_export' and 'export_v1' finds no importer or caller in src/ or tests/, only the file itself and generated .tech-debt reports. It is not a script entry point (no __main__, no CLI wiring found) and not a test. Commented-out export_v0 and the '#TODO(#42): delete' marker corroborate it is abandoned legacy code, not a live plugin/entry surface.

### Evidence

- `src/pay/legacy_export.py:1-1`

```
"""Legacy CSV export kept for the v1 reporting job."""
```

- `src/pay/legacy_export.py:7-8`

```
# TODO(#42): delete once finance moves to the v2 report
def export_v1(refund_id: str, db: str = "refunds.db") -> list[tuple[str, int]]:
```

## Release process gaps

```yaml
status: pending
slug: release-process-gaps
fingerprint: 50201bbba28e3082
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
branch hotfix/ledger-rounding unmerged, last commit 2026-04-10 (152 days ago)
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

## Ledger test masks admitted flakiness with an unexplained sleep

```yaml
status: pending
slug: ledger-test-masks-admitted-flakiness-with-an-unexplained-sleep
fingerprint: 0fca9371a215c6b3
tier: B
priority: 1.4588
family: half-finished
category: half-finished
debt_type: code
type_id: null
severity: 2
effort: S
diff: NEW
```

### Proof

ledger.post (ledger.py:12-15) closes the file handle (context manager exit, which flushes) before returning, and balance (ledger.py:18-26) reads synchronously afterward on the same local tmp_path — there is no async I/O or separate process, so the sleep at test_ledger.py:14 has no evident mechanism to fix a real race. The comment's claim 'retried in the workflow' is unverifiable and appears false: .github/workflows/ci.yml:12 runs only 'pytest -q' with no retry step or plugin, and requirements.txt/pyproject.toml list no pytest-rerun/retry dependency. The workaround is undiagnosed and its safety-net claim is unsupported by the actual CI config.

### Evidence

- `tests/test_ledger.py:13-15`

```
    ledger.post(Entry(account="a", amount_cents=100), path)
    time.sleep(0.05)  # flaky on CI without this; retried in the workflow
    assert ledger.balance("a", path) == 100
```

## Legacy reporting job embedded in core payment package with own datastore

```yaml
status: pending
slug: legacy-reporting-job-embedded-in-core-payment-package-with-own-d
fingerprint: 784727ca3fd3a182
tier: B
priority: 1.4
family: architecture
category: architecture
debt_type: architecture
type_id: null
severity: 2
effort: S
diff: NEW
```

### Proof

legacy_export.py:4,9 opens a separate sqlite3 'refunds.db' inside src/pay, while docs/adr/0001-ledger.md:5-6 declares JSON-lines ledger.py as the single source of truth. Grep across the repo shows legacy_export/export_v1 referenced nowhere else in source or tests, confirming it is an orphaned, architecturally inconsistent module sitting in the core package. No cycle or re-export pattern is involved, so no trap applies.

### Evidence

- `src/pay/legacy_export.py:1-9`

```
"""Legacy CSV export kept for the v1 reporting job."""
from __future__ import annotations

import sqlite3
import subprocess

# TODO(#42): delete once finance moves to the v2 report
def export_v1(refund_id: str, db: str = "refunds.db") -> list[tuple[str, int]]:
    con = sqlite3.connect(db)
```

- `docs/adr/0001-ledger.md:1-6`

```
# ADR 0001: append-only ledger

Status: accepted, 2024-10-05.

We store ledger entries as JSON lines in `src/pay/ledger.py` and never rewrite
history; reversals are new entries.
```

## CHANGELOG missing entries for released 0.2.0 work

```yaml
status: pending
slug: changelog-missing-entries-for-released-0-2-0-work
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

pyproject.toml:3 declares version 0.2.0; CHANGELOG.md:3-5 only documents 0.1.0 (2024-10-05) with a single bullet. Git history (feat: refund audit trail, feat: migrate gateway to v2 API) shows real shipped work with no corresponding changelog entry. No generator produces this changelog and no ADR marks 0.2.0 as unreleased/planned, so the absence is genuine drift, not a planned-interface or generated-doc case.

### Evidence

- `CHANGELOG.md:1-5`

```
# Changelog

## 0.1.0 - 2024-10-05

- initial refund and ledger flow
```

- `pyproject.toml:2-3`

```
name = "pay-service"
version = "0.2.0"
```

## pyproject.toml floating requests range diverges from pinned requirements.txt

```yaml
status: pending
slug: pyproject-toml-floating-requests-range-diverges-from-pinned-requ
fingerprint: ecf0205d7d75e559
tier: B
priority: 1.4
family: dependency-debt
category: dependency-debt
debt_type: dependency
type_id: TD-02
severity: 2
effort: S
diff: NEW
```

### Proof

pyproject.toml:5 declares `requests>=2.31` (unbounded) while requirements.txt:1 pins `requests==2.32.3`. Dockerfile:4-5 and ci.yml:11 both install only from requirements.txt, so pyproject's dependencies field is unused there — but any editable install (`pip install -e .`) would resolve independently under the floating range, and no lockfile exists to reconcile the two. This is a live inconsistency, not a library-without-lockfile case (this is an application/service, per Dockerfile CMD).

### Evidence

- `pyproject.toml:5-5`

```
dependencies = ["requests>=2.31"]
```

- `requirements.txt:1-1`

```
requests==2.32.3
```

- `Dockerfile:4-5`

```
COPY requirements.txt .
RUN pip install -r requirements.txt
```

- `.github/workflows/ci.yml:11-11`

```
      - run: pip install -r requirements.txt
```

## Commented-out export_v0 function left in legacy_export.py

```yaml
status: pending
slug: commented-out-export-v0-function-left-in-legacy-export-py
fingerprint: 08dd9ba688d79fda
tier: A
priority: 1.0
family: dead-code
category: dead-code
debt_type: code
type_id: null
severity: 1
effort: S
diff: NEW
```

### Proof

legacy_export.py:17-19 contains a commented-out export_v0 stub with no explanation, no ticket reference, and no removal date near it (the only ticket, TODO(#42) at line 7, refers to export_v1's removal, not export_v0). git history is available via version control so this dead snippet adds no value kept in-file. Low severity given effort S and zero functional risk.

### Evidence

- `src/pay/legacy_export.py:17-19`

```
# def export_v0(refund_id):
#     rows = fetch(refund_id)
#     return rows
```

## SEED_A / SEED_B fixture data never referenced by any test

```yaml
status: pending
slug: seed-a-seed-b-fixture-data-never-referenced-by-any-test
fingerprint: ee0e5f40d3e1aeab
tier: A
priority: 1.0
family: dead-code
category: dead-code
debt_type: code
type_id: null
severity: 1
effort: S
diff: NEW
```

### Proof

SEED_A/SEED_B (seed.py:4-5) are unreferenced: tests/conftest.py:1-11 defines only a 'refund' fixture with no import from tests.fixtures.seed; tests/test_refund.py:1-21 and tests/test_ledger.py:1-19 import only from pay, not tests.fixtures.seed. Repo-wide grep for SEED_A/SEED_B finds no other hits. The file's own docstring ('duplicated on purpose so each test owns its copy', line 1) is contradicted — neither constant is owned by any test. No parametrize/fixture-loader mechanism references the file by name.

### Evidence

- `tests/fixtures/seed.py:4-5`

```
SEED_A = [{"account": "a", "amount": 100}, {"account": "b", "amount": 200}]
SEED_B = [{"account": "a", "amount": 100}, {"account": "b", "amount": 200}]
```

# Below the cut: tier C and unverified

| slug | family | file | reason |
| --- | --- | --- | --- |
| f-string-sql-interpolation-suppressed-with-unexplained-nosec | security | src/pay/legacy_export.py | the verifier downgraded it |
| runtime-dependency-declared-in-both-requirements-txt-and-pyproje | migration | requirements.txt | the verifier downgraded it |

# Considered and rejected

- **Release version bump/changelog drifted from last tag** - `pyproject.toml` - .git/refs/tags shows only v0.1.0 exists — no v0.2.0 tag has ever been pushed, so release.yml (triggers only on tag push, .github/workflows/release.yml:2-4) has never published a build inconsistent with CHANGELOG.md:3. pyproject.toml:3 at 0.2.0 while the last release/tag/changelog are 0.1.0 is the normal in-development state between releases, with the human expected to update changelog/version before cutting the next tag — no evidence of an actual mismatched release.

# Looks bad but is fine

- `src/pay/gateway.py:20` - longest_indented_run=8 flagged by the inventory signal comes from a single multi-line requests.post() call with keyword arguments spread across lines, not from nested conditionals or branching; there is no control flow to simplify.
- `src/pay/refund.py:31` - Two sequential try/except blocks (max_indent=2) but no nesting or chained branching; each function in this file is under 20 lines with a single level of conditional logic.
- `src/pay/ledger.py:18` - balance() has a single for-loop with one if-check inside (max_indent=3), which is a straightforward accumulation, not a hard-to-change unit.
- `src/pay/refund.py:24` - issue() calls into both ledger.post and gateway.refund, which could look like a hub reaching into two subsystems, but it only calls their public functions (ledger.post, Gateway.refund) with data it already owns — no field-level reach-in, and the module has a single cohesive responsibility (refund workflow). Not a god class; the whole repo is 243 LOC and every pay/ file is under 55 lines with one clear purpose.
- `src/pay/refund.py:30` - Entry(account=refund.order_id, amount_cents=-refund.amount_cents, reason=refund.reason_code) negates amount_cents like ledger.py:30's reverse(), but the two build entries for different purposes (issuing a refund debit vs. reversing an arbitrary entry) and change for different reasons; not a maintenance-coupled clone.
- `src/pay/models.py:8` - Entry and Refund dataclasses share a similar three-field shape (account/order_id, amount_cents, reason/reason_code), but they model different concepts (ledger line vs. refund request) with independent reasons to change.
- `tests/test_refund.py:19` - test_issue_calls_gateway is skipped with a reason and raises NotImplementedError; it is a runner-discovered test placeholder, not dead code.
- `src/pay/refund.py:51` - audit_trail looked like an unused helper but is called directly by tests/test_refund.py:16, so it has a real caller.
- `src/pay/refund.py:36` - except OSError as exc: logs via log.exception (cause preserved) and re-raises as RuntimeError from exc, keeping the chain. Boundary catch that reports and stops, not masking.
- `src/pay/models.py:1` - Trivial dataclasses (Entry, Refund) with no logic; no mapped test exists but this is glue/data definition, not behaviour, matching the glue-code trap.
- `src/pay/legacy_export.py:7` - TODO(#42) references a ticket and a concrete deprecation condition (finance moving to v2 report); this is a ticketed, deliberate deferral rather than half-finished work.
- `src/pay/gateway.py:1` - The migration_commits=1 lead corresponds to the v1-to-v2 gateway API migration; only the Gateway class and v2 API_BASE remain, no old gateway code path or v1 caller exists anywhere in the repo, so this migration is complete.
- `src/pay/legacy_export.py:7` - export_v1 is unused (zero callers) rather than an old idiom still being called alongside a replacement, so it does not fit the migration-debt pattern of two coexisting call paths; it also carries a ticketed TODO(#42) for removal.
- `setup.py:1` - Thin setuptools shim deferring to pyproject.toml; not a second competing manifest, just packaging glue.
- `.python-version:0` - No runtime-version file exists; pyproject.toml (>=3.11), Dockerfile (python:3.11-slim), and ci.yml (3.11) all agree, so there is no runtime/manifest disagreement to report.
- `docs/adr/0001-ledger.md:1` - Flagged as stale (625 days) by the deterministic signal, but its content (JSON-lines append-only storage in src/pay/ledger.py, reversals as new entries) still matches the current ledger.py implementation exactly; no contradiction found.
- `docs/übersicht.md:1` - Two-line generic notes file with no specific technical claims to verify against code; flagged stale by the signal but contains nothing that can be shown to contradict current code.
- `src/pay/refund.py:6` - refund.py imports ledger, gateway, models and utils directly, but the import graph across all src/pay modules is a clean acyclic chain (refund -> ledger/gateway/models/utils; ledger -> models) with no cycle and no re-export tricks.
- `src/pay/ledger.py:1` - ledger.py and refund.py share the highest churn/hotspot scores and co-change, but refund.py has a declared direct import of ledger.py, so the coupling is an explicit, expected dependency rather than a hidden architecture issue.
- `src/pay/gateway.py:12` - CORS_HEADERS with Access-Control-Allow-Origin: * is merged into the headers of an outbound client POST request (requests.post), not returned as a response header by a server this code controls. As a request header it has no CORS-enabling effect, so it does not function as a server-side wildcard-CORS misconfiguration in this context.
- `src/pay/utils.py:11` - fingerprint() uses hashlib.md5 but is named/used as an order_id fingerprint/dedup key rather than a password or security-sensitive hash, and per repo-wide grep it currently has zero callers anywhere in the codebase.
- `tests/test_refund.py:19` - test_issue_calls_gateway is assert-free but pytest.mark.skip'd with an explicit reason ('gateway stub not written yet'); it does not run and is honestly labeled incomplete rather than disguised as coverage.
- `tests/test_refund.py:15` - audit_trail assertion against a literal list directly reflects the fixture's own values (order_id/amount/reason from the refund fixture), not an unexplained magic-number assertion.
- `Dockerfile:7` - CMD python -m pay.refund is the container's single entrypoint; no dev-only compose file or floating-tag override exists in this repo, so no dev-only-path-in-production pattern applies.

# Open questions for the maintainer

- `src/pay/ledger.py:29` - reverse() has no production caller and is exercised only by tests/test_ledger.py::test_reverse_smoke, which asserts nothing. Is reverse() intended for future use, or is the smoke test the only reason it survives?
- `setup.py:1` - Is a build-system table intentionally omitted from pyproject.toml (relying on setuptools legacy default), or was this dropped when the packaging migration to pyproject.toml was started?
- `requirements.txt:1` - Is requirements.txt meant to be replaced by pyproject.toml's dependencies list, or kept permanently for pinned CI/Docker installs alongside the looser pyproject.toml range?
- `src/pay/legacy_export.py:1` - README.md states the v1 exporter (src/pay/exporter.py) was removed in 0.1.0, yet src/pay/legacy_export.py still exists in the pay package with a distinct sqlite datastore — is this file intended to stay in the payment component, or should it be relocated/retired as a separate reporting service?
- `src/pay/legacy_export.py:7` - TODO(#42) marks this module for deletion once finance moves to v2; is the suppressed SQL/shell pattern scheduled to be removed with it, or does it need independent remediation in the meantime?
- `tests/test_ledger.py:14` - Whether the sleep(0.05) masks a real race in ledger.post/balance under concurrent writers, or is a leftover workaround for an unrelated CI issue.

# Not assessed

- Families not run: none
- Tools: a claim that needs a tool which did not run -- currency, end-of-life, vulnerability -- is not assessed; the frontmatter's tools_absent names every such tool
- Runtime-only: coverage numbers, flake confirmation, model staleness, rollout state, deploy frequency
- By design: magic literals, convention violations, and class-level metrics that need a parser
