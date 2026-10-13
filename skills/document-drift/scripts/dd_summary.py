"""The terminal summary of a run -> summary.md (spec 9.5).

``render`` and ``run`` read the workdir files of the three stages and write one section per
bullet of the spec (see ``render``). Absent files count as empty and their section says "not
run". ``preflight.json`` carries the run fields ``dd_run`` records (``run_id``, ``check``,
``base``). Under ``--check`` ``commits.json`` is not read, and the planned edits (kept and
accepted, or kept notice edits) are listed in the commit-bullet grammar
(``dd_commit.render_bullet``).

Every repository-derived string passes through ``dd_redaction.redact``. The text is written to
``summary.md`` as UTF-8 with LF endings and returned.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from dd_apply import selected_edits
from dd_commit import collect_human, gap_kind, human_line, render_bullet
from dd_common import EXIT_MISSING, EXIT_OK, StepError, read_json
from dd_readme import accepted as readme_accepted
from dd_redaction import redact

NOT_RUN = "not run"
CLEAR_REASONS = (("clear-anchored", "now anchored"), ("clear-changed", "block changed"),
                 ("clear-ignore", "drift-ignore"))
FIRST_SPLIT = ("not about the code (0 code claims)", "describes the code but names nothing",
               "not reviewed")


def _opt(workdir: Path, name: str) -> Any:
    path = workdir / name
    return read_json(path) if path.is_file() else None


def _r(value: Any) -> str:
    return redact(str(value))


def _counted(counter: Counter[str]) -> list[str]:
    return [f"- {_r(k)}: {counter[k]}" for k in sorted(counter)]


def _plural(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _run_section(pre: dict[str, Any], changes: dict[str, Any] | None) -> list[str]:
    mode = str(changes["mode"]) if changes else "unknown"
    scope = str(changes["scope"]) if changes else "unknown"
    lines = ["Run", f"Run id: {_r(pre.get('run_id', ''))}", f"Mode: {mode}",
             f"Scope: {_r(scope)}"]
    if changes and changes.get("last_run"):
        lines.append(f"Last run: {_r(changes['last_run'])} ({_r(changes.get('last_run_source'))})")
    lines.append(f"Head: {_r(pre.get('head', ''))}")
    if pre.get("base"):
        lines.append(f"Base: {_r(pre['base'])}")
    lines.append(f"Check: {'yes' if pre.get('check') else 'no'}")
    return lines


def _docs_section(inventory: dict[str, Any], anchors: dict[str, Any] | None) -> list[str]:
    excluded = Counter(str(e.get("reason")) for e in inventory.get("excluded", []))
    skipped = [(str(s.get("path", s.get("doc"))), str(s.get("reason")))
               for s in [*inventory.get("skipped", []), *(anchors or {}).get("skipped", [])]]
    lines = ["Docs", f"scanned: {len(inventory.get('docs', []))}",
             f"excluded: {sum(excluded.values())}", *_counted(excluded),
             f"skipped: {len(skipped)}"]
    lines += [f"- {_r(p)} ({_r(why)})" for p, why in sorted(skipped)]
    return lines


def _anchors_section(anchors: dict[str, Any] | None) -> list[str]:
    if anchors is None:
        return ["References and anchors", NOT_RUN]
    c = anchors.get("counts", {})
    unanchored = int(c.get("ambiguous", 0)) + int(c.get("unknown", 0))
    return ["References and anchors", f"references: {int(c.get('references', 0))}",
            f"anchored: {int(c.get('anchored', 0))}", f"unanchored: {unanchored}",
            f"- ambiguous: {int(c.get('ambiguous', 0))}",
            f"- unknown: {int(c.get('unknown', 0))}"]


def _checkability(anchors: dict[str, Any] | None, first: bool, claims: dict[str, int] | None,
                  anchor_edits: Counter[str]) -> list[str]:
    if anchors is None:
        return ["Checkability", NOT_RUN]
    docs: dict[str, dict[str, Any]] = anchors.get("checkability", {})
    lines = ["Checkability"]
    for doc in sorted(docs):
        d = docs[doc]
        lines.append(f"{_r(doc)}: {int(d['references'])} refs, {int(d['anchored'])} anchored "
                     f"({float(d['rate']) * 100:.0f}%)")

    def entry(doc: str, indent: str) -> str:
        n = anchor_edits.get(doc, 0)
        tail = f" ({_plural(n, 'anchor edit')} applied)" if n else ""
        return f"{indent}- {_r(doc)}{tail}"

    unverifiable = sorted(d for d in docs if docs[d].get("status") == "unverifiable")
    weak = sorted(d for d in docs if docs[d].get("status") == "weak")
    if unverifiable:
        lines.append("Unverifiable (no anchor):")
        if first:
            groups: dict[str, list[str]] = {name: [] for name in FIRST_SPLIT}
            for doc in unverifiable:
                if claims is None or doc not in claims:
                    groups[FIRST_SPLIT[2]].append(doc)
                elif int(claims[doc]) == 0:
                    groups[FIRST_SPLIT[0]].append(doc)
                else:
                    groups[FIRST_SPLIT[1]].append(doc)
            for name in FIRST_SPLIT:
                if groups[name]:
                    lines.append(f"  {name}:")
                    lines += [entry(doc, "    ") for doc in groups[name]]
        else:
            lines += [entry(doc, "  ") for doc in unverifiable]
    if weak:
        lines.append("Weakly anchored:")
        lines += [entry(doc, "  ") for doc in weak]
    if unverifiable or weak:
        lines.append("A later run cannot see code changes behind these docs until they name code.")
    return lines


def _notice_loop(notices: dict[str, Any] | None, effect: set[str]) -> list[str]:
    if notices is None:
        return ["Notice loop", NOT_RUN]
    decisions = {(d["doc"], int(d["line"])): str(d["action"]) for d in notices.get("decisions", [])}
    types: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    for edit in notices.get("edits", []):
        if str(edit["id"]) not in effect:
            continue
        types[str(edit["type"])] += 1
        if edit["type"] == "clear":
            reasons[decisions.get((edit["doc"], int(edit["start_line"])), "")] += 1
    split = ", ".join(f"{label} {reasons[action]}" for action, label in CLEAR_REASONS)
    return ["Notice loop",
            f"placed {types['notice']}, escalated {types['escalate']}, "
            f"cleared {types['clear']} ({split}), removed {types['unverified']}, "
            f"stale {len(notices.get('stale', []))}"]


def _change_set(changes: dict[str, Any]) -> list[str]:
    hunks: dict[str, list[Any]] = changes.get("hunks") or {}  # keyed by file
    lines = ["Change set", f"changed files {len(changes.get('changed_files', []))}, "
             f"hunks {sum(len(each) for each in hunks.values())}"]
    affected: dict[str, dict[str, Any]] = changes.get("affected", {})
    for doc in sorted(affected):
        a = affected[doc]
        reasons = []
        if a.get("anchor_reasons"):
            reasons.append(f"anchors {len(a['anchor_reasons'])}")
        if a.get("missing"):
            reasons.append(f"missing {len(a['missing'])}")
        if a.get("doc_changed"):
            reasons.append("doc changed")
        lines.append(f"- {_r(doc)}: {', '.join(reasons)}")
    return lines


def _units_section(units: dict[str, Any] | None, edits: dict[str, Any] | None,
                   changes: dict[str, Any] | None, gaps: dict[str, Any] | None,
                   first: bool) -> list[str]:
    if changes is not None and not first and not changes.get("review"):
        none = "No doc was affected"
        if gaps is not None and not gaps.get("targets"):
            return ["Review units", f"{none} and no gap candidate exists; "
                    "no agent was dispatched."]
        return ["Review units", f"{none}; no review agent was dispatched."]
    if units is None:
        return ["Review units", NOT_RUN]
    by_cap = {str(u) for u in units.get("unchecked", [])}
    retry = ([u for u in edits.get("unchecked_units", []) if str(u) not in by_cap]
             if edits else [])
    checked = len(units.get("units", [])) - len(retry)
    retry_units = [u for u in units.get("units", []) if u.get("retry_of")]
    ranges = list((edits or {}).get("not_reviewed", []))
    return ["Review units", f"checked {checked}, unchecked by cap {len(by_cap)}, "
            f"unchecked after retry {len(retry)}, retry units {len(retry_units)}, "
            f"not reviewed {len(ranges)} ranges",
            *(f"- {_r(str(r['doc']))}:{r['start_line']}-{r['end_line']} ({_r(str(r['why']))})"
              for r in ranges)]


def _claims_section(workdir: Path) -> list[str]:
    files = sorted((workdir / "review").glob("*.json")) if (workdir / "review").is_dir() else []
    if not files:
        return ["Claims checked", "claims checked: 0 (no review output)"]
    return ["Claims checked",
            f"claims checked: {sum(int(read_json(f).get('claims_checked', 0)) for f in files)}"]


def _edits_section(edits: dict[str, Any] | None) -> list[str]:
    if edits is None:
        return ["Edits proposed", NOT_RUN]
    sources = Counter(str(e.get("source")) for e in edits["edits"])
    lines = ["Edits proposed"]
    lines += [f"{name}: {sources.get(name, 0)}" for name in ("review", "gap", "notice")]
    return lines


def _checks_section(edits: dict[str, Any] | None) -> list[str]:
    if edits is None:
        return ["Script checks", NOT_RUN]
    failing = Counter(str(e["check"]) for e in edits["edits"] if e.get("check"))
    kept = sum(e.get("status") == "kept" for e in edits["edits"])
    return ["Script checks", *_counted(failing), f"kept {kept}"]


def _verdicts_section(verdicts: dict[str, Any] | None) -> list[str]:
    if verdicts is None:
        return ["Verdicts", NOT_RUN]
    kinds = Counter(str(v.get("verdict")) for v in verdicts.get("verdicts", {}).values())
    return ["Verdicts", f"accept {kinds['accept']}, reject {kinds['reject']}, "
            f"unsure {kinds['unsure']}, unverified {len(verdicts.get('unverified', []))}"]


def _applied_section(applied: dict[str, Any] | None, check: bool) -> list[str]:
    if applied is None:
        return ["Applied", NOT_RUN + (" (check mode)" if check else "")]
    return ["Applied", f"applied {len(applied.get('applied', []))}, "
            f"reverted {len(applied.get('reverted', []))}, "
            f"link updates {len(applied.get('link_updates', []))}",
            *(f"- {_r(d)}" for d in sorted(applied.get("docs", [])))]


def _gaps_section(gaps: dict[str, Any] | None, edits: dict[str, Any] | None) -> list[str]:
    if gaps is None:
        return ["Gaps", NOT_RUN]
    kinds = Counter(str(g.get("gap_kind")) for g in gaps.get("gaps", []))
    targets = Counter(str(g.get("target_doc")) for g in gaps.get("gaps", [])
                      if g.get("target_doc"))
    refusals = Counter(str(r.get("kind")) for r in (edits or {}).get("refusals", []))
    unchecked = sorted((edits or {}).get("unchecked_gap_docs", gaps.get("unchecked", [])))
    lines = ["Gaps", f"candidates {len(gaps.get('candidates', []))}",
             "gaps by kind: " + ", ".join(f"{k} {kinds.get(k, 0)}"
                                          for k in ("undocumented", "missing-from-list")),
             "targets by doc:", *(f"- {_r(d)}: {targets[d]}" for d in sorted(targets)),
             f"no home {len(gaps.get('no_home', []))}",
             "refusals: " + ", ".join(f"{_r(k)} {refusals.get(k, 0)}"
                                      for k in ("not-user-facing", "already-documented",
                                                *sorted(set(refusals) - {"not-user-facing",
                                                                         "already-documented"}))),
             f"unchecked gap docs: {len(unchecked)}", *(f"- {_r(d)}" for d in unchecked)]
    return lines


def _writer_attempts(workdir: Path) -> int:
    plan, retry = _opt(workdir, "plan-readme.json"), _opt(workdir, "retry.json")
    if not plan:
        return 0
    return 1 + sum(1 for e in retry or [] if e.get("role") == "readme")


def _written(pre: dict[str, Any], sheets: dict[str, Any] | None,
             readme: dict[str, Any] | None, applied: dict[str, Any] | None) -> str:
    record = (applied or {}).get("readme")
    if record:
        return f"written: README.md, {int(record['lines'])} lines"
    if pre.get("check"):
        reason = "check mode"
    elif not (sheets or {}).get("sheets"):
        reason = "no valid sheet"
    elif readme is None or readme.get("invalid") == ["no writer output"]:
        reason = "no writer output"
    elif readme.get("invalid"):
        reason = "invalid writer output"
    else:
        reason = "no accepted statement"
    return f"written: none ({reason})"


def _readme_section(workdir: Path, pre: dict[str, Any]) -> list[str]:
    areas = (_opt(workdir, "areas.json") or {}).get("areas", [])
    sheets, readme = _opt(workdir, "sheets.json"), _opt(workdir, "readme.json")
    verdicts = _opt(workdir, "verdicts.json")
    unchecked = (sheets or {}).get("unchecked", [])
    retried = sum(e.get("role") == "sheet" for e in _opt(workdir, "retry.json") or [])
    hints = sum(len(a.get("hints", [])) for a in areas)
    why = ", ".join(f"{_r(u['area'])}: {_r(u['why'])}" for u in unchecked)
    statements = (readme or {}).get("statements", [])
    found = (verdicts or {}).get("readme") or {}
    kinds = {s["id"]: str((found.get(s["id"]) or {}).get("verdict")) for s in statements}
    unverified = len((verdicts or {}).get("readme_unverified") or [])
    rejected = sum(bool(s.get("prereject")) or kinds[s["id"]] == "reject" for s in statements)
    return ["README",
            f"areas: {len(areas)} ({sum(int(a.get('lines', 0)) for a in areas)} lines, "
            f"area_lines {int((_opt(workdir, 'areas.json') or {}).get('area_lines', 0))})",
            f"sheets: {len((sheets or {}).get('sheets', {}))} valid, {len(unchecked)} unchecked "
            f"({why}), {retried} retried",
            f"hints: {hints - int((sheets or {}).get('filled', 0))} accounted for, "
            f"{int((sheets or {}).get('filled', 0))} filled from the scan",
            f"writer: {_plural(_writer_attempts(workdir), 'attempt')}",
            f"statements: {len(statements)} proposed, "
            f"{len(readme_accepted(readme or {}, verdicts or {}))} accepted, {rejected} rejected, "
            f"{sum(v == 'unsure' for v in kinds.values())} unsure, {unverified} unverified",
            _written(pre, sheets, readme, _opt(workdir, "applied.json"))]


def _human_section(workdir: Path, root: Path | None, edits: dict[str, Any] | None) -> list[str]:
    if edits is None:
        return ["Needs a human decision", NOT_RUN]
    found = collect_human(workdir, root)
    lines = ["Needs a human decision", f"entries: {len(found)}"]
    lines.extend(human_line(entry) for entry in found)
    return lines


def _markers_section(tokens: dict[str, Any] | None, anchors: dict[str, Any] | None,
                     notices: dict[str, Any] | None) -> list[str]:
    refs = [(str(r["doc"]), int(r["line"])) for r in (anchors or {}).get("references", [])]
    markers = [m for m in (tokens or {}).get("markers", []) if m.get("kind") == "drift-ignore"]
    bare = sorted(m for m in markers if not m.get("reason"))
    stale = []
    for m in markers:
        start, end = m.get("target_line_start"), m.get("target_line_end")
        if m.get("reason") and (start is None or end is None or not any(
                doc == m["doc"] and start <= line <= end for doc, line in refs)):
            stale.append(m)

    def where(m: dict[str, Any]) -> tuple[str, int]:
        return (str(m["doc"]), int(m["line"]))

    lines = ["Markers", f"markers without reasons: {len(bare)}"]
    lines += [f"- {_r(d)}:{n}" for d, n in sorted(where(m) for m in bare)]
    if anchors is None:
        lines.append(f"stale markers: {NOT_RUN}")
    else:
        lines.append(f"stale markers: {len(stale)}")
        lines += [f"- {_r(d)}:{n}" for d, n in sorted(where(m) for m in stale)]
    notes = sorted((str(s["doc"]), int(s["line"]), str(s.get("reason")))
                    for s in (notices or {}).get("stale", []))
    lines.append(f"stale notices: {len(notes)}")
    lines += [f"- {_r(d)}:{n} {_r(why)}" for d, n, why in notes]
    return lines


def _create_edit(workdir: Path, edits: dict[str, Any] | None) -> dict[str, Any] | None:
    """The README's ``create`` edit when a run without ``--check`` would write the README."""
    readme, verdicts = _opt(workdir, "readme.json"), _opt(workdir, "verdicts.json")
    create = next((e for e in (edits or {}).get("edits", [])
                   if e.get("type") == "create" and e.get("source") == "readme"), None)
    kept = readme_accepted(readme or {}, verdicts or {})
    if create is None or not kept:
        return None
    sheets = (_opt(workdir, "sheets.json") or {}).get("sheets", {})
    proposed = len((readme or {}).get("statements", []))
    return {**create, "sheets": len(sheets), "removed": proposed - len(kept)}


