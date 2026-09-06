"""Build the synthesis prompt and validate the synthesis LLM's output.

Stage 3 of /tech-debt-scan. The scouts each emit a JSON array of raw
ScoutFindings (see categories.py for the shared shape). Those arrays are
concatenated into one raw-findings list and handed here.

`build_prompt` renders a single prompt that asks the synthesis model to pick
the top N findings (default 5) and re-emit them in a stricter shape (adding
`slug` and `reasoning`). Ranking is grounded in three axes:

  - impact:       the scout's severity (blast radius if left unfixed)
  - interest:     hotspot location — debt in high-churn x high-complexity
                  files is re-paid on every change, so it compounds fastest
  - tractability: the scout's S/M/L effort estimate

Before rendering, findings are pre-ranked deterministically by a composite
``priority score`` (severity x effort weight x confidence weight x hotspot
boost) so that when the raw list is truncated to MAX_FINDINGS, the cut keeps
the highest-value candidates rather than merely the highest severities.

`validate_synthesis_output` parses the model's reply and enforces the strict
shape, raising SynthesisError with the offending field on any deviation. The
classification fields (debt_type / effort / confidence) are validated when
present; older payloads without them still pass.

Direct-path invocable (no package imports): `python build_synthesis_prompt.py`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Final

from categories import CATEGORIES
from validation import (
    ValidationError,
    validate_debt_type,
    validate_effort,
    validate_slug,
)

# Cap the number of raw findings sent to synthesis so the prompt stays well
# under the model's input window. Sort by priority score DESC and keep the top
# N; the dropped count is surfaced (stderr) by the CLI so SKILL.md can log it.
MAX_FINDINGS: Final[int] = 30

TOP5_COUNT: Final[int] = 5

# Tractability: small fixes deliver their value sooner, so they outrank an
# equally-severe finding that needs its own project. Unknown effort is scored
# as M, not punished.
EFFORT_WEIGHT: Final[dict[str, float]] = {"S": 1.0, "M": 0.7, "L": 0.45}
_DEFAULT_EFFORT_WEIGHT: Final[float] = 0.7

# Findings the scout itself is unsure about should not crowd out solid ones.
CONFIDENCE_WEIGHT: Final[dict[str, float]] = {"high": 1.0, "medium": 0.8, "low": 0.55}
_DEFAULT_CONFIDENCE_WEIGHT: Final[float] = 0.8

# Debt evidenced inside a hotspot file accrues interest on every change.
HOTSPOT_BOOST: Final[float] = 1.5

_REQUIRED_ITEM_FIELDS: Final[tuple[str, ...]] = (
    "slug",
    "title",
    "severity",
    "category",
    "reasoning",
    "evidence",
    "suggested_fix",
)

# Validated when present (strict values), tolerated when absent. confidence
# is no longer validated: validate_confidence was removed from validation.py.
_OPTIONAL_VALIDATORS: Final[dict[str, Any]] = {
    "debt_type": validate_debt_type,
    "effort": validate_effort,
}


class SynthesisError(Exception):
    """Raised when the synthesis output fails the strict schema."""


def _output_schema(top_n: int) -> str:
    return f"""
Emit a single JSON object with exactly one key, "top5", whose value is an array
of exactly {top_n} findings. (The key is named "top5" for historical reasons
regardless of the count.) Each finding has exactly these keys:

  {{
    "slug": "kebab-case-id (lowercase letter start, [a-z0-9-], <=64 chars)",
    "title": "<=80 chars, one-line summary",
    "severity": 1-5 integer (5 = most damaging),
    "category": "one of the scout category names",
    "debt_type": "one of: code, design, architecture, test, documentation,
                  dependency, build, requirement",
    "effort": "S" | "M" | "L",
    "confidence": "low" | "medium" | "high",
    "reasoning": "why this made the cut (impact x interest x tractability)",
    "evidence": [{{"file": "relative/path", "line": 123, "note": "what is wrong"}}],
    "suggested_fix": "<=500 chars describing the remediation"
  }}

