"""Agent dispatch: plan files, prompt rendering, output validation and retries (spec 3.2).

A plan file is a JSON list of entries ``{"id", "role", "prompt", "output", "model"}``; ``prompt``
and ``output`` are absolute POSIX-style paths inside the workdir. Gap entries also carry
``doc`` (the target doc) and verify entries ``edits`` (the edit ids of their batch).

- ``plan_docs`` writes ``plan-docs.json``: one review entry per unit of ``units.json`` (id the
  unit id, prompt ``prompts/review-uNNN.md`` from template ``review-first`` or ``review-later``
  by ``changes.json``'s mode, output ``review/uNNN.json``) and one gap entry per target doc of
  ``gaps.json`` (ids ``g001``... in path order, prompt ``prompts/gap-gNNN.md``, output
  ``gaps/gNNN.json``). Both inputs are already within their caps.
- ``plan_verify`` writes ``plan-verify.json``: one entry per batch within ``caps.verify``
  (ids ``v01``..., prompt ``prompts/verify-vNN.md``, output ``verdicts/vNN.json``).
- ``plan_retry`` appends review entries for the retry units of ``dd_units.retry_units`` to
  ``plan-docs.json`` and writes their prompts; ``not_reviewed`` collects, per valid review
  output, the ranges its agent reported as ``not_reviewed`` (an optional key).
- ``check_outputs`` validates a wave's outputs; ``write_retry`` writes ``retry.json``;
  ``collect_verdicts`` writes ``verdicts.json``.

Templates live in ``prompts/`` next to the scripts directory; ``{{name}}`` placeholders are
filled in one pass, so a value is never rescanned.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, NotRequired, TypedDict, TypeGuard

from dd_common import EXIT_MISSING, EXIT_OK, StepError, read_json, write_json

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
CONTEXT_LINES = 10
DEFAULT_VERIFY_CAP = 25
EDIT_TYPES = {"review": ("correct", "remove", "anchor"), "gap": ("add",)}
QUESTION_KINDS = {"guarantee-mismatch": "code", "unsure": "question"}
REFUSAL_KINDS = ("not-user-facing", "already-documented", "target-refused")
VERDICTS = ("accept", "reject", "unsure")
ROLE_DIRS = {"review": "review", "gap": "gaps", "verify": "verdicts"}

_PLACEHOLDER = re.compile(r"\{\{([A-Za-z_]+)\}\}")
_TICKS = re.compile(r"`+")


class PlanEntry(TypedDict):
    id: str
    role: str
    prompt: str
    output: str
    model: str
    doc: NotRequired[str]
    edits: NotRequired[list[str]]


# ---------------------------------------------------------------- rendering

def render(template: str, values: Mapping[str, str], directory: Path | None = None) -> str:
    """Fill ``prompts/<template>.md``'s ``{{name}}`` placeholders from ``values``. A placeholder
    without a value, or a value no placeholder uses, raises ``KeyError``."""
    text = ((directory or PROMPTS_DIR) / f"{template}.md").read_text(encoding="utf-8")
    used = set(_PLACEHOLDER.findall(text))
    unknown = sorted(used - set(values))
    if unknown:
        raise KeyError(f"template {template} has no value for {', '.join(unknown)}")
    unused = sorted(set(values) - used)
    if unused:
        raise KeyError(f"template {template} has no placeholder for {', '.join(unused)}")
    return _PLACEHOLDER.sub(lambda m: values[m.group(1)], text)


def _fence(text: str, info: str = "text") -> str:
    """``text`` in a fenced block whose fence is longer than any backtick run inside it."""
    longest = max((len(m) for m in _TICKS.findall(text)), default=0)
    fence = "`" * max(3, longest + 1)
    body = text if text.endswith("\n") or not text else text + "\n"
    return f"{fence}{info}\n{body}{fence}"


def _ranges(ranges: Iterable[Sequence[int]]) -> str:
    return ", ".join(f"{r[0]}-{r[1]}" for r in ranges)


def _doc_lines(root: Path, doc: str) -> list[str] | None:
    try:
        return (root / doc).read_bytes().decode("utf-8", "replace").splitlines()
    except OSError:
        return None


def _docs_value(root: Path, unit: Mapping[str, Any], affected: Mapping[str, Any],
                later: bool) -> str:
    out = []
    for entry in unit["docs"]:
        lines = _doc_lines(root, entry["doc"])
        size = f" ({len(lines)} lines)" if lines is not None else ""
        line = f"- {entry['doc']}{size}: lines {_ranges(entry['ranges'])}"
        if later:
            sections = affected.get(entry["doc"], {}).get("sections", [])
            line += f"; changed sections: {_ranges(sections) if sections else 'none'}"
        out.append(line)
    return "\n".join(out)


def _in_ranges(line: int, ranges: Iterable[Sequence[int]]) -> bool:
    return any(r[0] <= line <= r[1] for r in ranges)


def _anchor_line(ref: str, doc: str, line: int, file: str, span: Sequence[int]) -> str:
    return f"- `{ref}` ({doc} line {line}) -> {file}:{span[0]}-{span[1]}"


def _anchors_value(unit: Mapping[str, Any], affected: Mapping[str, Any], later: bool,
                   last_run: str) -> str:
    """One line per anchor with its reading range; on a later run only the anchors the changes
    touched, then the names that no longer resolve (with the definition they had)."""
    anchors = unit["anchors"]
    if later:
        touched = {(doc, r["line"], r["ref"]) for doc, entry in affected.items()
                   for r in entry.get("anchor_reasons", [])}
        anchors = [a for a in anchors if (a["doc"], a["line"], a["ref"]) in touched]
    out = [_anchor_line(a["ref"], a["doc"], a["line"], a["file"], a.get("reading")
                        or [a["start"], a["end"]]) for a in anchors]
    if later:
        for entry in unit["docs"]:
            for miss in affected.get(entry["doc"], {}).get("missing", []):
                if _in_ranges(miss["line"], entry["ranges"]):
                    out.append(f"- `{miss['ref']}` ({entry['doc']} line {miss['line']}) -> "
                               f"no longer defined; was {miss['file']}:{miss['start']}-"
                               f"{miss['end']} at commit {last_run}")
    return "\n".join(out) if out else "(none)"


def _diff_value(hunks: Sequence[Mapping[str, Any]]) -> str:
    """The hunks as a unified diff, one ``--- file`` header per file, in a fenced block."""
    out: list[str] = []
    current = None
    for hunk in hunks:
        if hunk["file"] != current:
            current = hunk["file"]
            out.append(f"--- {current}")
        old_count = hunk["old_end"] - hunk["old_start"] + 1
        new_count = hunk["new_end"] - hunk["new_start"] + 1
        out.append(f"@@ -{hunk['old_start']},{old_count} +{hunk['new_start']},{new_count} @@")
        out.append(hunk["text"].rstrip("\n"))
    return _fence("\n".join(out), "diff") if out else "(no hunks)"


def _gaps_value(gaps: Sequence[Mapping[str, Any]]) -> str:
    out = []
    for gap in gaps:
        parent = f"`{gap['parent']}`" if gap.get("parent") else "none"
        out.append(f"- {gap['kind']} `{gap['name']}`, parent {parent}, "
                   f"{gap['file']}:{gap['line']}, {gap['gap_kind']}, "
                   f"target line {gap['target_line']}, reason {gap['reason']}")
    return "\n".join(out)


def _edit_value(edit: Mapping[str, Any], lines: list[str] | None) -> str:
    start, end = int(edit["start_line"]), int(edit["end_line"])
    evidence = ", ".join(edit.get("evidence") or []) or "none"
    out = [f"### Edit {edit['id']} ({edit['type']})", "",
           f"- Doc: {edit['doc']}, lines {start}-{end}",
           f"- Claim: {edit['claim']}",
           f"- Evidence: {evidence}"]
    if edit.get("subject"):
        out.append(f"- Subject: `{edit['subject']}`")
    out += ["", "Old text:", _fence(edit["old"]), ""]
    if edit["new"]:
        out += ["New text:", _fence(edit["new"])]
    else:
        out.append("New text: empty (the edit deletes these lines).")
    if lines is not None:
        low, high = max(1, start - CONTEXT_LINES), min(len(lines), end + CONTEXT_LINES)
        numbered = "\n".join(f"{n}: {lines[n - 1]}" for n in range(low, high + 1))
        out += ["", f"The doc around the edit as it is now (lines {low}-{high}):",
                _fence(numbered)]
    else:
        out += ["", "The doc could not be read; open it yourself."]
    return "\n".join(out)


# ---------------------------------------------------------------- plans

def _entry(workdir: Path, eid: str, role: str, model: str) -> PlanEntry:
    prefix = {"review": "review", "gap": "gap", "verify": "verify"}[role]
    return {"id": eid, "role": role,
            "prompt": (workdir / "prompts" / f"{prefix}-{eid}.md").absolute().as_posix(),
            "output": (workdir / ROLE_DIRS[role] / f"{eid}.json").absolute().as_posix(),
            "model": model}


def _write_prompt(entry: PlanEntry, text: str) -> None:
    path = Path(entry["prompt"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _require(workdir: Path, name: str, step: str) -> Any:
    path = workdir / name
    if not path.is_file():
        raise StepError(f"{name} is missing; run {step} first", EXIT_MISSING)
    return read_json(path)


def _review_entry(root: Path, workdir: Path, config: Mapping[str, Any],
                  unit: Mapping[str, Any], changes: Mapping[str, Any]) -> PlanEntry:
    """The plan entry of one review unit, its prompt written."""
    repo = root.resolve().as_posix()
    later = changes.get("mode") != "first"
    last_run = str(changes.get("last_run") or "")[:9]
    affected = changes.get("affected", {}) if later else {}
    entry = _entry(workdir, str(unit["id"]), "review", str(config["models"]["review"]))
    values = {"repo": repo, "unit": str(unit["id"]), "output": entry["output"],
              "docs": _docs_value(root, unit, affected, later),
              "anchors": _anchors_value(unit, affected, later, last_run)}
    if later:
        values.update(diff=_diff_value(unit["hunks"]), last_run=last_run)
    _write_prompt(entry, render("review-later" if later else "review-first", values))
    return entry


def plan_docs(root: Path, workdir: Path, config: Mapping[str, Any]) -> list[PlanEntry]:
    """Write the review and gap prompts and ``plan-docs.json``; create the output dirs. The gap
    prompts list ``inventory.json``'s docs as the only docs that count as documentation."""
    units = _require(workdir, "units.json", "dd_units")
    gaps = _require(workdir, "gaps.json", "dd_gaps")
    changes = _require(workdir, "changes.json", "dd_changes")
    inventory = _require(workdir, "inventory.json", "dd_inventory")
    in_scope = "\n".join(f"- {d}" for d in sorted(inventory.get("docs", []))) or "(none)"
    for name in ROLE_DIRS.values():
        (workdir / name).mkdir(parents=True, exist_ok=True)
    models = config["models"]
    repo = root.resolve().as_posix()
    plan: list[PlanEntry] = [_review_entry(root, workdir, config, unit, changes)
                             for unit in units["units"]]
    for number, doc in enumerate(sorted(gaps["targets"]), 1):
        entry = _entry(workdir, f"g{number:03d}", "gap", str(models["gap"]))
        entry["doc"] = doc
        _write_prompt(entry, render("gap", {
            "repo": repo, "doc": doc, "docs_in_scope": in_scope,
            "gaps": _gaps_value(gaps["targets"][doc]),
            "output": entry["output"], "id": entry["id"]}))
        plan.append(entry)
    write_json(workdir / "plan-docs.json", plan)
    return plan


