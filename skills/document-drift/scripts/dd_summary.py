"""The terminal summary of a run -> summary.md.

Reads the step outputs in the workdir. ``preflight.json`` carries, besides the preflight fields,
the run fields ``dd_run`` adds: ``run_id``, ``scope`` (``all`` or ``base:<ref>``), ``check`` and
``config_warnings``. ``inventory.json`` may carry ``scope_dropped`` (docs a ``--base`` run left
out). In check mode ``applied.json`` and ``commits.json`` are not read.

Counts: docs scanned are the inventory docs minus those extraction skipped; a token is
``resolved`` when it produced no candidate and no marker suppressed it; candidates are counted
per class from ``findings.json`` (superseded findings included under their class). The human
section is ``dd_commit.render_human``. A marker with a reason is stale when the lines it covers
hold no token it suppressed (``honoured``); markers without a reason are listed apart.

Every repository-derived string passes through ``dd_redaction.redact``. The text is written to
``summary.md`` as UTF-8 with LF endings and returned.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from dd_commit import render_human
from dd_common import EXIT_MISSING, EXIT_OK, StepError, read_json
from dd_redaction import redact

TOKEN_KINDS = ("path", "anchor", "script", "version", "tree")
CLASSES = ("provable-replace", "provable-delete", "human", "summary-only")


def _load(workdir: Path, name: str) -> Any:
    path = workdir / name
    if not path.is_file():
        raise StepError(f"missing {path}; run the earlier steps first", EXIT_MISSING)
    return read_json(path)


def _by_reason(title: str, entries: list[tuple[str, str]]) -> list[str]:
    """``title: N`` then each reason with its count and its paths, sorted."""
    lines = [f"{title}: {len(entries)}"]
    groups: dict[str, list[str]] = defaultdict(list)
    for path, reason in entries:
        groups[reason].append(path)
    for reason in sorted(groups):
        paths = sorted(groups[reason])
        lines.append(f"- {redact(reason)} ({len(paths)})")
        lines.extend(f"  - {redact(p)}" for p in paths)
    return lines


def _counts(counter: Counter[str], order: tuple[str, ...]) -> str:
    extra = sorted(k for k in counter if k not in order)
    return ", ".join(f"{redact(k)} {counter[k]}" for k in (*order, *extra))


def _marker_line(marker: dict[str, Any]) -> str:
    head = f"- {redact(str(marker.get('doc', '')))}:{marker.get('line')} {marker.get('kind')}"
    reason = marker.get("reason")
    return f"{head}: {redact(str(reason))}" if reason else head


def _is_stale(marker: dict[str, Any], honoured: list[dict[str, Any]]) -> bool:
    start, end = marker.get("target_line_start"), marker.get("target_line_end")
    if start is None or end is None:
        return True
    return not any(h.get("doc") == marker.get("doc") and start <= h.get("line", 0) <= end
                   for h in honoured)


def render(workdir: Path) -> str:
    """The summary text for the run whose outputs are in ``workdir``."""
    pre = _load(workdir, "preflight.json")
    inventory = _load(workdir, "inventory.json")
    tokens = _load(workdir, "tokens.json")
    findings_doc = _load(workdir, "findings.json")
    hunks = _load(workdir, "hunks-provable.json")["hunks"]
    check = bool(pre.get("check"))
    applied = None if check else _load(workdir, "applied.json")
    commits = None if check else _load(workdir, "commits.json")
    findings: list[dict[str, Any]] = findings_doc["findings"]
    honoured: list[dict[str, Any]] = findings_doc.get("honoured", [])

    sections: list[list[str]] = []
    sections.append([
        f"Run: {pre.get('run_id', '')}",
        f"Scope: {redact(str(pre.get('scope', 'all')))}",
        f"Base: {pre.get('head', '')}",
    ])

    docs_part: list[str] = []
    skipped = [(str(s["path"]), str(s["reason"])) for s in inventory.get("skipped", [])]
    skipped += [(str(s["doc"]), str(s["reason"])) for s in tokens.get("skipped", [])]
    unread = {s["doc"] for s in tokens.get("skipped", [])}
    docs_part.append(f"Docs scanned: {len([d for d in inventory['docs'] if d not in unread])}")
    dropped = inventory.get("scope_dropped") or []
    if dropped:
        docs_part.append(f"Docs out of scope: {len(dropped)}")
        docs_part.extend(f"  - {redact(str(d))}" for d in sorted(dropped))
    excluded = [(str(e["path"]), str(e["reason"])) for e in inventory.get("excluded", [])]
    docs_part += _by_reason("Docs excluded", excluded)
    docs_part += _by_reason("Docs skipped", skipped)
    sections.append(docs_part)

    kinds: Counter[str] = Counter()
    for doc_tokens in tokens.get("docs", {}).values():
        kinds.update(str(t.get("kind")) for t in doc_tokens)
    total = sum(kinds.values())
    resolved = total - len(findings) - len(honoured)
    classes: Counter[str] = Counter(str(f.get("class")) for f in findings)
    counts = [
        f"Tokens: {total} ({_counts(kinds, TOKEN_KINDS)}); resolved {resolved}; "
        f"suppressed by a marker {len(honoured)}",
        f"Candidates: {len(findings)} ({_counts(classes, CLASSES)})",
    ]
    if applied is None:
        counts.append(f"Hunks: {len(hunks)} provable; check mode: no edits made")
    else:
        reverted = applied.get("reverted", [])
        counts.append(f"Hunks: {len(hunks)} provable; applied {len(applied.get('applied', []))};"
                      f" reverted {len(reverted)}")
        counts.extend(f"- {r['hunk']} reverted: {redact(str(r['reason']))}" for r in reverted)
    sections.append(counts)

    human = render_human(findings)
    if human:
        sections.append(human.rstrip("\n").split("\n"))

    markers: list[dict[str, Any]] = tokens.get("markers", [])
    no_reason = [m for m in markers if not m.get("reason")]
    if no_reason:
        sections.append(["Markers without a reason:", *(_marker_line(m) for m in no_reason)])
    stale = [m for m in markers if m.get("reason") and _is_stale(m, honoured)]
    if stale:
        sections.append(["Stale markers (their block holds no suppressed reference):",
                         *(_marker_line(m) for m in stale)])

    notes: list[str] = []
    if findings_doc.get("history_unavailable"):
        notes.append("History unavailable: git blame or a snapshot tree could not be read for "
                     "some references; they were not checked against history.")
    warnings = pre.get("config_warnings") or []
    if warnings:
        notes.append("Config warnings:")
        notes.extend(f"- {redact(str(w))}" for w in warnings)
    if notes:
        sections.append(notes)

    branch = commits.get("branch") if commits else None
    if branch:
        shas = " ".join(str(s) for s in commits.get("commits", [])) if commits else ""
        sections.append([f"Branch: {redact(str(branch))}", f"Commits: {shas}"])
    else:
        sections.append(["No branch created."])
    return "\n\n".join("\n".join(part) for part in sections) + "\n"


def run(workdir: Path) -> str:
    """Render the summary, write ``workdir/summary.md`` (UTF-8, LF) and return the text."""
    text = render(workdir)
    (workdir / "summary.md").write_bytes(text.encode("utf-8"))
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the run summary.")
    parser.add_argument("--workdir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        text = run(args.workdir)
    except StepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    sys.stdout.write(text)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
