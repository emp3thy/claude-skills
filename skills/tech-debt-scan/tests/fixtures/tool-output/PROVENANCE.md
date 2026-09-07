# Where each payload came from

Captured from the installed tool against the corpus on 2026-09-06:

| File | Tool | Version | Command |
|---|---|---|---|
| `ruff.json` | ruff | installed | `ruff check --isolated --output-format json` |
| `vulture.txt` | vulture | 2.16 | `vulture <root>` (exit 3) |
| `lizard.csv` | lizard | 1.24.0 | `lizard --csv <root>` |
| `madge.json` | madge | 8.0.0 | `madge --extensions ts --circular --json <dir>` |
| `jscpd.json` | jscpd | 5.1.2 | `jscpd --reporters json --min-tokens 20 --output <dir>` |
| `knip.json` | knip | installed | `knip --reporter json` (exit 1) |

Written from the tool's documented schema, never executed — these four are
not installable on the development machine:

| File | Tool | Schema source |
|---|---|---|
| `osv-scanner.json` | osv-scanner | documented `results[].packages[].vulnerabilities[]` shape, v1 JSON output |
| `gitleaks.json` | gitleaks | documented report array with `RuleID`, `File`, `StartLine`, `Entropy` |
| `hadolint.json` | hadolint | documented array of `{file, line, column, level, code, message}` |
| `actionlint.json` | actionlint | documented `-format '{{json .}}'` array of `{message, filepath, line, column, kind}` |

A normaliser in the second table has never seen its tool's real output. When
one is corrected against a real run, update this row with the version and
command that produced the correction, so the next reader knows which claims
have been tested and which have not.
