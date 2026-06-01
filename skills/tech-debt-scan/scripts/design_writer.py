"""Render design.md and apply in-place ``mark_promoted`` status edits.

Stage 5 of /tech-debt-scan (``render_design_md``) turns the synthesised top-5
findings into the single ``design.md`` document the user reviews. Stage 3 of
/tech-debt-promote (``mark_promoted``) flips approved findings to ``promoted``
in place once their bundles have been emitted.

Format invariants (the round-trip partner is design_parser.parse_design):
  - Output is LF-only. The body is built as ``"\n".join(parts)`` and written via
    ``write_bytes`` so Windows text-mode CRLF translation never corrupts it.
  - After writing, ``render_design_md`` re-parses its own output as a self-check
    so format drift surfaces at write time, not just in tests.
  - ``mark_promoted`` writes ``<path>.tmp`` then ``os.replace`` onto ``<path>``
    (atomic on POSIX + Windows) and keeps the previous content at ``<path>.bak``.
    It only touches findings currently ``approved``; an already-``promoted``
    finding is an idempotent no-op (and skips the ``.bak`` rotation when nothing
    changes).

Slug + status validation is shared with design_parser via validation.py so the
write side and read side accept the same inputs.

Direct-path invocable (no package imports): `python design_writer.py ...`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from design_parser import DesignParseError, parse_design


class DesignWriteError(Exception):
    """Raised when rendering or an in-place status edit fails."""


def _render_frontmatter(inventory: dict[str, Any], scan_date: str) -> list[str]:
    languages = list(inventory["languages"])
    lines = [
        "---",
        f"scan_date: {scan_date}",
        f"root: {inventory['root']}",
        f"total_files: {inventory['total_files']}",
        f"total_loc: {inventory['total_loc']}",
        "languages:",
    ]
    lines.extend(f"- {lang}" for lang in languages)
    lines.append("---")
    return lines


def _render_header(inventory: dict[str, Any], scan_date: str) -> list[str]:
    languages = list(inventory["languages"])
    langs = ", ".join(languages)
    return [
        "",
        f"# Tech-debt scan - {scan_date}",
        "",
        f"Scanned `{inventory['root']}` - {inventory['total_files']} files, "
        f"{inventory['total_loc']} LOC across: {langs}.",
        "",
        "Review each finding below. To act on one, change its `status:` from `pending`",
        "to `approved` (or `rejected`), then run `/tech-debt-promote`.",
    ]


def _render_evidence(evidence: list[dict[str, Any]]) -> list[str]:
    return [f"- `{item['file']}:{item['line']}` - {item['note']}" for item in evidence]


def _render_finding(finding: dict[str, Any]) -> list[str]:
    lines = [
        "",
        f"## {finding['title']}",
        "",
        "```yaml",
        "status: pending",
        f"slug: {finding['slug']}",
        f"severity: {finding['severity']}",
        f"category: {finding['category']}",
        "```",
        "",
        "### Reasoning",
        "",
        finding["reasoning"],
        "",
        "### Evidence",
        "",
    ]
    lines.extend(_render_evidence(finding["evidence"]))
    lines.extend(
        [
            "",
            "### Suggested fix",
            "",
            finding["suggested_fix"],
        ]
    )
    return lines


def render_design_md(
    top5: dict[str, Any],
    inventory: dict[str, Any],
    scan_date: str,
    out_path: Path,
) -> None:
    """Render ``top5`` findings into ``out_path`` as an LF-only design.md.

    Raises DesignWriteError on an empty findings list (per the empty-input
    guard) or if the rendered document fails the round-trip self-check.
    """
    findings = top5.get("top5", [])
    if not findings:
        raise DesignWriteError("no findings to render")

    parts: list[str] = []
    parts.extend(_render_frontmatter(inventory, scan_date))
    parts.extend(_render_header(inventory, scan_date))
    for finding in findings:
        parts.extend(_render_finding(finding))

    text = "\n".join(parts) + "\n"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(text.encode("utf-8"))

    # Self-check: the document must parse back through the read side cleanly.
    try:
        parse_design(out_path)
    except DesignParseError as exc:
        raise DesignWriteError(f"self-check failed: {exc}") from exc


def _status_line_index(lines: list[str], anchor_lineno: int) -> int | None:
    """Return the 0-based index of the ``status:`` line inside the anchor.

    ``anchor_lineno`` is the 1-based line of the opening ```yaml fence (as
    reported by parse_design). The status key may sit anywhere inside the fence.
    """
    open_idx = anchor_lineno - 1
    i = open_idx + 1
    while i < len(lines) and lines[i].strip() != "```":
        if lines[i].lstrip().startswith("status:"):
            return i
        i += 1
    return None


def mark_promoted(path: Path, slugs: list[str]) -> None:
    """Flip each ``slug`` from ``approved`` to ``promoted`` in place.

    Raises DesignWriteError for an unknown slug or a finding that is not
    currently ``approved``. Already-``promoted`` findings are a no-op. When no
    finding actually changes, the file (and its ``.bak``) is left untouched.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DesignWriteError(f"could not read {path}: {exc}") from exc

    parsed = parse_design(path)
    by_slug = {f["slug"]: f for f in parsed["findings"]}

    for slug in slugs:
        if slug not in by_slug:
            raise DesignWriteError(f"unknown slug: {slug!r}")

    to_change: list[str] = []
    for slug in slugs:
        status = by_slug[slug]["status"]
        if status == "promoted":
            continue  # idempotent no-op
        if status != "approved":
            raise DesignWriteError(
                f"finding {slug!r} is not approved (status: {status!r})"
            )
        to_change.append(slug)

    if not to_change:
        return  # nothing to do; do not rotate .bak

    lines = text.splitlines()
    for slug in to_change:
        idx = _status_line_index(lines, by_slug[slug]["line"])
        if idx is None:
            raise DesignWriteError(f"could not locate status line for {slug!r}")
        lines[idx] = "status: promoted"

    new_text = "\n".join(lines) + "\n"

    bak_path = Path(str(path) + ".bak")
    bak_path.write_bytes(text.encode("utf-8"))

    tmp_path = Path(str(path) + ".tmp")
    tmp_path.write_bytes(new_text.encode("utf-8"))
    os.replace(tmp_path, path)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render or edit a design.md")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_render = sub.add_parser("render", help="render a design.md from JSON inputs")
    p_render.add_argument("--top5", required=True, help="path to top5 synthesis JSON")
    p_render.add_argument("--inventory", required=True, help="path to inventory.json")
    p_render.add_argument("--scan-date", required=True, help="ISO scan date")
    p_render.add_argument("--out", required=True, help="output design.md path")

    p_mark = sub.add_parser("mark-promoted", help="flip approved findings to promoted")
    p_mark.add_argument("design", help="path to design.md")
    p_mark.add_argument("--slug", action="append", default=[], help="slug to promote")

    args = parser.parse_args(argv)

    try:
        if args.cmd == "render":
            top5 = json.loads(Path(args.top5).read_text(encoding="utf-8"))
            inventory = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
            render_design_md(
                top5=top5,
                inventory=inventory,
                scan_date=args.scan_date,
                out_path=Path(args.out),
            )
            print(f"wrote {args.out}")
        else:
            mark_promoted(Path(args.design), slugs=args.slug)
            print(f"promoted {len(args.slug)} finding(s) in {args.design}")
    except (DesignWriteError, DesignParseError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