def plan_retry(root: Path, workdir: Path, config: Mapping[str, Any],
               units: Sequence[Mapping[str, Any]]) -> list[PlanEntry]:
    """Review entries for ``units`` (retry units), their prompts written and the entries
    appended to ``plan-docs.json``."""
    changes = _require(workdir, "changes.json", "dd_changes")
    plan: list[PlanEntry] = _require(workdir, "plan-docs.json", "dd_dispatch")
    entries = [_review_entry(root, workdir, config, unit, changes) for unit in units]
    write_json(workdir / "plan-docs.json", [*plan, *entries])
    return entries


def not_reviewed(workdir: Path, plan: Sequence[PlanEntry],
                 failed: Iterable[str]) -> dict[str, list[dict[str, Any]]]:
    """Per review entry with a valid output, the ranges its agent reported as
    ``not_reviewed`` (only the entries that have any)."""
    skip = set(failed)
    found: dict[str, list[dict[str, Any]]] = {}
    for entry in plan:
        if entry["role"] != "review" or entry["id"] in skip:
            continue
        path = Path(entry["output"])
        if not path.is_absolute():
            path = workdir / path
        ranges = read_json(path).get("not_reviewed") or []
        if ranges:
            found[entry["id"]] = [dict(r) for r in ranges]
    return found


