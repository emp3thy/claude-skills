"""Commit the applied edits on a new branch with the owner-parsed message grammar (spec 9.4).

``run``, ``render_message``, ``render_bullet`` and ``collect_human`` make the corrections and
additions commits (see ``run``). Every repository-derived string of a message passes through
``dd_redaction.redact`` and every line is cut to ``LINE_MAX`` characters.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from dd_common import (
    EXIT_COMMIT,
    EXIT_MISSING,
    EXIT_OK,
    StepError,
    read_json,
    run_git,
    write_json,
)
from dd_defindex import norm
from dd_readme import accepted as readme_accepted
from dd_redaction import redact

LINE_MAX = 160
SUBJECTS = {"corrections": "docs(drift): correct stale docs",
            "additions": "docs(drift): document missing surface"}
KIND_ORDER = ("corrections", "additions")
ADDITION_SOURCES = ("gap", "readme")  # the README's create edit is an addition (spec B 8)
README = "README.md"
PROPOSED = " (proposed line)"  # a readme-rejected line is the proposed README's, not the file's
_SPAN = re.compile(r"`([^`\n]+)`")


def _line(text: str) -> str:
    """One redacted line of at most ``LINE_MAX`` characters (cut without a marker)."""
    indent = text[:len(text) - len(text.lstrip(" "))]
    return (indent + " ".join(redact(text).split()))[:LINE_MAX]


def render_bullet(edit: dict[str, Any], line: int | None = None) -> str:
    """The spec 9.4 bullet of one applied edit; ``line`` is the doc line at the starting HEAD
    (default: the edit's ``start_line``). An ``add`` edit's kind is ``edit["gap_kind"]``
    (``name`` when unset): ``run`` fills it from the ``gaps.json`` gap whose name is the edit's
    ``subject`` (the gap agent's ``subject`` is the name added), since the gap edit does not
    carry the gap's kind. A ``create`` edit (the README, phase B spec 8) reads its counts from
    ``edit["statements"]``, ``edit["sheets"]`` (the valid sheets of ``sheets.json``) and
    ``edit["removed"]`` (``applied.json`` ``readme``), which ``run`` fills in."""
    where = f"{edit['doc']}:{line if line is not None else edit['start_line']}"
    kind = edit["type"]
    claim = str(edit.get("claim") or "")
    evidence = [str(e) for e in edit.get("evidence") or []]
    subject = str(edit.get("subject") or "")
    if kind == "correct":
        text = f"correct {claim} ({', '.join(evidence)})"
    elif kind == "remove":
        text = f"remove {claim} ({subject} not in source)"
    elif kind == "anchor":
        text = f"anchor {subject} ({evidence[0] if evidence else ''})"
    elif kind == "notice":
        text = "notice unverified block (1st notice)"
    elif kind == "escalate":
        text = "escalate unverified notice (2nd notice)"
    elif kind == "clear":
        text = f"clear unverified notice ({claim})"
    elif kind == "unverified":
        found = re.search(r"since (\S+)", claim)
        since = found.group(1) if found else claim
        text = f"remove unverified block (3rd notice, unchanged since {since})"
    elif kind == "add":
        text = (f"add {edit.get('gap_kind') or 'name'} {subject.strip().strip('`').strip()} "
                f"({evidence[0] if evidence else ''})")
    elif kind == "create":
        text = (f"create readme ({int(edit.get('statements') or 0)} statements from "
                f"{int(edit.get('sheets') or 0)} sheets, {int(edit.get('removed') or 0)} removed)")
    else:
        raise StepError(f"edit {edit.get('id')} has the unknown type {kind!r}", EXIT_COMMIT)
    return _line(f"- {where} {text}")


def human_line(entry: dict[str, Any]) -> str:
    """One redacted `- doc:line kind: text (evidence)` line of a Human-decision entry; an entry
    with no doc (``no-home``, whose place is its evidence) has no ``doc:line``."""
    evidence = ", ".join(str(e) for e in entry.get("evidence") or [])
    tail = f" ({evidence})" if evidence else ""
    where = f"{entry['doc']}:{entry['line']} " if entry.get("doc") else ""
    return _line(f"- {where}{entry['kind']}: {entry['text']}{tail}")


def render_message(kind: str, bullets: list[str], *, run_id: str, base: str, scope: str,
                   unchecked: tuple[int, int, int], human: list[dict[str, Any]] | None,
                   trailers: list[str]) -> str:
    """One commit message: subject, the four ``Drift-`` lines, the bullets (already rendered),
    then, when ``human`` is given, the ``Needs a human decision:`` block, then the trailers.
    Every line is redacted and cut to 160 characters."""
    units, gap_docs, batches = unchecked
    lines = [SUBJECTS[kind], "",
             f"Drift-Run: {run_id}", f"Drift-Base: {base}", f"Drift-Scope: {scope}",
             f"Drift-Unchecked: {units} doc units, {gap_docs} gap docs, {batches} verify batches",
             "", *bullets]
    if human:
        lines += ["", "Needs a human decision:", *(human_line(h) for h in human)]
    if trailers:
        lines += ["", *trailers]
    return "\n".join(_line(x) if x else x for x in lines) + "\n"


def _optional(workdir: Path, name: str) -> Any:
    path = workdir / name
    return read_json(path) if path.is_file() else None


def _need(workdir: Path, name: str) -> Any:
    path = workdir / name
    if not path.is_file():
        raise StepError(f"missing {path}; run the earlier steps first", EXIT_MISSING)
    return read_json(path)


def _first_line(root: Path | None, head: str, doc: str, block_start: int) -> str:
    text = run_git(root, ["show", f"{head}:{doc}"]) if root is not None and head else None
    if text is None:
        return "unverified block"
    lines = text.splitlines()
    return lines[block_start - 1].strip() if 0 < block_start <= len(lines) else "unverified block"


def _written_readme(workdir: Path, root: Path | None) -> str:
    """The README the run wrote: ``README.md`` at ``root`` when it is there, else
    ``readme.json``'s text without the lines of the statements that did not stay."""
    if root is not None and (root / README).is_file():
        return (root / README).read_text(encoding="utf-8", errors="replace")
    readme = _optional(workdir, "readme.json") or {}
    verdicts = _optional(workdir, "verdicts.json") or {}
    kept = {str(s["id"]) for s in readme_accepted(readme, verdicts)}
    gone = {n for s in readme.get("statements", []) if str(s["id"]) not in kept
            for n in range(int(s["start_line"]), int(s.get("end_line", s["start_line"])) + 1)}
    lines = str(readme.get("text") or "").split("\n")
    return "\n".join(line for n, line in enumerate(lines, 1) if n not in gone)


def _span_keys(text: str) -> set[str]:
    """Each inline-code span of ``text`` by ``dd_defindex.norm`` (without a ``$`` prefix or a
    trailing ``()``, also read as a route)."""
    keys: set[str] = set()
    for span in _SPAN.findall(text):
        bare = span.strip().lstrip("$").removesuffix("()")
        if bare:
            keys |= {norm(bare), norm(bare, routes=True)}
    return keys


def collect_human(workdir: Path, root: Path | None = None) -> list[dict[str, Any]]:
    """Every Human-decision entry of the run, sorted by ``(doc, line)`` (source order breaks
    ties), without duplicates on ``(doc, line, kind, text)``.

    Sources, in order: ``edits.json`` ``human`` as it is; ``verify-rejected`` for each edit
    whose verdict is ``reject`` or ``unsure`` (text ``<claim>: <reason>``); ``recheck-failed``
    for each ``applied.json`` revert with that reason; ``no-home`` for ``gaps.json``
    ``no_home`` (doc ``""``, line 0, text ``<kind> <name>``), left out when ``applied.json``
    ``readme`` is set and an inline-code span of the written README names it by
    ``dd_defindex.norm`` (the README is ``README.md`` at ``root``, else ``readme.json``'s text
    without the statements that did not stay); ``readme-rejected`` for each ``verdicts.json``
    ``readme`` verdict ``reject`` or ``unsure`` (doc ``README.md``, the statement's
    ``readme.json`` ``start_line``, a line of the proposed README, and the first line of its
    text with `` (proposed line)`` appended, evidence the reason); ``unverified`` for each
    ``notices.json`` decision with action ``escalate`` (the text is the first line of its
    block, read from the starting HEAD's doc when ``root`` is given)."""
    edits_doc = _need(workdir, "edits.json")
    by_id = {str(e["id"]): e for e in edits_doc.get("edits", [])}
    found: list[dict[str, Any]] = [dict(h) for h in edits_doc.get("human", [])]
    verdicts_doc = _optional(workdir, "verdicts.json") or {}
    verdicts = verdicts_doc.get("verdicts", {})
    for eid in sorted(verdicts):
        verdict, edit = verdicts[eid], by_id.get(eid)
        if edit is not None and verdict.get("verdict") in ("reject", "unsure"):
            found.append({"doc": edit["doc"], "line": int(edit["start_line"]),
                          "kind": "verify-rejected",
                          "text": f"{edit.get('claim', '')}: {verdict.get('reason', '')}",
                          "evidence": list(edit.get("evidence") or [])})
    applied = _optional(workdir, "applied.json") or {}
    for item in applied.get("reverted", []):
        edit = by_id.get(str(item.get("edit")))
        if edit is not None and item.get("reason") == "recheck-failed":
            found.append({"doc": edit["doc"], "line": int(edit["start_line"]),
                          "kind": "recheck-failed", "text": str(edit.get("claim", "")),
                          "evidence": list(edit.get("evidence") or [])})
    named = _span_keys(_written_readme(workdir, root)) if applied.get("readme") else set()
    for name in (_optional(workdir, "gaps.json") or {}).get("no_home", []):
        if norm(str(name["name"]), routes=name["kind"] == "route") in named:
            continue  # the written README documents it
        found.append({"doc": "", "line": 0, "kind": "no-home",
                      "text": f"{name['kind']} {name['name']}",
                      "evidence": [f"{name['file']}:{name['line']}"]})
    statements = {str(s["id"]): s
                  for s in (_optional(workdir, "readme.json") or {}).get("statements", [])}
    readme_verdicts = verdicts_doc.get("readme") or {}
    for sid in sorted(readme_verdicts):
        verdict, statement = readme_verdicts[sid], statements.get(sid)
        if statement is not None and verdict.get("verdict") in ("reject", "unsure"):
            found.append({"doc": README, "line": int(statement["start_line"]),
                          "kind": "readme-rejected",
                          "text": str(statement["text"]).split("\n", 1)[0] + PROPOSED,
                          "evidence": [str(verdict.get("reason", ""))]})
    head = str((_optional(workdir, "preflight.json") or {}).get("head") or "")
    for decision in (_optional(workdir, "notices.json") or {}).get("decisions", []):
        if decision.get("action") == "escalate":
            found.append({"doc": decision["doc"], "line": int(decision["line"]),
                          "kind": "unverified",
                          "text": _first_line(root, head, decision["doc"],
                                              int(decision["block"][0])),
                          "evidence": []})
    seen: set[tuple[str, int, str, str]] = set()
    unique: list[dict[str, Any]] = []
    for entry in found:
        key = (entry["doc"], int(entry["line"]), entry["kind"], entry["text"])
        if key not in seen:
            seen.add(key)
            unique.append(entry)
    unique.sort(key=lambda h: (h["doc"], int(h["line"])))
    return unique


def _count(value: Any) -> int:
    return len(value) if isinstance(value, list) else int(value or 0)


def gap_kind(edit: dict[str, Any], gaps: list[dict[str, Any]]) -> str:
    """Kind of the gap an ``add`` edit documents: the ``gaps.json`` gap whose name equals the
    edit's ``subject`` (backticks and spaces stripped, both sides ``dd_defindex.norm``ed),
    preferring the one targeting the edit's doc. No match raises ``StepError``."""
    want = norm(str(edit.get("subject") or "").strip().strip("`").strip())
    same = [g for g in gaps if norm(str(g.get("name") or "")) == want]
    same.sort(key=lambda g: g.get("target_doc") != edit["doc"])
    if not same:
        raise StepError(f"add edit {edit['id']} names {edit.get('subject')!r}, which matches no "
                        "gap in gaps.json", EXIT_MISSING)
    return str(same[0]["kind"])



def run(root: Path, workdir: Path, branch: str, run_id: str, base: str, scope: str,
        trailers: list[str]) -> dict[str, Any]:
    """Make the corrections and additions commits on ``branch``; write ``commits.json``
    ``{"branch", "commits": [{"sha", "kind"}]}`` and ``commit-msg-<kind>.txt``.

    Corrections hold the applied review and notice edits and their link updates, additions the
    applied gap edits and the README's ``create`` edit (``README.md`` staged by path, so the
    additions commit is made for it even when it is the only edit; its bullet's counts come
    from ``sheets.json`` and ``applied.json`` ``readme``). The edits are already in the working
    tree, so a doc cannot be split: it is staged in the first commit that touches it, and a doc
    with both kinds of edits lands in the corrections commit, so a doc carrying both kinds has
    its additions in the corrections commit (the additions commit is then made with
    ``--allow-empty`` when no doc is left to stage, to keep its bullets). If the second commit
    fails, ``commits.json`` already lists the first. Bullets are ordered by ``(doc,
    start_line, id)`` with a link update as an indented sub-bullet under its edit. With no
    applied edit there is no branch. The human list goes on the last commit made."""
    edits_doc = _need(workdir, "edits.json")
    applied = _need(workdir, "applied.json")
    done = set(applied.get("applied", []))
    links: list[dict[str, Any]] = [u for u in applied.get("link_updates", [])
                                   if u.get("new") is not None]
    gaps = (_optional(workdir, "gaps.json") or {}).get("gaps", [])
    sheets = len((_optional(workdir, "sheets.json") or {}).get("sheets", {}))
    removed = int((applied.get("readme") or {}).get("removed") or 0)
    groups: dict[str, list[dict[str, Any]]] = {k: [] for k in KIND_ORDER}
    for edit in edits_doc["edits"]:
        if edit["id"] in done:
            groups["additions" if edit.get("source") in ADDITION_SOURCES
                   else "corrections"].append(edit)
    kinds = [k for k in KIND_ORDER if groups[k]]
    if not kinds:
        result: dict[str, Any] = {"branch": None, "commits": []}
        write_json(workdir / "commits.json", result)
        return result
    if (run_git(root, ["rev-parse", "HEAD"]) or "").strip() != base:
        raise StepError(
            f"HEAD moved during the run (expected {base}); no branch was created", EXIT_COMMIT)
    unchecked = (_count(edits_doc.get("unchecked_units")),
                 _count(edits_doc.get("unchecked_gap_docs")),
                 _count(edits_doc.get("unverified_batches")))
    human = collect_human(workdir, root)
    if run_git(root, ["switch", "-c", branch]) is None:
        raise StepError(f"git switch -c {branch} failed after the edits were applied",
                        EXIT_COMMIT)
    here = f"you are on branch {branch}"
    commits: list[dict[str, str]] = []
    staged: set[str] = set()
    for n, kind in enumerate(kinds):
        group = sorted(groups[kind], key=lambda e: (e["doc"], int(e["start_line"]), e["id"]))
        bullets: list[str] = []
        docs: set[str] = set()
        for edit in group:
            if edit["type"] == "add":
                edit = {**edit, "gap_kind": gap_kind(edit, gaps)}
            elif edit["type"] == "create":
                edit = {**edit, "sheets": sheets, "removed": removed}
            bullets.append(render_bullet(edit))
            docs.add(edit["doc"])
            for link in sorted((u for u in links if u["edit"] == edit["id"]),
                               key=lambda u: (u["doc"], u["line"], u["old"])):
                old, new = str(link["old"]).lstrip("#"), str(link["new"]).lstrip("#")
                bullets.append(f"  - {link['doc']}:{link['line']} link #{old} -> #{new}")
                docs.add(link["doc"])
        message = render_message(kind, bullets, run_id=run_id, base=base, scope=scope,
                                 unchecked=unchecked,
                                 human=human if n == len(kinds) - 1 else None,
                                 trailers=trailers)
        path = workdir / f"commit-msg-{kind}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(message.encode("utf-8"))
        todo = sorted(docs - staged)
        empty = ["--allow-empty"] if kind == "additions" and not todo else []
        failure = ""
        if todo and run_git(root, ["--literal-pathspecs", "add", "--", *todo]) is None:
            failure = f"git add failed; {here} with the edits unstaged"
        elif run_git(root, ["commit", *empty, "--cleanup=verbatim", "-F", str(path)]) is None:
            failure = f"git commit failed; {here} with the edits staged"
        sha = None if failure else run_git(root, ["rev-parse", "HEAD"])
        if sha is None:
            write_json(workdir / "commits.json", {"branch": branch, "commits": commits})
            raise StepError(failure or f"git rev-parse failed after the commit; {here}",
                            EXIT_COMMIT)
        staged |= docs
        commits.append({"sha": sha.strip(), "kind": kind})
    result = {"branch": branch, "commits": commits}
    write_json(workdir / "commits.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Commit applied drift fixes.")
    parser.add_argument("repo", type=Path)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--base", help="the starting HEAD (default: preflight.json head)")
    parser.add_argument("--scope", required=True)
    parser.add_argument("--trailer", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        base = args.base or str(_need(args.workdir, "preflight.json")["head"])
        run(args.repo, args.workdir, args.branch, args.run_id, base, args.scope, args.trailer)
    except StepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
