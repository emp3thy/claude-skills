"""Fact sheets: the validator for a sheet agent's output (spec 5.3), the script's repairs
(``correct_hidden``, ``fill``, spec 5.4) and ``sheets.json``.

``sheets.json`` is ``{"sheets": {"a01": sheet, ...}, "unchecked": [{"area", "why"}],
"filled": n, "hidden_corrected": n}``; each surface entry and behaviour carries an ``id``
(``a03-s12``, ``a03-b04``) for the README writer to cite.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dd_checks import _guarantees
from dd_common import EXIT_MISSING, EXIT_OK, StepError, read_json, write_json
from dd_defindex import norm

KINDS = ("command", "flag", "env", "config", "route", "tool", "param", "script", "entry",
         "function", "class", "module")
_SKIP_TOKENS = frozenset({"python", "node", "npm", "npx", "uv", "pip"})
_TOKEN = re.compile(r"[A-Za-z0-9_]+")
_SPAN = re.compile(r"`[^`]+`")
_PLACE = re.compile(r"(.+):(\d+)")
_PARENT_NOTE = re.compile(r"\s*\(parent [^)]*\)\s*$")
_WINDOW = 3

Key = tuple[str, str, str | None]


def _key(kind: str, name: str, parent: str | None) -> Key:
    return (kind, norm(name, routes=kind == "route"), parent or None)


def _tokens(name: str) -> list[str]:
    text = name
    if "/" in text and not text.startswith("/"):
        text = text.split("/", 1)[1]  # a leading directory matches anywhere
    return [t for t in _TOKEN.findall(text) if len(t) >= 3 and t not in _SKIP_TOKENS]


def _names_its_file(name: str, path: str) -> bool:
    text = name[len("python -m "):] if name.startswith("python -m ") else name
    stem = path.rsplit(".", 1)[0] if "." in path.rsplit("/", 1)[-1] else path
    dotted = text.replace(".", "/")  # a module under a source root (`src/`) names a path suffix
    return stem in (dotted, text) or stem.endswith("/" + dotted) or path.endswith("/" + text)


def _hint_dismissed(hint: Mapping[str, Any], dismissed: list[str]) -> bool:
    kind = str(hint["kind"])
    name = norm(str(hint["name"]), routes=kind == "route")
    for text in dismissed:
        text = _PARENT_NOTE.sub("", text.strip())
        first, _, rest = text.partition(" ")
        if rest and first in KINDS:
            if first == kind and norm(rest, routes=first == "route") == name:
                return True
        elif norm(text, routes=kind == "route") == name:
            return True
    return False


def validate(sheet: Any, area: Mapping[str, Any], root: Path | None,
             tracked: set[str] | None, *, require_hints: bool = True) -> list[str]:
    """Problems with one sheet output; empty when valid. Without ``root`` the file-reading
    rules (line within the file, name at its place) are skipped; without ``tracked`` so is
    the tracked-at-HEAD rule. Without ``require_hints`` (the output after the retry, spec
    5.4) a hint that is neither an entry nor dismissed is no problem: ``fill`` adds it."""
    if not isinstance(sheet, dict):
        return ["output is not a JSON object"]
    surface, behaviours, dismissed = (sheet.get(k) for k in
                                      ("surface", "behaviours", "dismissed"))
    if not (isinstance(surface, list) and isinstance(behaviours, list)
            and isinstance(dismissed, list)):
        return ["surface, behaviours and dismissed must all be lists"]
    paths = {str(f["path"]) for f in area["files"]}
    texts: dict[str, list[str]] = {}
    problems: list[str] = []

    def lines(path: str) -> list[str]:
        if path not in texts:
            try:
                content = (root / path).read_text("utf-8", errors="replace") if root else ""
            except OSError:
                content = ""
            texts[path] = content.splitlines()
        return texts[path]

    def place(ref: Any, what: str, name: str | None) -> None:
        match = _PLACE.fullmatch(str(ref))
        if not match:
            problems.append(f"{what}: {ref!r} is not path:line")
            return
        path, number = match.group(1), int(match.group(2))
        if path not in paths:
            problems.append(f"{what}: {path} is outside the area")
            return
        if tracked is not None and path not in tracked:
            problems.append(f"{what}: {path} is not tracked")
            return
        if root is None:
            return
        text = lines(path)
        if not 1 <= number <= len(text):
            problems.append(f"{what}: line {number} is outside {path} ({len(text)} lines)")
            return
        if name is None or _names_its_file(name, path):
            return
        window = "\n".join(text[max(0, number - 1 - _WINDOW):number + _WINDOW])
        if not any(token in window for token in _tokens(name)):
            problems.append(f"{what}: {name!r} is not within {_WINDOW} lines of {path}:{number}")

    seen: set[Key] = set()
    for n, entry in enumerate(surface):
        where = f"surface[{n}]"
        if entry.get("kind") not in KINDS:
            problems.append(f"{where}: kind {entry.get('kind')!r} is not one of the kinds")
        name = str(entry.get("name", ""))
        if not name.strip():
            problems.append(f"{where}: empty name")
        if "\n" in str(entry.get("summary", "")).strip():
            problems.append(f"{where}: summary is not one line")
        place(entry.get("defined_at"), where, name)
        key = _key(str(entry.get("kind")), name, entry.get("parent"))
        if key in seen:
            problems.append(f"{where}: duplicate of another entry {key}")
        seen.add(key)
    for n, behaviour in enumerate(behaviours):
        where = f"behaviours[{n}]"
        statement = str(behaviour.get("statement", ""))
        if not statement.strip() or "\n" in statement.strip():
            problems.append(f"{where}: statement is empty or has several lines")
        if not _SPAN.search(statement):
            problems.append(f"{where}: statement has no inline-code span")
        if _guarantees(statement):
            problems.append(f"{where}: statement has a guarantee word")
        evidence = behaviour.get("evidence")
        if not evidence:
            problems.append(f"{where}: no evidence")
        for ref in evidence or []:
            place(ref, f"{where} evidence", None)
    reasons = [str(d.get("hint", "")) for d in dismissed]
    missing = [f"{h['kind']} {h['name']}" for h in area["hints"]
               if _key(h["kind"], h["name"], h.get("parent")) not in seen
               and not _hint_dismissed(h, reasons)]
    if missing and require_hints:
        problems.append(f"hints neither an entry nor dismissed: {', '.join(missing)}")
    return problems


def correct_hidden(sheet: dict[str, Any], area: Mapping[str, Any]) -> int:
    """Give each surface entry matching a hint the hint's ``hidden``; return how many changed."""
    hidden = {_key(h["kind"], h["name"], h.get("parent")): bool(h.get("hidden"))
              for h in area["hints"]}
    changed = 0
    for entry in sheet["surface"]:
        key = _key(entry["kind"], entry["name"], entry.get("parent"))
        if key in hidden and entry.get("hidden") != hidden[key]:
            entry["hidden"] = hidden[key]
            changed += 1
    return changed