def plan_verify(root: Path, workdir: Path, batches: Sequence[Sequence[Mapping[str, Any]]],
                config: Mapping[str, Any]) -> list[PlanEntry]:
    """Write one verifier prompt per batch within ``caps.verify`` and ``plan-verify.json``."""
    (workdir / "verdicts").mkdir(parents=True, exist_ok=True)
    cap = int(config.get("caps", {}).get("verify", DEFAULT_VERIFY_CAP))
    repo = root.resolve().as_posix()
    texts: dict[str, list[str] | None] = {}
    plan: list[PlanEntry] = []
    for number, batch in enumerate(batches[:cap], 1):
        entry = _entry(workdir, f"v{number:02d}", "verify", str(config["models"]["verify"]))
        entry["edits"] = [str(e["id"]) for e in batch]
        parts = []
        for edit in batch:
            if edit["doc"] not in texts:
                texts[edit["doc"]] = _doc_lines(root, edit["doc"])
            parts.append(_edit_value(edit, texts[edit["doc"]]))
        _write_prompt(entry, render("verify", {"repo": repo, "batch": entry["id"],
                                               "edits": "\n\n".join(parts),
                                               "output": entry["output"]}))
        plan.append(entry)
    write_json(workdir / "plan-verify.json", plan)
    return plan


