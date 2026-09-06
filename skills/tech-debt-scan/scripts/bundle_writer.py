"""Write a single ralph-friendly PBI bundle from an approved design.md finding.

Stage 2 of /tech-debt-promote. The promote orchestrator hands one parsed
finding (as produced by design_parser.parse_design) to ``write_bundle``; this
module materialises a self-contained PBI directory the user can paste straight
into a ralph queue.

Bundle layout (per [[cfa7e7f8-pbi-shape-type-aware]] — type=feature => PBI.md
is the entry file; ralph only recognises feature/bug/pr-feedback, so tech-debt
findings ride as features even though the bundle id keeps a ``chore-`` slug):

  <out_root>/chore-<slug>-<date>/
    PBI.md       # frontmatter (incl. blank target_repo:) + the finding body
    PLAN.md      # the finding's own acceptance criteria, or a one-step stub
    HISTORY.md   # empty, carrying only the executor-schema sentinel comment

Format invariants (the round-trip partner is the ralph queue schema):
  - Every file is LF-only. Each is built as ``"\n".join(parts)`` and written via
    ``write_bytes`` so Windows text-mode CRLF translation never corrupts it.
  - PBI.md frontmatter always carries ``target_repo:`` (blank) per
    [[77c83c69-target-repo-required]] so a later ralph claim does not fail.
  - PBI_OPTIONAL_KEYS (fingerprint, tier, type_id, family, debt_type, effort)
    follow ``category`` when the finding carries them (a v2 design.md anchor);
    absent from an older finding, so a v1 bundle's key order -- and bytes --
    never move (spec 8). ``priority`` is a rank artifact, never a PBI key.
  - PLAN.md's steps are ``acceptance_criteria(body_md)`` -- the checklist under
    the finding's own ``### Acceptance criteria`` section -- numbered in order;
    a finding with none (an older design, or the writer's own placeholder text)
    keeps the one-step stub pointing back at PBI.md.
  - Content is ASCII-only (no em-dash) so a default-encoding ``read_text`` on
    Windows byte-matches the utf-8 bytes written here.

Collision policy: a pre-existing bundle directory raises BundleWriteError unless
``force=True``, which overwrites the three files in place.

Slug validation is shared with design_parser/design_writer via validation.py.

Direct-path invocable (no package imports): `python bundle_writer.py ...`.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Final

from validation import ValidationError, validate_slug

# Maps a numeric finding severity (1-5) onto a ralph PBI severity word so the
# emitted PBI.md is claimable by ralph without further editing.
SEVERITY_WORD: Final[dict[int, str]] = {
    5: "critical",
    4: "high",
    3: "normal",
    2: "low",
    1: "low",
}
_DEFAULT_SEVERITY_WORD: Final[str] = "normal"

# A curated subset of the v2 anchor's optional keys (design_parser.OPTIONAL_KEYS
# carries eleven; these six are what a PBI executor actually needs), carried
# into PBI.md's frontmatter when present, appended after ``category`` in this
# fixed order so a v1 bundle's key order (and therefore its bytes) never moves.
# ``priority``, ``confidence``, ``diff``, ``reason`` and ``until`` are anchor
# keys too, but are deliberately not PBI keys: they are scan-time or review-
# workflow artifacts, not something an executor acts on.
PBI_OPTIONAL_KEYS: Final[tuple[str, ...]] = (
    "fingerprint",
    "tier",
    "type_id",
    "family",
    "debt_type",
    "effort",
)

_CRITERIA_HEADING: Final[str] = "### Acceptance criteria"
_CRITERION_RE: Final[re.Pattern[str]] = re.compile(r"^\s*-\s*\[[ xX]\]\s*(?P<text>.+?)\s*$")


class BundleWriteError(Exception):
    """Raised when a PBI bundle cannot be written."""


def _severity_word(severity: Any) -> str:
    try:
        return SEVERITY_WORD.get(int(severity), _DEFAULT_SEVERITY_WORD)
    except (TypeError, ValueError):
        return _DEFAULT_SEVERITY_WORD


def acceptance_criteria(body_md: str) -> list[str]:
    """The checklist items under ``### Acceptance criteria``, in order.

    Stops at the next heading of any level, so a later section's checkboxes are
    never absorbed. Returns [] when the section is absent or holds the writer's
    placeholder rather than a list. A criterion's own text is taken as written --
    it may carry a leading ``\\#`` (design_writer.free_text escapes a criterion
    that would otherwise read as a heading), and that backslash is not stripped
    here; it is body text, not a formatting instruction to this parser.
    """
    criteria: list[str] = []
    in_section = False
    for line in body_md.split("\n"):
        stripped = line.strip()
        if not in_section:
            if stripped == _CRITERIA_HEADING:
                in_section = True
            continue
        if stripped.startswith("#"):
            break
        match = _CRITERION_RE.match(line)
        if match:
            criteria.append(match.group("text"))
    return criteria


def _render_pbi(
    finding: dict[str, Any], bundle_id: str, source_design: str, date: str
) -> str:
    parts = [
        "---",
        f"id: {bundle_id}",
        "type: feature",
        "status: inbox",
        f"severity: {_severity_word(finding['severity'])}",
        "attempts: 0",
        f"created_at: {date}T00:00:00+00:00",
        f"updated_at: {date}T00:00:00+00:00",
        "depends_on: []",
        "target_repo:",
        f"source_design: {source_design}",
        f"category: {finding['category']}",
    ]
    # PBI_OPTIONAL_KEYS: classification axes from newer designs, appended after
    # category in that fixed order; omitted when absent so a bundle from an
    # older (v1) design.md stays byte-identical.
    for key in PBI_OPTIONAL_KEYS:
        value = finding.get(key)
        if value is not None:
            parts.append(f"{key}: {value}")
    parts += [
        "---",
        "",
        f"# {finding['title']}",
        "",
    ]
    header = "\n".join(parts) + "\n"
    body = str(finding.get("body_md", "")).rstrip("\n") + "\n"
    return header + body


def _render_plan(finding: dict[str, Any]) -> str:
    """The plan's steps are the finding's own acceptance criteria when it has any.

    Falls back to the one-step stub when ``body_md`` carries no ``###
    Acceptance criteria`` section (or a placeholder rather than a checklist),
    which is also what keeps a v1 finding's PLAN.md byte-identical (spec 8).
    """
    criteria = acceptance_criteria(str(finding.get("body_md", "")))
    if criteria:
        steps = [f"- [ ] {n}. {criterion}" for n, criterion in enumerate(criteria, start=1)]
    else:
        steps = ["- [ ] 1. Address the tech-debt finding described in PBI.md."]
    parts = [
        f"# Plan: {finding['title']}",
        "",
        *steps,
        "",
        "This bundle was generated by /tech-debt-promote from a design.md finding.",
        "See PBI.md for the evidence and the suggested fix.",
    ]
    return "\n".join(parts) + "\n"


def _render_history() -> str:
    return (
        "<!-- Executor appends attempt records here. Do not delete - "
        "required by the PBI directory schema. -->\n"
    )


def write_bundle(
    finding: dict[str, Any],
    *,
    out_root: Path,
    source_design: str,
    date: str,
    force: bool = False,
) -> Path:
    """Write one PBI bundle for ``finding`` under ``out_root``; return its dir.

    Raises BundleWriteError on an invalid slug, a pre-existing bundle (unless
    ``force``), or any filesystem write failure.
    """
    slug = str(finding.get("slug", ""))
    try:
        validate_slug(slug)
    except ValidationError as exc:
        raise BundleWriteError(f"invalid slug: {exc}") from exc

    bundle_id = f"chore-{slug}-{date}"
    bundle_dir = out_root / bundle_id

    if bundle_dir.exists() and not force:
        raise BundleWriteError(f"bundle already exists: {bundle_dir}")

    files = {
        "PBI.md": _render_pbi(finding, bundle_id, source_design, date),
        "PLAN.md": _render_plan(finding),
        "HISTORY.md": _render_history(),
    }

    try:
        bundle_dir.mkdir(parents=True, exist_ok=True)
        for name, text in files.items():
            (bundle_dir / name).write_bytes(text.encode("utf-8"))
    except OSError as exc:
        raise BundleWriteError(f"cannot write bundle {bundle_dir}: {exc}") from exc

    return bundle_dir


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write a ralph PBI bundle from a finding")
    parser.add_argument("--finding", required=True, help="path to a finding JSON object")
    parser.add_argument("--out-root", required=True, help="directory to write the bundle under")
    parser.add_argument("--source-design", required=True, help="path of the source design.md")
    parser.add_argument("--date", required=True, help="ISO date for the bundle id")
    parser.add_argument("--force", action="store_true", help="overwrite an existing bundle")
    args = parser.parse_args(argv)

    try:
        finding = json.loads(Path(args.finding).read_text(encoding="utf-8"))
        bundle_dir = write_bundle(
            finding,
            out_root=Path(args.out_root),
            source_design=args.source_design,
            date=args.date,
            force=args.force,
        )
    except (BundleWriteError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {bundle_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
