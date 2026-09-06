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

# Below the cut: tier C and unverified

# Considered and rejected

# Looks bad but is fine

# Open questions for the maintainer

# Not assessed