# ---------------------------------------------------------------- validation

def _is_int(value: Any) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _fields(obj: Any, where: str, spec: Mapping[str, str]) -> list[str]:
    """Check ``obj`` is an object holding each key of ``spec`` with its kind: ``str``,
    ``int`` (>= 0), ``line`` (>= 1), ``list``, ``strs`` (list of str), ``str?`` (str or null)."""
    if not isinstance(obj, dict):
        return [f"{where} is not a JSON object"]
    problems = []
    for key, kind in spec.items():
        if key not in obj:
            problems.append(f"{where} has no {key}")
            continue
        value = obj[key]
        ok = {"str": isinstance(value, str),
              "str?": value is None or isinstance(value, str),
              "int": _is_int(value) and value >= 0,
              "line": _is_int(value) and value >= 1,
              "list": isinstance(value, list),
              "dict": isinstance(value, dict),
              "strs": isinstance(value, list) and all(isinstance(v, str) for v in value),
              }[kind]
        if not ok:
            problems.append(f"{where}: {key} is not {_KIND_NAMES[kind]}")
    return problems


_KIND_NAMES = {"str": "a string", "str?": "a string or null", "int": "an integer >= 0",
               "line": "a line number >= 1", "list": "a list", "dict": "an object",
               "strs": "a list of strings"}
_EDIT = {"id": "str", "doc": "str", "start_line": "line", "end_line": "line", "old": "str",
         "new": "str", "type": "str", "claim": "str", "evidence": "strs", "subject": "str?"}
_RANGE = {"doc": "str", "start_line": "line", "end_line": "line", "why": "str"}


def _line_order(obj: Mapping[str, Any], where: str) -> list[str]:
    start, end = obj.get("start_line"), obj.get("end_line")
    if _is_int(start) and _is_int(end) and start > end:
        return [f"{where}: start_line {start} is after end_line {end}"]
    return []


