"""Build the synthesis prompt and validate the synthesis LLM's output.

Stage 3 of /tech-debt-scan. The seven scouts each emit a JSON array of raw
ScoutFindings (see categories.py for the shared shape). Those arrays are
concatenated into one raw-findings list and handed here.

`build_prompt` renders a single prompt that asks the synthesis model to pick
the top 5 findings by RICE/WSJF and re-emit them in a stricter shape (adding
`slug`, `reasoning`, `confidence`, `change_size`, `change_risk`, `disposition`,
`why_now`, `scope_boundary`, and `acceptance_criteria`).
`validate_synthesis_output` parses the model's reply and enforces that shape,
raising SynthesisError with the offending field on any deviation.

Direct-path invocable (no package imports): `python build_synthesis_prompt.py`.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Final

from categories import CATEGORIES
from validation import (
    ValidationError,
    validate_slug,
    validate_change_size,
    validate_change_risk,
    validate_disposition,
)

# Cap the number of raw findings sent to synthesis so the prompt stays well
# under the model's input window. Sort by severity DESC and keep the top N;
# the dropped count is surfaced (stderr) by the CLI so SKILL.md can log it.
MAX_FINDINGS: Final[int] = 30

TOP5_COUNT: Final[int] = 5

_REQUIRED_ITEM_FIELDS: Final[tuple[str, ...]] = (
    "slug",
    "title",
    "severity",
    "category",
    "reasoning",
    "evidence",
    "suggested_fix",
    "confidence",
    "change_size",
    "change_risk",
    "disposition",
    "why_now",
    "scope_boundary",
    "acceptance_criteria",
)

_OUTPUT_SCHEMA: Final[str] = """
Emit a single JSON object with exactly one key, "top5", whose value is an array
of exactly 5 findings. Each finding has exactly these keys:

  {
    "slug": "kebab-case-id (lowercase letter start, [a-z0-9-], <=64 chars)",
    "title": "<=80 chars, one-line summary",
    "severity": 1-5 integer (5 = most damaging),
    "category": "one of the scout category names",
    "reasoning": "why this made the top 5",
    "evidence": [{"file": "relative/path", "line": 123, "note": "what is wrong"}],
    "suggested_fix": "<=500 chars describing the remediation",
    "confidence": 1-5 integer (5 = strongest evidence; penalise speculation),
    "change_size": "S | M | L | XL (scope/complexity of the fix diff, NOT time)",
    "change_risk": "low | med | high (chance the fix itself breaks behaviour)",
    "disposition": "full-repayment | debt-conversion | interest-only",
    "why_now": "the cost-of-delay signal (e.g. high-churn hotspot, blocks feature)",
    "scope_boundary": "what is explicitly OUT of this fix",
    "acceptance_criteria": "a verifiable done-signal for an autonomous coder"
  }