def _result_section(workdir: Path, check: bool, edits: dict[str, Any] | None,
                    effect: set[str], gaps: dict[str, Any] | None) -> list[str]:
    lines = ["Result"]
    commits = None if check else _opt(workdir, "commits.json")
    if commits and commits.get("branch"):
        lines.append(f"Branch: {_r(commits['branch'])}")
        lines += [f"Commits: {_r(c['sha'])} ({_r(c['kind'])})" for c in commits.get("commits", [])]
        record = (_opt(workdir, "applied.json") or {}).get("readme")
        if record:
            lines.append(f"README: README.md ({int(record['lines'])} lines)")
    else:
        lines.append("No branch created")
    if check:
        create = _create_edit(workdir, edits)
        planned = sorted(([create] if create else [])
                         + [e for e in (edits or {}).get("edits", [])
                            if str(e["id"]) in effect and e.get("type") != "create"],
                         key=lambda e: (e["doc"], int(e["start_line"]), str(e["id"])))
        lines.append("Planned edits:")
        for edit in planned:
            if edit["type"] == "add":
                edit = {**edit, "gap_kind": gap_kind(edit, (gaps or {}).get("gaps", []))}
            lines.append(render_bullet(edit))
        lines.append("Exit: 1 (accepted edits exist)" if planned else "Exit: 0")
    return lines


