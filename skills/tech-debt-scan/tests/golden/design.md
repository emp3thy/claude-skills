---
scan_date: 2026-05-31
root: /abs/path/to/repo
total_files: 100
total_loc: 12000
languages:
- python
---

# Tech-debt scan - 2026-05-31

Scanned `/abs/path/to/repo` - 100 files, 12000 LOC across: python.

Review each finding below. To act on one, change its `status:` from `pending`
to `approved` (or `rejected`), then run `/tech-debt-promote`.

## Split the 1240-LOC auth/service god module

```yaml
status: pending
slug: finding-0
severity: 5
category: god-modules
confidence: 5
change_size: L
change_risk: med
disposition: full-repayment
```

### Reasoning

Highest blast radius: login, tokens, and email share one module, so every auth change risks the others. Splitting is mechanical and well bounded.

### Evidence

- `src/auth/service.py:1` - single module owns login, tokens, and email

### Suggested fix

split into auth.session, auth.tokens, auth.notifications

### Why now

highest-churn module; every auth change pays the tax

### Scope boundary

split only; no behaviour change, no new features

### Acceptance criteria

module split into three units, all existing tests pass unchanged

## Cover the untested payment refund path

```yaml
status: pending
slug: finding-1
severity: 5
category: test-gaps
confidence: 4
change_size: M
change_risk: low
disposition: full-repayment
```

### Reasoning

Refunds move money and have zero coverage; a regression is high-impact and the fix is purely additive tests.

### Evidence

- `src/payments/refund.py:1` - no test exercises partial refunds

### Suggested fix

add unit + integration tests for refund flows

### Why now

next sprint adds new refund types; untested baseline blocks safe extension

### Scope boundary

tests only; no refund logic changes

### Acceptance criteria

partial and full refund paths covered by unit and integration tests, CI green

## Extract the retry loop duplicated across six clients

```yaml
status: pending
slug: finding-2
severity: 4
category: duplication
confidence: 4
change_size: M
change_risk: low
disposition: debt-conversion
```

### Reasoning

Six verbatim copies of backoff logic drift independently; one shared helper removes a recurring source of bugs.

### Evidence

- `src/clients/http.ts:88` - exponential backoff duplicated verbatim

### Suggested fix

extract a shared withRetry helper

### Why now

two clients already diverged; consolidating now prevents a third divergence in the upcoming API migration

### Scope boundary

retry/backoff logic only; timeout values and error handling unchanged

### Acceptance criteria

single withRetry helper used by all six clients, existing retry behaviour preserved, tests pass

## Delete the never-called legacy_export path

```yaml
status: pending
slug: finding-3
severity: 3
category: dead-code
confidence: 5
change_size: S
change_risk: low
disposition: full-repayment
```

### Reasoning

legacy_export is superseded and unreferenced; removing it shrinks the surface with no behavioural risk.

### Evidence

- `src/export/legacy.py:1` - no references; superseded by export.v2

### Suggested fix

delete legacy_export and its tests

### Why now

dead code is indexed by tooling and misleads new contributors during onboarding

### Scope boundary

legacy_export module and its dedicated tests only; export.v2 untouched

### Acceptance criteria

legacy_export deleted, no references remain, full test suite passes

## Fix README install steps pointing at a removed script

```yaml
status: pending
slug: finding-4
severity: 2
category: doc-drift
confidence: 4
change_size: S
change_risk: low
disposition: interest-only
```

### Reasoning

New contributors follow install steps that reference a deleted setup.sh; a quick doc fix unblocks onboarding.

### Evidence

- `README.md:22` - points at setup.sh deleted last release

### Suggested fix

update install section to current bootstrap

### Why now

new hire onboarding scheduled next week; stale steps will waste setup time

### Scope boundary

README install section only; no code changes

### Acceptance criteria

README install steps reference current bootstrap script and a fresh clone succeeds end-to-end