def fill(sheet: dict[str, Any], area: Mapping[str, Any]) -> int:
    """Add a surface entry for each hint that is neither an entry nor dismissed."""
    have = {_key(e["kind"], e["name"], e.get("parent")) for e in sheet["surface"]}
    reasons = [str(d.get("hint", "")) for d in sheet["dismissed"]]
    added = 0
    for hint in area["hints"]:
        key = _key(hint["kind"], hint["name"], hint.get("parent"))
        if key in have or _hint_dismissed(hint, reasons):
            continue
        sheet["surface"].append({
            "kind": hint["kind"], "name": hint["name"], "parent": hint.get("parent"),
            "summary": "from the pattern scan", "default": None,
            "defined_at": f"{hint['file']}:{hint['line']}", "user_facing": True,
            "hidden": bool(hint.get("hidden")), "filled": True})
        have.add(key)
        added += 1
    return added


def _load(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def run(root: Path, workdir: Path, config: Mapping[str, Any],
        failed: frozenset[str]) -> dict[str, Any]:
    """Write ``sheets.json``: each planned area's valid sheet with ids, hidden corrected and
    hints filled; every other area is unchecked with its reason. ``failed`` holds the areas
    whose output failed validation after the retry; a sheet short only of hints is valid here,
    since this step fills them."""
    from dd_dispatch import _problems  # dd_dispatch imports this module lazily

    areas_path = workdir / "areas.json"
    if not areas_path.is_file():
        raise StepError(f"{areas_path.as_posix()} is missing; run dd_areas first", EXIT_MISSING)
    areas = read_json(areas_path)
    by_id = {str(a["id"]): a for a in areas["areas"]}
    plan_path = workdir / "plan-docs.json"
    plan = read_json(plan_path) if plan_path.is_file() else []
    sheets: dict[str, Any] = {}
    unchecked: list[dict[str, str]] = []
    filled = corrected = 0
    for entry in plan:
        if entry["role"] != "sheet" or entry["id"] not in by_id:
            continue
        aid = str(entry["id"])
        out = Path(entry["output"])
        sheet = _load(out if out.is_absolute() else workdir / out)
        if aid in failed:
            unchecked.append({"area": aid, "why": "invalid after retry"})
        elif sheet is None:
            unchecked.append({"area": aid, "why": "no output"})
        elif _problems(workdir, entry, root=root, require_hints=False):
            unchecked.append({"area": aid, "why": "invalid after retry"})
        else:
            sheet = copy.deepcopy(sheet)
            corrected += correct_hidden(sheet, by_id[aid])
            filled += fill(sheet, by_id[aid])
            for n, item in enumerate(sheet["surface"], 1):
                item["id"] = f"{aid}-s{n:02d}"
            for n, item in enumerate(sheet["behaviours"], 1):
                item["id"] = f"{aid}-b{n:02d}"
            sheets[aid] = sheet
    unchecked += [{"area": str(a), "why": "over the cap"} for a in areas.get("unplanned", [])]
    result: dict[str, Any] = {"sheets": sheets, "unchecked": unchecked, "filled": filled,
                              "hidden_corrected": corrected}
    write_json(workdir / "sheets.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect the valid fact sheets into sheets.json.")
    parser.add_argument("repo", type=Path)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--failed", nargs="*", default=[], help="area ids invalid after retry")
    args = parser.parse_args(argv)
    try:
        run(args.repo, args.workdir, {}, frozenset(args.failed))
    except StepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