Rank by RICE/WSJF intent: Impact (severity) x Confidence, divided by change_size
(prefer smaller, higher-confidence, higher-impact items). change_risk is
informational only and does not affect ranking. Return valid JSON only; no prose
before or after the object.
"""


class SynthesisError(Exception):
    """Raised when the synthesis output fails the strict schema."""


def _finding_churn(finding: dict[str, Any], churn_by_file: dict[str, int]) -> int:
    return max(
        (churn_by_file.get(ev.get("file", ""), 0) for ev in finding.get("evidence", [])),
        default=0,
    )


def build_prompt(
    raw_findings: list[dict[str, Any]],
    churn_by_file: dict[str, int] | None = None,
) -> str:
    """Render the top-5 synthesis prompt from the raw scout findings.

    When ``churn_by_file`` is provided, findings are ranked by the git-hotspot
    key ``severity * log1p(churn)`` with severity as a tiebreak; otherwise by
    severity alone (git-optional fallback). Capped at MAX_FINDINGS.
    """
    if churn_by_file:
        ranked = sorted(
            raw_findings,
            key=lambda f: (
                f.get("severity", 0) * math.log1p(_finding_churn(f, churn_by_file)),
                f.get("severity", 0),
            ),
            reverse=True,
        )
    else:
        ranked = sorted(
            raw_findings,
            key=lambda f: f.get("severity", 0),
            reverse=True,
        )

    truncated_from = 0
    if len(ranked) > MAX_FINDINGS:
        truncated_from = len(ranked)
        ranked = ranked[:MAX_FINDINGS]
        print(
            f"warning: truncated {truncated_from} raw findings to top {MAX_FINDINGS} "
            "by hotspot rank before synthesis",
            file=sys.stderr,
        )

    findings_json = json.dumps(ranked, indent=2)
    categories_line = ", ".join(CATEGORIES)
    return (
        "You are synthesising the raw tech-debt findings below into the five most "
        "valuable items to fix. Each raw finding came from a read-only scout.\n\n"
        "Pick exactly 5 by RICE/WSJF intent: Impact (severity) x Confidence divided "
        "by change_size, favouring high-churn hotspots. Merge near-duplicate "
        "findings into one. Do not invent findings.\n\n"
        f"Valid category names: {categories_line}.\n\n"
        "Raw findings:\n"
        f"{findings_json}\n"
        f"{_OUTPUT_SCHEMA}"
    )


def _require_field(item: dict[str, Any], field: str, index: int) -> Any:
    if field not in item:
        raise SynthesisError(f"finding {index}: missing field {field!r}")
    return item[field]


def validate_synthesis_output(text: str) -> dict[str, Any]:
    """Parse + strictly validate the synthesis model's JSON reply.

    Raises SynthesisError on: not-JSON, missing/!= 5 ``top5`` items, any item
    missing a required field, invalid slug, bad severity, unknown category,
    bad confidence, bad change_size/change_risk/disposition, or empty prose.
    """
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise SynthesisError(f"synthesis response is not valid JSON: {exc}") from exc

    if not isinstance(data, dict) or "top5" not in data:
        raise SynthesisError("synthesis response missing 'top5' key")

    items = data["top5"]
    if not isinstance(items, list):
        raise SynthesisError("'top5' must be a JSON array")
    if len(items) != TOP5_COUNT:
        raise SynthesisError(f"expected 5 findings, got {len(items)}")

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise SynthesisError(f"finding {index}: not a JSON object")
        for field in _REQUIRED_ITEM_FIELDS:
            _require_field(item, field, index)

        slug = item["slug"]
        try:
            validate_slug(slug)
        except ValidationError as exc:
            raise SynthesisError(f"finding {index}: {exc}") from exc

        severity = item["severity"]
        is_int = isinstance(severity, int) and not isinstance(severity, bool)
        if not is_int or severity not in range(1, 6):
            raise SynthesisError(
                f"finding {index}: severity must be an integer 1-5, got {severity!r}"
            )

        category = item["category"]
        if category not in CATEGORIES:
            raise SynthesisError(
                f"finding {index}: unknown category {category!r}; "
                f"expected one of {list(CATEGORIES)}"
            )

        confidence = item["confidence"]
        conf_is_int = isinstance(confidence, int) and not isinstance(confidence, bool)
        if not conf_is_int or confidence not in range(1, 6):
            raise SynthesisError(
                f"finding {index}: confidence must be an integer 1-5, got {confidence!r}"
            )

        for field_name, validator in (
            ("change_size", validate_change_size),
            ("change_risk", validate_change_risk),
            ("disposition", validate_disposition),
        ):
            try:
                validator(str(item[field_name]))
            except ValidationError as exc:
                raise SynthesisError(f"finding {index}: {exc}") from exc

        for prose in ("why_now", "scope_boundary", "acceptance_criteria"):
            value = item[prose]
            if not isinstance(value, str) or not value.strip():
                raise SynthesisError(
                    f"finding {index}: {prose} must be a non-empty string"
                )

    return data


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render the top-5 synthesis prompt from raw scout findings"
    )
    parser.add_argument("raw_findings", help="path to raw-findings.json")
    parser.add_argument(
        "--out",
        default=".tech-debt/synthesis-prompt.txt",
        help="output path for the rendered prompt",
    )
    parser.add_argument(
        "--inventory",
        default=None,
        help="path to inventory.json (enables git-hotspot ranking)",
    )
    args = parser.parse_args(argv)

    try:
        raw = json.loads(Path(args.raw_findings).read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"error: could not read {args.raw_findings}: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"error: {args.raw_findings} is not valid JSON: {exc}", file=sys.stderr)
        return 2

    if not isinstance(raw, list):
        print("error: raw-findings.json must be a JSON array", file=sys.stderr)
        return 2

    churn_by_file: dict[str, int] | None = None
    if args.inventory:
        try:
            inv = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
            churn_by_file = {
                e["path"]: e["git_churn"]
                for e in inv.get("files", [])
                if e.get("git_churn") is not None
            }
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            print(f"warning: could not load churn from {args.inventory}: {exc}", file=sys.stderr)
            churn_by_file = None

    prompt = build_prompt(raw, churn_by_file=churn_by_file)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(prompt.encode("utf-8"))
    print(f"wrote {out_path} ({len(raw)} raw findings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
