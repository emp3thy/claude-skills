You are writing the remediation notes for the top tech-debt findings found in the repository at `/abs/path/to/repo`.
You have read-only access: read and search files if you need more context; change nothing.

## 1. Refund failure swallowed by a bare except
fingerprint: 0123456789abcdef
family: error-masking  severity: 4  effort: M

The catch at lines 120 to 123 returns on any failure and logs nothing.

- `src/pay/refund.py:120-123`

```
    except Exception:
        pass
```

Reply with one JSON array, one object per finding, exactly these keys:

[
  {
    "fingerprint": "<as given>",
    "remediation": "<=120 words on how to pay this debt down, no code>",
    "acceptance_criteria": ["<one checkable statement>", "..."]
  }
]

Write for the engineer who will do the work: what to change and in what order, not why
the debt matters. Two to five acceptance criteria, each checkable by reading a diff or
running a test. Do not restate the finding, do not propose a schedule, do not include a
fix in code.
