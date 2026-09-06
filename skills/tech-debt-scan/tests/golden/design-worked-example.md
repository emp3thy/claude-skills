---
schema_version: 2
scan_date: 2026-09-06
root: /abs/path/to/repo
total_files: 100
total_loc: 12000
languages:
- python
preset: balanced
families_run:
- error-masking
- security
families_skipped:
- family: duplication
  reason: no leads
tools_run: []
tools_absent: []
git_available: true
counts:
  candidates: 3
  quote_failed: 1
  verified: 2
  tier_a: 1
  tier_b: 1
  tier_c: 1
  unverified: 1
  rejected: 0
  suppressed: 0
---

# Tech-debt scan - 2026-09-06

Scanned `/abs/path/to/repo` - 100 files, 12000 LOC across: python.

Review each finding below. To act on one, change its `status:` from `pending` to
`approved`, `rejected`, or `accepted` (add a `reason:` and an optional `until:` ISO
date), then run `/tech-debt-promote`.

Top hotspots: `src/pay/refund.py` (80.0), `src/pay/gateway.py` (45.0).

Top coupled pairs: `src/pay/refund.py` <-> `src/pay/gateway.py` (shared 4, ratio 0.8).

# Top 1

## Refund failure swallowed by a bare except

```yaml
status: pending
slug: refund-failure-swallowed-by-a-bare-except
fingerprint: 0123456789abcdef
tier: A
priority: 6.3
family: error-masking
category: error-masking
debt_type: defect
type_id: TD-13
severity: 4
effort: M
diff: NEW
```

### Proof

The catch at lines 120 to 123 returns on any failure and logs nothing.

### Evidence

- `src/pay/refund.py:120-123`

```
    except Exception:
        pass
```

### Signals

- hotspot score 80.0, churn 4, coupling pairs 1, fan-in 2 (approximate)
- confirmed by: hotspot, pattern:swallowed-catch, scout:error-masking

### Remediation

remediation note not available

### Acceptance criteria

remediation note not available

# Below the cut

## Hard-coded credential in the gateway client

```yaml
status: pending
slug: hard-coded-credential-in-the-gateway-client
fingerprint: fedcba9876543210
tier: B
priority: 3.5
family: security
category: security
debt_type: security
type_id: TD-03
severity: 5
effort: S
diff: NEW
```

### Proof

A credential-shaped literal sits in source, not in configuration.

### Evidence

- `src/pay/gateway.py:11-11`

```
token = "sk_l***"
```

# Below the cut: tier C and unverified

| slug | family | file | reason |
| --- | --- | --- | --- |
| unused-helper-in-the-ledger-module | dead-code | src/pay/ledger.py | unverified |

# Considered and rejected

_None._

# Looks bad but is fine

- `src/pay/gateway.py:19` - One multi-line call, not nested branching.

# Open questions for the maintainer

- `src/pay/refund.py:51` - Is audit_trail() wired into a production caller?
- `src/pay/ledger.py:12` - quote not found: Ledger rounding drifts on partial refunds

# Not assessed

- Families not run: duplication (no leads)
- Tools: the tool probe lands in phase 4, so currency, end-of-life and vulnerability claims are not assessed
- Runtime-only: coverage numbers, flake confirmation, model staleness, rollout state, deploy frequency
- By design: magic literals, convention violations, and class-level metrics that need a parser
