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
- ``plan_verify_readme`` appends the README's statement batches to ``plan-verify.json``
  (phase B spec 7): the statements without ``prereject``, grouped by ``section`` in README
  order and cut into batches of ``caps.readme_batch`` (a batch never mixes sections; the
  ``caps.verify`` cap is phase A's alone), ids continuing after the ones already there, key
  ``statements``, prompt from ``verify-readme``.
- ``plan_retry`` appends review entries for the retry units of ``dd_units.retry_units`` to
  ``plan-docs.json`` and writes their prompts; ``not_reviewed`` collects, per valid review
  output, the ranges its agent reported as ``not_reviewed`` (an optional key).
- ``plan_readme`` writes ``plan-readme.json``: one writer entry ``r001`` (prompt
  ``prompts/readme-r001.md``, output ``readme/r001.json``) rendered from ``sheets.json``.
- ``check_outputs`` validates a wave's outputs (a writer output also by
  ``dd_readme.structural_problems`` against ``sheets.json`` and ``readme_lines``, a README
  batch's verdicts by ``validate_readme_verdicts``); ``write_retry`` writes ``retry.json``;
  ``collect_verdicts`` writes ``verdicts.json``.

Templates live in ``prompts/`` next to the scripts directory; ``{{name}}`` placeholders are
filled in one pass, so a value is never rescanned.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, NotRequired, TypedDict, TypeGuard

from dd_common import EXIT_MISSING, EXIT_OK, StepError, read_json, write_json
from dd_config import DEFAULTS

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
CONTEXT_LINES = 10
DEFAULT_VERIFY_CAP = 25
EDIT_TYPES = {"review": ("correct", "remove", "anchor"), "gap": ("add",)}
QUESTION_KINDS = {"guarantee-mismatch": "code", "unsure": "question"}
REFUSAL_KINDS = ("not-user-facing", "already-documented", "target-refused")
VERDICTS = ("accept", "reject", "unsure")
ROLE_DIRS = {"review": "review", "gap": "gaps", "verify": "verdicts", "sheet": "sheets",
             "readme": "readme"}
NO_DESCRIPTION = "(the manifest has no description)"
# manifest -> where its description lives: TOML tables, or None for package.json's key
_DESCRIPTIONS: dict[str, tuple[str, ...] | None] = {
    "pyproject.toml": ("project", "tool.poetry"), "Cargo.toml": ("package",),
    "package.json": None}

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
    statements: NotRequired[list[str]]


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


NO_ANCHORS = "no anchors in these lines"


def _docs_value(root: Path, unit: Mapping[str, Any], affected: Mapping[str, Any],
                later: bool) -> str:
    """One line per doc of the unit: its size, the reviewed ranges, on a later run the changed
    sections, and ``NO_ANCHORS`` when none of the unit's anchors sits in those ranges (the
    agent is asked for ``anchor`` edits and unverified blocks there)."""
    out = []
    for entry in unit["docs"]:
        lines = _doc_lines(root, entry["doc"])
        size = f" ({len(lines)} lines)" if lines is not None else ""
        line = f"- {entry['doc']}{size}: lines {_ranges(entry['ranges'])}"
        if later:
            sections = affected.get(entry["doc"], {}).get("sections", [])
            line += f"; changed sections: {_ranges(sections) if sections else 'none'}"
        if not any(a["doc"] == entry["doc"] and _in_ranges(int(a["line"]), entry["ranges"])
                   for a in unit["anchors"]):
            line += f"; {NO_ANCHORS}"
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
    prefix = {"review": "review", "gap": "gap", "verify": "verify", "sheet": "sheet",
              "readme": "readme"}[role]
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
    for role in ("review", "gap", "verify"):
        (workdir / ROLE_DIRS[role]).mkdir(parents=True, exist_ok=True)
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


def _sheet_files(area: Mapping[str, Any]) -> str:
    return "\n".join(f"- {f['path']} ({f['lines']} lines)" for f in area["files"])


def _sheet_hints(area: Mapping[str, Any]) -> str:
    lines = []
    for hint in area["hints"]:
        parent = f" (parent {hint['parent']})" if hint.get("parent") else ""
        hidden = " hidden" if hint.get("hidden") else ""
        lines.append(f"- {hint['kind']} {hint['name']}{parent} "
                     f"{hint['file']}:{hint['line']}{hidden}")
    return "\n".join(lines) or "(none)"


def plan_sheets(root: Path, workdir: Path, config: Mapping[str, Any]) -> list[PlanEntry]:
    """Append one sheet entry per area of ``areas.json`` to ``plan-docs.json``, within
    ``caps.sheet_agents``; the smallest areas past the cap are recorded in ``areas.json`` as
    ``unplanned``. Returns the sheet entries; prompts are ``prompts/sheet-aNN.md``."""
    areas = _require(workdir, "areas.json", "dd_areas")
    (workdir / ROLE_DIRS["sheet"]).mkdir(parents=True, exist_ok=True)
    cap = int(config["caps"]["sheet_agents"])
    ordered = sorted(areas["areas"], key=lambda a: (-int(a["lines"]), str(a["id"])))
    kept, dropped = ordered[:cap], ordered[cap:]
    repo = root.resolve().as_posix()
    entries: list[PlanEntry] = []
    for area in sorted(kept, key=lambda a: str(a["id"])):
        entry = _entry(workdir, str(area["id"]), "sheet", str(config["models"]["sheet"]))
        _write_prompt(entry, render("sheet", {
            "repo": repo, "area": entry["id"], "files": _sheet_files(area),
            "hints": _sheet_hints(area), "output": entry["output"]}))
        entries.append(entry)
    areas["unplanned"] = sorted(str(a["id"]) for a in dropped)
    write_json(workdir / "areas.json", areas)
    path = workdir / "plan-docs.json"
    existing = read_json(path) if path.is_file() else []
    write_json(path, [*existing, *entries])
    return entries


def _description(manifest: str, text: str) -> str:
    """The description ``manifest`` declares, or ``NO_DESCRIPTION``."""
    tables = _DESCRIPTIONS.get(manifest, ())
    try:
        if tables is None:
            data: Any = json.loads(text)
            value = data.get("description") if isinstance(data, dict) else None
            return value.strip() if isinstance(value, str) and value.strip() else NO_DESCRIPTION
        parsed: Any = tomllib.loads(text) if tables else {}
    except ValueError:  # json.JSONDecodeError and tomllib.TOMLDecodeError are ValueErrors
        return NO_DESCRIPTION
    for table in tables:
        node: Any = parsed
        for part in table.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        value = node.get("description") if isinstance(node, dict) else None
        if isinstance(value, str) and value.strip():
            return value.strip()
    return NO_DESCRIPTION


def _project(root: Path, inventory: Mapping[str, Any]) -> tuple[str, str]:
    """The project's name and description: from the first project file (root files first, then
    in path order) whose manifest names the project, else the root directory's name."""
    from dd_inventory import _manifest_name

    paths = sorted((str(p) for p in inventory.get("project_files", [])),
                   key=lambda p: (p.count("/"), p))
    for path in paths:
        manifest = path.rsplit("/", 1)[-1]
        try:
            text = (root / path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        name = _manifest_name(manifest, text)
        if name:
            return name, _description(manifest, text)
    return root.resolve().name, NO_DESCRIPTION


def _sheet_lines(sheet: Mapping[str, Any]) -> list[str]:
    """One line per surface entry and behaviour of a sheet; hidden entries are left out."""
    lines = []
    for entry in sheet.get("surface", []):
        if entry.get("hidden"):
            continue
        parent = f", parent `{entry['parent']}`" if entry.get("parent") else ""
        default = f"; default `{entry['default']}`" if entry.get("default") is not None else ""
        filled = " (filled from the scan)" if entry.get("filled") else ""
        lines.append(f"- {entry['id']} {entry['kind']} `{entry['name']}`{parent}: "
                     f"{entry['summary']}{default}; {entry['defined_at']}{filled}")
    for behaviour in sheet.get("behaviours", []):
        lines.append(f"- {behaviour['id']}: {behaviour['statement']} "
                     f"({', '.join(str(e) for e in behaviour['evidence'])})")
    return lines


def plan_readme(root: Path, workdir: Path, config: Mapping[str, Any]) -> list[PlanEntry]:
    """Write the README writer's prompt (``prompts/readme-r001.md``) from ``sheets.json`` and
    ``plan-readme.json`` with its one entry; create ``readme/``."""
    sheets = _require(workdir, "sheets.json", "dd_sheets")
    inventory = _require(workdir, "inventory.json", "dd_inventory")
    (workdir / ROLE_DIRS["readme"]).mkdir(parents=True, exist_ok=True)
    name, description = _project(root, inventory)
    lines = [line for aid in sorted(sheets["sheets"])
             for line in _sheet_lines(sheets["sheets"][aid])]
    unchecked = sorted({str(u["area"]) for u in sheets.get("unchecked", [])})
    entry = _entry(workdir, "r001", "readme", str(config["models"]["readme"]))
    _write_prompt(entry, render("readme", {
        "repo": root.resolve().as_posix(), "name": name, "description": description,
        "sheets": "\n".join(lines) or "(none)",
        "unchecked": "\n".join(f"- {a}" for a in unchecked) or "(none)",
        "readme_lines": str(config["readme_lines"]), "output": entry["output"]}))
    plan = [entry]
    write_json(workdir / "plan-readme.json", plan)
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


def _cited_line(cid: str, entry: Mapping[str, Any] | None) -> str:
    if entry is None:
        return f"- {cid}: (not in sheets.json)"
    if "name" in entry:
        return (f"- {cid}: {entry['kind']} `{entry['name']}`, {entry['summary']}, "
                f"{entry['defined_at']}")
    return f"- {cid}: {entry['statement']} ({', '.join(str(e) for e in entry['evidence'])})"


def _statement_value(statement: Mapping[str, Any], entries: Mapping[str, Mapping[str, Any]],
                     lines: Sequence[str]) -> str:
    """One statement of a README batch: its text, the cited sheet entries and the README
    around it, numbered."""
    start, end = int(statement["start_line"]), int(statement["end_line"])
    cited = [_cited_line(str(c), entries.get(str(c))) for c in statement["cites"]]
    low, high = max(1, start - CONTEXT_LINES), min(len(lines), end + CONTEXT_LINES)
    numbered = "\n".join(f"{n}: {lines[n - 1]}" for n in range(low, high + 1))
    return "\n".join([
        f"### Statement {statement['id']} (section {statement['section'] or 'none'}, "
        f"lines {start}-{end})", "",
        "Text:", _fence(str(statement["text"])), "",
        "Cited sheet entries:", *(cited or ["(none)"]), "",
        f"The README around it (lines {low}-{high}):", _fence(numbered)])


def plan_verify_readme(root: Path, workdir: Path, statements: Sequence[Mapping[str, Any]],
                       config: Mapping[str, Any]) -> list[PlanEntry]:
    """Append the README statements' verifier batches to ``plan-verify.json`` and write their
    prompts; ``readme.json`` and ``sheets.json`` give the README text and the cited
    entries."""
    path = workdir / "plan-verify.json"
    existing: list[PlanEntry] = read_json(path) if path.is_file() else []
    groups: list[list[Mapping[str, Any]]] = []
    for statement in statements:
        if statement.get("prereject"):
            continue
        if groups and groups[-1][0]["section"] == statement["section"]:
            groups[-1].append(statement)
        else:
            groups.append([statement])
    size = int(config["caps"]["readme_batch"])
    batches = [group[i:i + size] for group in groups for i in range(0, len(group), size)]
    plan: list[PlanEntry] = []
    if batches:
        (workdir / "verdicts").mkdir(parents=True, exist_ok=True)
        text = str(_require(workdir, "readme.json", "dd_readme")["text"])
        lines = re.split(r"\r?\n", text)  # as dd_readme numbers them
        if lines and lines[-1] == "":
            lines.pop()
        sheets = _require(workdir, "sheets.json", "dd_sheets")
        entries = {str(e["id"]): e for sheet in sheets["sheets"].values()
                   for key in ("surface", "behaviours") for e in sheet.get(key, [])}
        number = max((int(e["id"][1:]) for e in existing if re.fullmatch(r"v\d+", e["id"])),
                     default=0)
        repo = root.resolve().as_posix()
        for batch in batches:
            number += 1
            entry = _entry(workdir, f"v{number:02d}", "verify", str(config["models"]["verify"]))
            entry["statements"] = [str(s["id"]) for s in batch]
            _write_prompt(entry, render("verify-readme", {
                "repo": repo, "batch": entry["id"], "output": entry["output"],
                "statements": "\n\n".join(_statement_value(s, entries, lines)
                                          for s in batch)}))
            plan.append(entry)
    write_json(path, [*existing, *plan])
    return plan


# ---------------------------------------------------------------- validation

def _is_int(value: Any) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _fields(obj: Any, where: str, spec: Mapping[str, str]) -> list[str]:
    """Check ``obj`` is an object holding each key of ``spec`` with its kind: ``str``,
    ``int`` (>= 0), ``line`` (>= 1), ``bool``, ``list``, ``strs`` (list of str), ``str?`` (str
    or null)."""
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
              "bool": isinstance(value, bool),
              "strs": isinstance(value, list) and all(isinstance(v, str) for v in value),
              }[kind]
        if not ok:
            problems.append(f"{where}: {key} is not {_KIND_NAMES[kind]}")
    return problems


_KIND_NAMES = {"str": "a string", "str?": "a string or null", "int": "an integer >= 0",
               "line": "a line number >= 1", "list": "a list", "dict": "an object",
               "bool": "a boolean",
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


_SURFACE = {"kind": "str", "name": "str", "summary": "str", "defined_at": "str",
            "user_facing": "bool", "hidden": "bool", "parent": "str?", "default": "str?"}


def validate_sheet(obj: Any) -> list[str]:
    """Shape problems with a sheet output (spec 5.2); empty when well-formed. Content checks
    (places, hints, duplicates) belong to ``dd_sheets.validate``."""
    problems = _fields(obj, "output", {"area": "str", "surface": "list", "behaviours": "list",
                                       "dismissed": "list"})
    if not isinstance(obj, dict):
        return problems
    for key, spec in (("surface", _SURFACE),
                      ("behaviours", {"statement": "str", "evidence": "list"}),
                      ("dismissed", {"hint": "str", "why": "str"})):
        items = obj.get(key)
        for n, item in enumerate(items if isinstance(items, list) else []):
            problems += _fields(item, f"{key}[{n}]", spec)
    return problems


def validate_readme(obj: Any) -> list[str]:
    """Shape problems with the README writer's output (spec 6.3); empty when well-formed. The
    citation check is ``dd_readme``'s."""
    if not isinstance(obj, dict):
        return ["output is not a JSON object"]
    problems = _fields(obj, "output", {"text": "str", "claims": "list"})
    claims = obj.get("claims")
    for n, claim in enumerate(claims if isinstance(claims, list) else []):
        problems += _fields(claim, f"claims[{n}]",
                            {"start_line": "int", "end_line": "int", "cites": "strs"})
    return problems


def _verdict_problems(obj: Any, expected_ids: Iterable[str], key: str) -> list[str]:
    """Problems with a verifier output whose verdicts name their ``key`` (``edit`` or
    ``statement``): every expected id exactly once, no other id; empty when valid."""
    if not isinstance(obj, dict):
        return ["output is not a JSON object"]
    problems = _fields(obj, "output", {"batch": "str", "verdicts": "list"})
    expected = list(expected_ids)
    counts = dict.fromkeys(expected, 0)
    for n, verdict in enumerate(obj.get("verdicts") or []):
        where = f"verdicts[{n}]"
        problems += _fields(verdict, where, {key: "str", "verdict": "str", "reason": "str"})
        if not isinstance(verdict, dict):
            continue
        if isinstance(verdict.get("verdict"), str) and verdict["verdict"] not in VERDICTS:
            problems.append(f"{where}: verdict {verdict['verdict']!r} is not one of "
                            f"{', '.join(VERDICTS)}")
        eid = verdict.get(key)
        if isinstance(eid, str):
            if eid not in counts:
                problems.append(f"{where}: {key} {eid!r} is not in this batch")
            else:
                counts[eid] += 1
    problems += [f"{key} {eid!r} has no verdict" for eid, c in counts.items() if c == 0]
    problems += [f"{key} {eid!r} has {c} verdicts" for eid, c in counts.items() if c > 1]
    return problems


def validate_verdicts(obj: Any, expected_ids: Iterable[str]) -> list[str]:
    """Problems with a verifier output (spec 9.2): every expected edit id exactly once, no
    other id; empty when valid."""
    return _verdict_problems(obj, expected_ids, "edit")


def validate_readme_verdicts(obj: Any, expected_ids: Iterable[str]) -> list[str]:
    """Problems with a README batch's verifier output (phase B spec 7): as
    ``validate_verdicts``, each verdict naming its ``statement``."""
    return _verdict_problems(obj, expected_ids, "statement")


def _readme_problems(workdir: Path, obj: Any, readme_lines: int | None) -> list[str]:
    """``dd_readme.structural_problems`` for a well-formed writer output, against
    ``sheets.json`` and ``readme_lines`` (the default when None)."""
    from dd_readme import structural_problems  # dd_readme imports this module

    path = workdir / "sheets.json"
    if not path.is_file():
        return ["sheets.json is missing"]
    lines = int(DEFAULTS["readme_lines"]) if readme_lines is None else readme_lines
    return structural_problems(obj, read_json(path), lines)


def _problems(workdir: Path, entry: PlanEntry, root: Path | None = None, *,
              require_hints: bool = True, readme_lines: int | None = None) -> list[str]:
    """Why ``entry``'s output is unusable: missing, not JSON, invalid, or another entry's.
    ``require_hints`` is ``dd_sheets.validate``'s, for a sheet; ``readme_lines`` the config's,
    for the README writer (the default when None)."""
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
    elif role == "sheet":
        problems, key = validate_sheet(obj), "area"
    elif role == "readme":  # one writer: no id key to compare
        return validate_readme(obj) or _readme_problems(workdir, obj, readme_lines)
    elif "statements" in entry:
        problems, key = validate_readme_verdicts(obj, entry["statements"]), "batch"
    else:
        problems, key = validate_verdicts(obj, entry.get("edits", [])), "batch"
    if isinstance(obj, dict) and isinstance(obj.get(key), str) and obj[key] != entry["id"]:
        problems.append(f"{key} {obj[key]!r} is not {entry['id']!r}")
    if role == "sheet" and not problems:
        problems += _sheet_content_problems(workdir, entry, obj, root, require_hints)
    return problems


def _sheet_content_problems(workdir: Path, entry: PlanEntry, obj: Any,
                            root: Path | None, require_hints: bool) -> list[str]:
    """``dd_sheets.validate`` for a well-formed sheet; without ``root`` the file-reading
    rules are skipped."""
    from dd_sheets import validate  # dd_sheets imports this module lazily

    areas_path = workdir / "areas.json"
    area = next((a for a in read_json(areas_path)["areas"] if a["id"] == entry["id"]),
                None) if areas_path.is_file() else None
    if area is None:
        return [f"area {entry['id']!r} is not in areas.json"]
    tracked: set[str] | None = None
    inventory = workdir / "inventory.json"
    if root is not None and inventory.is_file():
        tracked = {str(p) for p in read_json(inventory)["files"]}
    return validate(obj, area, root, tracked, require_hints=require_hints)


def check_outputs(workdir: Path, plan: Sequence[PlanEntry], role: str, *,
                  root: Path | None = None,
                  require_hints: bool = True,
                  readme_lines: int | None = None) -> tuple[list[str], list[PlanEntry]]:
    """The ids of ``role`` entries whose output is valid, and the entries that failed."""
    valid: list[str] = []
    failed: list[PlanEntry] = []
    for entry in plan:
        if entry["role"] != role:
            continue
        if _problems(workdir, entry, root=root, require_hints=require_hints,
                     readme_lines=readme_lines):
            failed.append(entry)
        else:
            valid.append(entry["id"])
    return valid, failed


def write_retry(workdir: Path, failed: Sequence[PlanEntry]) -> None:
    """Write ``retry.json``: the failed entries, in plan format."""
    write_json(workdir / "retry.json", list(failed))


def collect_verdicts(workdir: Path, plan: Sequence[PlanEntry]) -> dict[str, Any]:
    """Write ``verdicts.json``: each verdict of a valid batch output; every edit of a batch
    whose output is missing or invalid is unverified. README batches (``statements``) go to
    ``readme`` and ``readme_unverified``, which are empty without a README."""
    found: dict[str, dict[str, dict[str, str]]] = {"edit": {}, "statement": {}}
    missing: dict[str, list[str]] = {"edit": [], "statement": []}
    for entry in plan:
        if entry["role"] != "verify":
            continue
        key = "statement" if "statements" in entry else "edit"
        if _problems(workdir, entry):
            missing[key] += (entry.get("statements", []) if key == "statement"
                             else entry.get("edits", []))
            continue
        for verdict in read_json(Path(entry["output"]))["verdicts"]:
            found[key][verdict[key]] = {"verdict": verdict["verdict"],
                                        "reason": verdict["reason"]}
    result: dict[str, Any] = {"verdicts": found["edit"], "unverified": missing["edit"],
                              "readme": found["statement"],
                              "readme_unverified": missing["statement"]}
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
