---
id: chore-refund-failure-swallowed-2026-09-06
type: feature
status: inbox
severity: high
attempts: 0
created_at: 2026-09-06T00:00:00+00:00
updated_at: 2026-09-06T00:00:00+00:00
depends_on: []
target_repo:
source_design: d.md
category: error-masking
fingerprint: 0123456789abcdef
tier: A
type_id: TD-13
family: error-masking
debt_type: defect
effort: M
---

# Refund failure swallowed by a bare except

### Proof

p

### Evidence

- `src/pay/refund.py:120-123`

```
    except Exception:
        pass
```

### Remediation

Re-raise after logging.

### Acceptance criteria

- [ ] The failure path re-raises
- [ ] A regression test covers it