def _edits(edits: Sequence[Any], owner: Any, types: Sequence[str]) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for n, edit in enumerate(edits):
        where = f"edits[{n}]"
        found = _fields(edit, where, _EDIT)
        problems += found
        if not isinstance(edit, dict):
            continue
        problems += _line_order(edit, where)
        if isinstance(edit.get("type"), str) and edit["type"] not in types:
            problems.append(f"{where}: type {edit['type']!r} is not one of {', '.join(types)}")
        eid = edit.get("id")
        if isinstance(eid, str):
            if isinstance(owner, str) and not eid.startswith(f"{owner}-"):
                problems.append(f"{where}: id {eid!r} does not start with {owner}-")
            if eid in seen:
                problems.append(f"{where}: id {eid!r} repeats")
            seen.add(eid)
    return problems


def validate_review(obj: Any) -> list[str]:
    """Problems with a review output (spec 7.2); empty when valid."""
    if not isinstance(obj, dict):
        return ["output is not a JSON object"]
    problems = _fields(obj, "output", {
        "unit": "str", "claims_checked": "int", "code_claims": "dict",
        "unverified_blocks": "list", "edits": "list", "questions": "list"})
    claims = obj.get("code_claims")
    if isinstance(claims, dict):
        problems += [f"code_claims: {doc!r} is not a count >= 0"
                     for doc, count in claims.items() if not (_is_int(count) and count >= 0)]
    for key in ("unverified_blocks", "not_reviewed"):  # not_reviewed is optional
        ranges = obj.get(key) or []
        if not isinstance(ranges, list):
            problems.append(f"{key} is not a list")
            continue
        for n, block in enumerate(ranges):
            where = f"{key}[{n}]"
            problems += _fields(block, where, _RANGE)
            if isinstance(block, dict):
                problems += _line_order(block, where)
    if isinstance(obj.get("edits"), list):
        problems += _edits(obj["edits"], obj.get("unit"), EDIT_TYPES["review"])
    for n, question in enumerate(obj.get("questions") or []):
        where = f"questions[{n}]"
        problems += _fields(question, where, {"doc": "str", "line": "line", "kind": "str",
                                              "claim": "str", "evidence": "strs"})
        if not isinstance(question, dict) or not isinstance(question.get("kind"), str):
            continue
        extra = QUESTION_KINDS.get(question["kind"])
        if extra is None:
            problems.append(f"{where}: kind {question['kind']!r} is not one of "
                            f"{', '.join(QUESTION_KINDS)}")
        else:
            problems += _fields(question, where, {extra: "str"})
    return problems


def validate_gap(obj: Any, target: str | None = None) -> list[str]:
    """Problems with a gap output (spec 8.4); empty when valid. ``target`` is the plan entry's
    target doc: an edit aimed at any other doc is a problem too, so it is retried rather than
    taken as a candidate for a doc no gap agent was given."""
    if not isinstance(obj, dict):
        return ["output is not a JSON object"]
    problems = _fields(obj, "output", {"doc": "str", "edits": "list", "refusals": "list"})
    if isinstance(obj.get("edits"), list):
        problems += _edits(obj["edits"], obj.get("doc"), EDIT_TYPES["gap"])
        for n, edit in enumerate(obj["edits"]):
            path = edit.get("doc") if isinstance(edit, dict) else None
            if isinstance(path, str) and (not path.strip() or path == obj.get("doc")):
                problems.append(f"edits[{n}]: doc {path!r} is not the target doc's path")
            elif isinstance(path, str) and target is not None and path != target:
                problems.append(f"edits[{n}]: doc {path!r} is not the target doc {target!r}")
    for n, refusal in enumerate(obj.get("refusals") or []):
        where = f"refusals[{n}]"
        problems += _fields(refusal, where, {"name": "str", "kind": "str", "reason": "str"})
        kind = refusal.get("kind") if isinstance(refusal, dict) else None
        if isinstance(kind, str) and kind not in REFUSAL_KINDS:
            problems.append(f"{where}: kind {kind!r} is not one of {', '.join(REFUSAL_KINDS)}")
    return problems