def render(workdir: Path, root: Path | None = None) -> str:
    """The phase A summary (spec 9.5) of the run whose files are in ``workdir``.

    Plain text: a heading line per section, in the spec's order (``Run``, ``Docs``,
    ``References and anchors``, ``Checkability``, ``Notice loop``, ``Change set`` on a later
    run, ``Review units``, ``Claims checked``, ``Edits proposed``, ``Script checks``,
    ``Verdicts``, ``Applied``, ``Gaps``, ``README`` (README mode only),
    ``Needs a human decision``, ``Markers``, ``Result``),
    each followed by ``key: value`` lines and ``- item`` lists. Only ``preflight.json`` and
    ``inventory.json`` are required; an absent file is empty and its section says "not run".
    ``root`` (the repository) lets the human list read the first line of an escalated block."""
    pre = _opt(workdir, "preflight.json")
    inventory = _opt(workdir, "inventory.json")
    if pre is None or inventory is None:
        raise StepError(f"missing {workdir / 'preflight.json'} or inventory.json; run start",
                        EXIT_MISSING)
    check = bool(pre.get("check"))
    changes, anchors = _opt(workdir, "changes.json"), _opt(workdir, "anchors.json")
    notices, edits = _opt(workdir, "notices.json"), _opt(workdir, "edits.json")
    verdicts, gaps = _opt(workdir, "verdicts.json"), _opt(workdir, "gaps.json")
    applied_doc = _opt(workdir, "applied.json")
    applied = {str(x) for x in (applied_doc or {}).get("applied", [])}
    all_edits: list[dict[str, Any]] = (edits or {}).get("edits") or (notices or {}).get(
        "edits", [])
    if check:  # what a run without --check would apply
        effect = {str(e["id"])
                  for e in selected_edits(all_edits, (verdicts or {}).get("verdicts", {}))}
    else:
        effect = {str(e["id"]) for e in all_edits if str(e["id"]) in applied}
    notice_ids = {str(e["id"]) for e in (notices or {}).get("edits", [])}
    notice_effect = effect & notice_ids
    anchor_edits = Counter(str(e["doc"]) for e in all_edits
                           if e.get("type") == "anchor" and str(e["id"]) in effect)
    first = (changes or {}).get("mode", "first") == "first"
    code_claims = {str(k): int(v) for k, v in edits["code_claims"].items()} if edits else None

    sections = [_run_section(pre, changes), _docs_section(inventory, anchors),
                _anchors_section(anchors),
                _checkability(anchors, first, code_claims, anchor_edits),
                _notice_loop(notices, notice_effect)]
    if changes and not first:
        sections.append(_change_set(changes))
    units = _opt(workdir, "units.json")
    sections += [_units_section(units, edits, changes, gaps, first), _claims_section(workdir),
                 _edits_section(edits), _checks_section(edits), _verdicts_section(verdicts),
                 _applied_section(applied_doc, check), _gaps_section(gaps, edits)]
    if pre.get("readme"):
        sections.append(_readme_section(workdir, pre))
    sections += [_human_section(workdir, root, edits),
                 _markers_section(_opt(workdir, "tokens.json"), anchors, notices),
                 _result_section(workdir, check, edits, effect, gaps)]
    return "\n\n".join("\n".join(s) for s in sections) + "\n"


def run(workdir: Path, root: Path | None = None) -> str:
    """Render the phase A summary, write ``workdir/summary.md`` (UTF-8, LF) and return it."""
    text = render(workdir, root)
    (workdir / "summary.md").write_bytes(text.encode("utf-8"))
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the run summary.")
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("repo", nargs="?", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        text = run(args.workdir, args.repo)
    except StepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    sys.stdout.write(text)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
