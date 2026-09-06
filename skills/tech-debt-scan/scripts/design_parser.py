"""Parse a user-edited design.md into structured findings.

Stage 1 of /tech-debt-promote. The design.md is produced by design_writer
(stage 5 of /tech-debt-scan) and may be hand-edited by the user (flipping a
finding's ``status:`` from ``pending`` to ``approved`` / ``rejected``). This
module reads it back into a list of findings the promote orchestrator can act
on.

Document structure (see tests/golden/design-v1.md):
  - An optional top-level YAML frontmatter block delimited by ``---`` lines,
    surfaced as ``metadata``.
  - One ``## <title>`` H2 heading per finding.
  - Under each heading, a fenced ```yaml block (the "anchor") carrying the
    machine-readable keys: status, slug, severity, category.
  - The remaining prose under the heading is the finding's ``body_md``. A
    finding's section ends at the next H2 *or* the next H1 (spec 4.11), so a
    negative-space section (e.g. "# Considered and rejected") following the
    last finding is never absorbed into that finding's body. This boundary
    check ignores headings inside fenced code blocks, so a hand-edited quote
    or diff containing a line starting ``# `` or ``## `` (e.g. a code comment)
    does not truncate the body.

Only ``yaml.safe_load`` is used (never ``yaml.load``). Every DesignParseError
carries the 1-based source line of the offending heading or anchor so the user
can find it. Slug + status validation is shared with design_writer via
validation.py so the write side and read side reject the same inputs.

Direct-path invocable (no package imports): `python design_parser.py <path>`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Final

import yaml
from validation import ValidationError, validate_slug, validate_status

REQUIRED_KEYS: Final[tuple[str, ...]] = ("status", "slug", "severity", "category")

# Classification axes carried through when the anchor has them (newer designs);
# absent in older documents, never required. Values are passed through as-is —
# promote must not die on a hand-edited effort/confidence. v2 (spec 2-4) adds
# family, fingerprint, tier, priority, type_id, diff, reason and until; v1's
# confidence is kept so the writer can discard it (spec 8 compatibility).
OPTIONAL_KEYS: Final[tuple[str, ...]] = (
    "debt_type",
    "effort",
    "confidence",
    "family",
    "fingerprint",
    "tier",
    "priority",
    "type_id",
    "diff",
    "reason",
    "until",
)

_FRONTMATTER_FENCE: Final[str] = "---"
_YAML_OPEN: Final[str] = "```yaml"
_FENCE_CLOSE: Final[str] = "```"


class DesignParseError(Exception):
    """Raised when a design.md cannot be parsed."""


def _is_h2(line: str) -> bool:
    """True for a level-2 heading (``## ``), False for H1/H3 and deeper."""
    return line.startswith("## ") and not line.startswith("### ")


def _is_h1(line: str) -> bool:
    """True for a level-1 heading (``# ``), which never starts a finding (spec 4.11).

    A finding section therefore ends at the next H2 *or* the next H1, so the negative-space
    sections that follow the last finding are not absorbed into its body and copied into a PBI.
    """
    return line.startswith("# ")


def _ends_section(line: str) -> bool:
    return _is_h2(line) or _is_h1(line)


def _extract_frontmatter(lines: list[str]) -> tuple[dict[str, Any], int]:
    """Return (metadata, body_start_index).

    A frontmatter block is recognised only when the very first line is ``---``.
    Otherwise metadata is empty and the body starts at line 0.
    """
    if not lines or lines[0].strip() != _FRONTMATTER_FENCE:
        return {}, 0
    for idx in range(1, len(lines)):
        if lines[idx].strip() == _FRONTMATTER_FENCE:
            raw = yaml.safe_load("\n".join(lines[1:idx]))
            metadata = raw if isinstance(raw, dict) else {}
            return metadata, idx + 1
    raise DesignParseError("frontmatter opened at line 1 but never closed")


def _parse_anchor(
    section: list[tuple[int, str]], heading_lineno: int
) -> tuple[dict[str, Any], int]:
    """Locate and parse the ```yaml anchor inside a finding section.

    Returns (anchor_mapping, anchor_lineno). Raises if the anchor is absent,
    unterminated, or not a YAML mapping.
    """
    open_at: int | None = None
    anchor_lineno = heading_lineno
    body_lines: list[str] = []
    idx = 0
    while idx < len(section):
        lineno, text = section[idx]
        if text.strip() == _YAML_OPEN:
            open_at = idx
            anchor_lineno = lineno
            break
        idx += 1

    if open_at is None:
        raise DesignParseError(f"no yaml anchor under heading at line {heading_lineno}")

    yaml_body: list[str] = []
    idx = open_at + 1
    closed = False
    while idx < len(section):
        _, text = section[idx]
        if text.strip() == _FENCE_CLOSE:
            closed = True
            idx += 1
            break
        yaml_body.append(text)
        idx += 1
    if not closed:
        raise DesignParseError(f"yaml anchor at line {anchor_lineno} is not closed")

    raw = yaml.safe_load("\n".join(yaml_body))
    if not isinstance(raw, dict):
        raise DesignParseError(
            f"yaml anchor at line {anchor_lineno} is not a mapping"
        )

    # body_md is every section line that is not part of the anchor fence.
    for offset, (_, text) in enumerate(section):
        if open_at <= offset < idx:
            continue
        body_lines.append(text)
    raw["__body_md__"] = "\n".join(body_lines).strip("\n")
    raw["__line__"] = anchor_lineno
    return raw, anchor_lineno


def _build_finding(anchor: dict[str, Any], title: str, lineno: int) -> dict[str, Any]:
    for key in REQUIRED_KEYS:
        if key not in anchor:
            raise DesignParseError(
                f"finding {title!r} missing key {key!r} at line {lineno}"
            )

    # Per the truthiness-vs-None rule: a blank ``status:`` parses to None; coerce
    # to "" so it still reaches validate_status (errors with "unknown status")
    # rather than being silently skipped by a falsy check.
    raw_status = anchor["status"]
    status = "" if raw_status is None else str(raw_status)
    try:
        validate_status(status)
    except ValidationError as exc:
        raise DesignParseError(f"{exc} (line {lineno})") from exc

    slug = anchor["slug"]
    slug_str = "" if slug is None else str(slug)
    try:
        validate_slug(slug_str)
    except ValidationError as exc:
        raise DesignParseError(f"{exc} (line {lineno})") from exc

    finding: dict[str, Any] = {
        "title": title,
        "status": status,
        "slug": slug_str,
        "severity": anchor["severity"],
        "category": anchor["category"],
        "body_md": anchor["__body_md__"],
        "line": lineno,
    }
    for key in OPTIONAL_KEYS:
        if key in anchor and anchor[key] is not None:
            finding[key] = str(anchor[key])
    return finding


def parse_design(path: Path) -> dict[str, Any]:
    """Parse ``path`` into ``{"metadata": {...}, "findings": [...]}``.

    Raises DesignParseError (never a bare OSError / KeyError / ValueError) on a
    missing file, malformed frontmatter, a finding without a yaml anchor, an
    invalid slug/status, or a duplicate slug.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise DesignParseError(f"design file not found: {path}") from exc
    except OSError as exc:
        raise DesignParseError(f"could not read {path}: {exc}") from exc

    lines = text.splitlines()
    metadata, body_start = _extract_frontmatter(lines)

    findings: list[dict[str, Any]] = []
    seen_slugs: dict[str, int] = {}

    idx = body_start
    n = len(lines)
    while idx < n:
        if not _is_h2(lines[idx]):
            idx += 1
            continue
        heading_lineno = idx + 1
        title = lines[idx][3:].strip()
        section: list[tuple[int, str]] = []
        cursor = idx + 1
        in_fence = False
        while cursor < n:
            line = lines[cursor]
            if line.strip().startswith("```"):
                in_fence = not in_fence
            elif not in_fence and _ends_section(line):
                break
            section.append((cursor + 1, line))
            cursor += 1

        anchor, anchor_lineno = _parse_anchor(section, heading_lineno)
        finding = _build_finding(anchor, title, anchor_lineno)

        slug = finding["slug"]
        if slug in seen_slugs:
            raise DesignParseError(
                f"duplicate slug: {slug!r} at line {anchor_lineno} "
                f"(first seen at line {seen_slugs[slug]})"
            )
        seen_slugs[slug] = anchor_lineno

        findings.append(finding)
        idx = cursor

    return {"metadata": metadata, "findings": findings}


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse a design.md into JSON")
    parser.add_argument("design", help="path to design.md")
    args = parser.parse_args(argv)

    try:
        result = parse_design(Path(args.design))
    except DesignParseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # default=str: YAML auto-types ISO scalars in the frontmatter (e.g.
    # `scan_date: 2026-05-31` -> datetime.date), which json.dumps cannot
    # serialise on its own.
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