Return valid JSON only; no prose before or after the object.
"""


def _hotspot_paths(inventory: dict[str, Any] | None) -> set[str]:
    if not inventory:
        return set()
    hotspots = inventory.get("hotspots") or []
    return {
        str(h["path"]) for h in hotspots if isinstance(h, dict) and h.get("path")
    }


def priority_score(finding: dict[str, Any], hotspot_paths: set[str]) -> float:
    """Deterministic composite pre-rank: severity x effort x confidence x hotspot."""
    severity = finding.get("severity", 0)
    if not isinstance(severity, (int, float)) or isinstance(severity, bool):
        severity = 0
    effort_w = EFFORT_WEIGHT.get(str(finding.get("effort")), _DEFAULT_EFFORT_WEIGHT)
    conf_w = CONFIDENCE_WEIGHT.get(
        str(finding.get("confidence")), _DEFAULT_CONFIDENCE_WEIGHT
    )
    boost = 1.0
    for item in finding.get("evidence") or []:
        if isinstance(item, dict) and item.get("file") in hotspot_paths:
            boost = HOTSPOT_BOOST
            break
    return float(severity) * effort_w * conf_w * boost


def _render_hotspot_block(inventory: dict[str, Any] | None) -> str:
    if not inventory:
        return ""
    hotspots = inventory.get("hotspots") or []
    if not hotspots:
        return ""
    lines = [
        "",
        "Repository hotspots (churn x complexity, highest interest first). Debt",
        "evidenced in these files is re-paid on every change — weight it up:",
        "",
    ]
    for h in hotspots[:10]:
        lines.append(
            f"- {h.get('path')} (churn {h.get('churn')}, "
            f"complexity {h.get('complexity')}, score {h.get('score')})"
        )
    lines.append("")
    return "\n".join(lines)


def build_prompt(
    raw_findings: list[dict[str, Any]],
    top_n: int = TOP5_COUNT,
    inventory: dict[str, Any] | None = None,
) -> str:
    """Render the top-N synthesis prompt from the raw scout findings.

    Findings are pre-ranked by the composite priority score (descending) and
    capped at MAX_FINDINGS so the rendered prompt stays bounded. When findings
    are dropped, a warning is written to stderr.
    """
    hotspots = _hotspot_paths(inventory)
    ranked = sorted(
        raw_findings,
        key=lambda f: priority_score(f, hotspots),
        reverse=True,
    )
    truncated_from = 0
    if len(ranked) > MAX_FINDINGS:
        truncated_from = len(ranked)
        ranked = ranked[:MAX_FINDINGS]
        print(
            f"warning: truncated {truncated_from} raw findings to top {MAX_FINDINGS} "
            "by priority score before synthesis",
            file=sys.stderr,
        )

    findings_json = json.dumps(ranked, indent=2)
    categories_line = ", ".join(CATEGORIES)
    return (
        f"You are synthesising the raw tech-debt findings below into the {top_n} most "
        "valuable items to fix. Each raw finding came from a read-only scout.\n\n"
        f"Pick exactly {top_n} by ranking on three axes:\n"
        "- impact: how damaging the debt is if left (the severity rubric).\n"
        "- interest: how often the team re-pays it — debt in hotspot or "
        "high-churn files compounds on every change and outranks equally-bad "
        "debt in cold code.\n"
        "- tractability: prefer fixes deliverable soon (effort S/M) over ones "
        "needing their own project (L), unless the L item's impact dwarfs the rest.\n\n"
        "Also apply:\n"
        "- Merge near-duplicate findings into one (keep the union of evidence).\n"
        "- Findings about the same root cause across categories are duplicates.\n"
        "- Drop low-confidence findings unless severity is 5.\n"
        "- When scores are close, prefer a spread of categories over five "
        "variations of one problem.\n"
        "- Do not invent findings.\n"
        f"{_render_hotspot_block(inventory)}\n"
        f"Valid category names: {categories_line}.\n\n"
        "Raw findings:\n"
        f"{findings_json}\n"
        f"{_output_schema(top_n)}"
    )


def _require_field(item: dict[str, Any], field: str, index: int) -> Any:
    if field not in item:
        raise SynthesisError(f"finding {index}: missing field {field!r}")
    return item[field]


def validate_synthesis_output(
    text: str, expected_count: int = TOP5_COUNT
) -> dict[str, Any]:
    """Parse + strictly validate the synthesis model's JSON reply.

    Raises SynthesisError on: not-JSON, missing/!= ``expected_count`` ``top5``
    items, any item missing a required field, invalid slug, bad severity,
    unknown category, or an invalid debt_type / effort / confidence (these
    three are validated only when present).
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
    if len(items) != expected_count:
        raise SynthesisError(f"expected {expected_count} findings, got {len(items)}")

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

        for field, validator in _OPTIONAL_VALIDATORS.items():
            if field in item and item[field] is not None:
                try:
                    validator(str(item[field]))
                except ValidationError as exc:
                    raise SynthesisError(f"finding {index}: {exc}") from exc

    return data


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render the top-N synthesis prompt from raw scout findings"
    )
    parser.add_argument("raw_findings", help="path to raw-findings.json")
    parser.add_argument(
        "--out",
        default=".tech-debt/synthesis-prompt.txt",
        help="output path for the rendered prompt",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=TOP5_COUNT,
        help="how many findings the synthesis model must return (default 5)",
    )
    parser.add_argument(
        "--inventory",
        default=None,
        help="optional inventory.json path; enables hotspot-aware ranking",
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

    inventory: dict[str, Any] | None = None
    if args.inventory:
        try:
            inventory = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: could not read {args.inventory}: {exc}", file=sys.stderr)
            return 2

    if args.top < 1:
        print("error: --top must be >= 1", file=sys.stderr)
        return 2

    prompt = build_prompt(raw, top_n=args.top, inventory=inventory)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(prompt.encode("utf-8"))
    print(f"wrote {out_path} ({len(raw)} raw findings, top {args.top})")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