def validate_verdicts(obj: Any, expected_ids: Iterable[str]) -> list[str]:
    """Problems with a verifier output (spec 9.2): every expected edit id exactly once, no
    other id; empty when valid."""
    if not isinstance(obj, dict):
        return ["output is not a JSON object"]
    problems = _fields(obj, "output", {"batch": "str", "verdicts": "list"})
    expected = list(expected_ids)
    counts = dict.fromkeys(expected, 0)
    for n, verdict in enumerate(obj.get("verdicts") or []):
        where = f"verdicts[{n}]"
        problems += _fields(verdict, where, {"edit": "str", "verdict": "str", "reason": "str"})
        if not isinstance(verdict, dict):
            continue
        if isinstance(verdict.get("verdict"), str) and verdict["verdict"] not in VERDICTS:
            problems.append(f"{where}: verdict {verdict['verdict']!r} is not one of "
                            f"{', '.join(VERDICTS)}")
        eid = verdict.get("edit")
        if isinstance(eid, str):
            if eid not in counts:
                problems.append(f"{where}: edit {eid!r} is not in this batch")
            else:
                counts[eid] += 1
    problems += [f"edit {eid!r} has no verdict" for eid, c in counts.items() if c == 0]
    problems += [f"edit {eid!r} has {c} verdicts" for eid, c in counts.items() if c > 1]
    return problems


def _problems(workdir: Path, entry: PlanEntry) -> list[str]:
    """Why ``entry``'s output is unusable: missing, not JSON, invalid, or another entry's."""
    path = Path(entry["output"])
    if not path.is_absolute():
        path = workdir / path
    if not path.is_file():
        return [f"{path.as_posix()} is missing"]
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"{path.as_posix()} is not JSON: {exc}"]
    role = entry["role"]
    if role == "review":
        problems, key = validate_review(obj), "unit"
    elif role == "gap":
        problems, key = validate_gap(obj, entry.get("doc")), "doc"
    else:
        problems, key = validate_verdicts(obj, entry.get("edits", [])), "batch"
    if isinstance(obj, dict) and isinstance(obj.get(key), str) and obj[key] != entry["id"]:
        problems.append(f"{key} {obj[key]!r} is not {entry['id']!r}")
    return problems


def check_outputs(workdir: Path, plan: Sequence[PlanEntry],
                  role: str) -> tuple[list[str], list[PlanEntry]]:
    """The ids of ``role`` entries whose output is valid, and the entries that failed."""
    valid: list[str] = []
    failed: list[PlanEntry] = []
    for entry in plan:
        if entry["role"] != role:
            continue
        if _problems(workdir, entry):
            failed.append(entry)
        else:
            valid.append(entry["id"])
    return valid, failed


def write_retry(workdir: Path, failed: Sequence[PlanEntry]) -> None:
    """Write ``retry.json``: the failed entries, in plan format."""
    write_json(workdir / "retry.json", list(failed))


def collect_verdicts(workdir: Path, plan: Sequence[PlanEntry]) -> dict[str, Any]:
    """Write ``verdicts.json``: each verdict of a valid batch output; every edit of a batch
    whose output is missing or invalid is unverified."""
    verdicts: dict[str, dict[str, str]] = {}
    unverified: list[str] = []
    for entry in plan:
        if entry["role"] != "verify":
            continue
        if _problems(workdir, entry):
            unverified += entry.get("edits", [])
            continue
        for verdict in read_json(Path(entry["output"]))["verdicts"]:
            verdicts[verdict["edit"]] = {"verdict": verdict["verdict"],
                                         "reason": verdict["reason"]}
    result: dict[str, Any] = {"verdicts": verdicts, "unverified": unverified}
    write_json(workdir / "verdicts.json", result)
    return result


def run(root: Path, workdir: Path, config: Mapping[str, Any]) -> list[PlanEntry]:
    """The ``start`` stage's dispatch step: ``plan_docs``."""
    return plan_docs(root, workdir, config)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write the review and gap agent prompts and plan-docs.json.")
    parser.add_argument("repo", type=Path)
    parser.add_argument("--workdir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        from dd_config import load_config
        config, _ = load_config(args.repo)
        plan = run(args.repo, args.workdir, config)
    except StepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    print(f"{(args.workdir / 'plan-docs.json').as_posix()}: {len(plan)} entries")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
