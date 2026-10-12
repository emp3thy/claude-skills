"""Commit the applied edits on a new branch with the owner-parsed message grammar.

Phase A (spec 9.4): ``run``, ``render_message``, ``render_bullet`` and ``collect_human`` make the
corrections and additions commits (see ``run``). The phase 1 hunk functions below
(``run_hunks``, ``render_message_hunks``, ``render_bullets``, ``render_human``) stay for
``dd_run`` and ``dd_summary`` until they move to the edit pipeline.

Display (ruling R51): a ``script`` finding is shown as its invocation (``make lint``,
``npm run lint``, ``yarn lint``, ``pnpm lint``, ``just lint``, ``task lint``) in body bullets and
human statements; a ``tree`` replace bullet shows full paths on both sides, the new one being
the finding's path with its last segment replaced by the hunk's new text.

Final-review rulings: a ``large-deletion`` statement names its unit in words ("a list item",
"a table row", "a fence line", "a tree line", "a paragraph", "a heading"; R66), the
``heading-reference`` statement says a heading names the token (R62), and ``render_bullets`` is
shared with the check-mode summary (R66).
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
from dd_redaction import redact

SUBJECT = "docs(drift): provable fixes"


def _pos(finding: dict[str, Any]) -> tuple[str, int, int]:
    return (str(finding.get("doc", "")), int(finding.get("line", 0)), int(finding.get("col", 0)))


SCRIPT_INVOCATION: dict[str, str] = {
    "make": "make {}", "npm": "npm run {}", "yarn": "yarn {}", "pnpm": "pnpm {}",
    "just": "just {}", "task": "task {}",
}


def _tick(text: str) -> str:
    return f"`{redact(text)}`"


def _shown(finding: dict[str, Any]) -> str:
    """The token as a reader recognises it: a script as its invocation (ruling R51)."""
    text = str(finding.get("text", ""))
    if finding.get("kind") == "script":
        template = SCRIPT_INVOCATION.get(str(finding.get("script_tool") or ""))
        if template is not None:
            return template.format(text)
    return text


def tree_new_path(text: str, new_text: str) -> str:
    """A tree entry's path with its own last segment (and trailing ``/``) replaced."""
    trail = "/" if text.endswith("/") else ""
    own = text.rstrip("/").rsplit("/", 1)[-1] + trail
    return text[: len(text) - len(own)] + new_text


UNIT_WORDS: dict[str, str] = {
    "list_item": "a list item", "table_row": "a table row", "table_header": "a table row",
    "fence": "a fence line", "tree": "a tree line", "paragraph": "a paragraph",
    "heading": "a heading",
}


def _statement(finding: dict[str, Any]) -> str:
    token = _tick(_shown(finding))
    kind = finding.get("human_kind")
    if kind == "ambiguous-rename":
        return f"{token} was renamed or moved and no single new name is provable"
    if kind == "large-deletion":
        block = str((finding.get("block") or {}).get("kind") or "")
        return (f"{token} no longer exists and removing it would remove "
                f"{UNIT_WORDS.get(block, 'a block')}")
    if kind == "heading-reference":
        return f"{token} is named in a heading; changing it would break links to that heading"
    if kind == "prose-mention":
        return f"{token} no longer exists and is mentioned in running prose"
    if kind == "never-edit-section":
        path = finding.get("heading_path") or []
        heading = redact(str(path[-1])) if path else ""
        return f"{token} no longer exists, in a section headed '{heading}'"
    if kind == "generated-region":
        return f"{token} no longer exists inside a generated region; regenerate it"
    if kind == "recheck-failed":
        reason = redact(str(finding.get("recheck_reason") or "unknown"))
        return f"the proposed edit for {token} did not pass the re-check ({reason})"
    return f"{token} needs a human decision"


def render_human(findings: list[dict[str, Any]]) -> str:
    """The 'Needs a human decision' section (no trailing blank line); empty when none."""
    humans = sorted(
        (f for f in findings if f.get("class") == "human" and not f.get("superseded_by")),
        key=_pos,
    )
    if not humans:
        return ""
    lines = ["Needs a human decision:"]
    for f in humans:
        doc, line, _ = _pos(f)
        evidence = redact(str(f.get("evidence") or "")) or "none"
        lines.append(f"- {redact(doc)}:{line} [{f.get('human_kind')}] {_statement(f)}")
        lines.append(f"  evidence: {evidence}")
    return "\n".join(lines) + "\n"


def _bullet(finding: dict[str, Any], verb: str, new_text: str | None, reason: str) -> str:
    where = f"{redact(str(finding['doc']))}:{finding['line']}"
    old = _tick(_shown(finding))
    why = f"({redact(reason)})"
    if verb == "replace":
        new = new_text or ""
        if finding.get("kind") == "tree":
            new = tree_new_path(str(finding.get("text", "")), new)
        return f"- {where} replace {old} -> {_tick(new)} {why}"
    return f"- {where} {verb} {old} {why}"


def render_bullets(findings: list[dict[str, Any]], hunks: list[dict[str, Any]],
                   only: set[str] | None = None, missing_code: int = EXIT_COMMIT) -> list[str]:
    """One bullet per finding of each hunk (of the hunk ids in ``only``, when given), ordered
    by doc, line and column. A hunk naming a finding that is missing from ``findings`` raises
    ``StepError`` with ``missing_code`` (R48: never skipped)."""
    by_id = {f["id"]: f for f in findings if "id" in f}
    entries: list[tuple[tuple[str, int, int], str]] = []
    for hunk in hunks:
        if only is not None and hunk["id"] not in only:
            continue
        parts = [{"finding_id": hunk["finding_id"], "verb": hunk["verb"],
                  "new_text": hunk.get("new_text"), "reason": hunk.get("reason", "")},
                 *hunk.get("also", [])]
        for part in parts:
            finding = by_id.get(part["finding_id"])
            if finding is None:
                raise StepError(
                    f"applied hunk {hunk['id']} names finding {part['finding_id']} "
                    "which is missing from findings.json", missing_code)
            entries.append((_pos(finding), _bullet(
                finding, part["verb"], part.get("new_text"), part.get("reason", ""))))
    entries.sort(key=lambda e: e[0])
    return [b for _, b in entries]


def render_message_hunks(
    findings: list[dict[str, Any]],
    hunks: list[dict[str, Any]],
    applied: list[str],
    *,
    run_id: str,
    base: str,
    scope: str,
    trailers: list[str],
) -> str:
    """The full commit message for the applied hunks."""
    blocks = [
        SUBJECT,
        f"Drift-Run: {run_id}\nDrift-Base: {base}\nDrift-Scope: {redact(scope)}",
        "\n".join(render_bullets(findings, hunks, set(applied))),
    ]
    human = render_human(findings)
    if human:
        blocks.append(human.rstrip("\n"))
    if trailers:
        blocks.append("\n".join(redact(t) for t in trailers))
    return "\n\n".join(blocks) + "\n"


def run_hunks(
    root: Path,
    workdir: Path,
    branch: str,
    run_id: str,
    scope: str,
    trailers: list[str],
) -> dict[str, Any]:
    """Create ``branch`` from HEAD, commit the edited docs; write ``commits.json``."""
    for name in ("applied.json", "findings.json", "hunks-provable.json", "preflight.json"):
        if not (workdir / name).is_file():
            raise StepError(f"missing {workdir / name}; run the earlier steps first", EXIT_MISSING)
    applied = read_json(workdir / "applied.json")
    if not applied.get("applied"):
        result: dict[str, Any] = {"branch": None, "commits": []}
        write_json(workdir / "commits.json", result)
        return result
    findings = read_json(workdir / "findings.json")["findings"]
    hunks = read_json(workdir / "hunks-provable.json")["hunks"]
    base = read_json(workdir / "preflight.json")["head"]
    message = render_message_hunks(findings, hunks, applied["applied"], run_id=run_id, base=base,
                             scope=scope, trailers=trailers)
    msg_path = workdir / "commit-msg.txt"
    msg_path.parent.mkdir(parents=True, exist_ok=True)
    msg_path.write_bytes(message.encode("utf-8"))
    docs: list[str] = applied["docs"]
    current = run_git(root, ["rev-parse", "HEAD"])
    if current is None or current.strip() != base:
        raise StepError(
            f"HEAD moved during the run (expected {base}); no branch was created", EXIT_COMMIT)
    if run_git(root, ["switch", "-c", branch]) is None:
        raise StepError(f"git switch -c {branch} failed after the edits were applied",
                        EXIT_COMMIT)
    here = f"you are on branch {branch}"
    if run_git(root, ["--literal-pathspecs", "add", "--", *docs]) is None:
        raise StepError(f"git add failed; {here} with the edits unstaged", EXIT_COMMIT)
    if run_git(root, ["commit", "--cleanup=verbatim", "-F", str(msg_path)]) is None:
        raise StepError(f"git commit failed; {here} with the edits staged", EXIT_COMMIT)
    sha = run_git(root, ["rev-parse", "HEAD"])
    if sha is None:
        raise StepError(f"git rev-parse failed after the commit; you are on branch {branch}",
                        EXIT_COMMIT)
    result = {"branch": branch, "commits": [sha.strip()]}
    write_json(workdir / "commits.json", result)
    return result


# ------------------------------------------------------------------ phase A (spec 9.4)

LINE_MAX = 160
SUBJECTS = {"corrections": "docs(drift): correct stale docs",
            "additions": "docs(drift): document missing surface"}
KIND_ORDER = ("corrections", "additions")


def _line(text: str) -> str:
    """One redacted line of at most ``LINE_MAX`` characters (cut without a marker)."""
    indent = text[:len(text) - len(text.lstrip(" "))]
    return (indent + " ".join(redact(text).split()))[:LINE_MAX]


def render_bullet(edit: dict[str, Any], line: int | None = None) -> str:
    """The spec 9.4 bullet of one applied edit; ``line`` is the doc line at the starting HEAD
    (default: the edit's ``start_line``). An ``add`` edit's kind is ``edit["gap_kind"]``
    (``name`` when unset): ``run`` fills it from the ``gaps.json`` gap whose name is the edit's
    ``subject`` (the gap agent's ``subject`` is the name added), since the gap edit does not
    carry the gap's kind."""
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
        text = (f"add {edit.get('gap_kind') or 'name'} {subject} "
                f"({evidence[0] if evidence else ''})")
    else:
        raise StepError(f"edit {edit.get('id')} has the unknown type {kind!r}", EXIT_COMMIT)
    return _line(f"- {where} {text}")


def _human_line(entry: dict[str, Any]) -> str:
    evidence = ", ".join(str(e) for e in entry.get("evidence") or [])
    tail = f" ({evidence})" if evidence else ""
    return _line(f"- {entry['doc']}:{entry['line']} {entry['kind']}: {entry['text']}{tail}")


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
        lines += ["", "Needs a human decision:", *(_human_line(h) for h in human)]
    if trailers:
        lines += ["", *trailers]
    return "\n".join(x[:LINE_MAX] if x.startswith("  ") else _line(x) if x else x
                     for x in lines) + "\n"


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


def collect_human(workdir: Path, root: Path | None = None) -> list[dict[str, Any]]:
    """Every Human-decision entry of the run, sorted by ``(doc, line)`` (source order breaks
    ties), without duplicates on ``(doc, line, kind, text)``.

    Sources, in order: ``edits.json`` ``human`` as it is; ``verify-rejected`` for each edit
    whose verdict is ``reject`` or ``unsure`` (text ``<claim>: <reason>``); ``recheck-failed``
    for each ``applied.json`` revert with that reason; ``no-home`` for ``gaps.json``
    ``no_home`` (doc ``""``, line 0, text ``<kind> <name>``); ``unverified`` for each
    ``notices.json`` decision with action ``escalate`` (the text is the first line of its
    block, read from the starting HEAD's doc when ``root`` is given)."""
    edits_doc = _need(workdir, "edits.json")
    by_id = {str(e["id"]): e for e in edits_doc.get("edits", [])}
    found: list[dict[str, Any]] = [dict(h) for h in edits_doc.get("human", [])]
    verdicts = (_optional(workdir, "verdicts.json") or {}).get("verdicts", {})
    for eid in sorted(verdicts):
        verdict, edit = verdicts[eid], by_id.get(eid)
        if edit is not None and verdict.get("verdict") in ("reject", "unsure"):
            found.append({"doc": edit["doc"], "line": int(edit["start_line"]),
                          "kind": "verify-rejected",
                          "text": f"{edit.get('claim', '')}: {verdict.get('reason', '')}",
                          "evidence": list(edit.get("evidence") or [])})
    for item in (_optional(workdir, "applied.json") or {}).get("reverted", []):
        edit = by_id.get(str(item.get("edit")))
        if edit is not None and item.get("reason") == "recheck-failed":
            found.append({"doc": edit["doc"], "line": int(edit["start_line"]),
                          "kind": "recheck-failed", "text": str(edit.get("claim", "")),
                          "evidence": list(edit.get("evidence") or [])})
    for name in (_optional(workdir, "gaps.json") or {}).get("no_home", []):
        found.append({"doc": "", "line": 0, "kind": "no-home",
                      "text": f"{name['kind']} {name['name']}",
                      "evidence": [f"{name['file']}:{name['line']}"]})
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


def _gap_kind(edit: dict[str, Any], gaps: list[dict[str, Any]]) -> str | None:
    """Kind of the gap an ``add`` edit documents: the ``gaps.json`` gap whose name is the
    edit's ``subject``, preferring the one targeting the edit's doc."""
    same = [g for g in gaps if g.get("name") == edit.get("subject")]
    same.sort(key=lambda g: g.get("target_doc") != edit["doc"])
    return str(same[0]["kind"]) if same else None


def run(root: Path, workdir: Path, branch: str, run_id: str, base: str, scope: str,
        trailers: list[str]) -> dict[str, Any]:
    """Make the corrections and additions commits on ``branch``; write ``commits.json``
    ``{"branch", "commits": [{"sha", "kind"}]}`` and ``commit-msg-<kind>.txt``.

    Corrections hold the applied review and notice edits and their link updates, additions the
    applied gap edits. The edits are already in the working tree, so a doc cannot be split: it
    is staged in the first commit that touches it, and a doc with both kinds of edits lands in
    the corrections commit (the additions commit is then made with ``--allow-empty`` if nothing
    else is left to stage, to keep its bullets). Bullets are ordered by ``(doc, start_line,
    id)`` with a link update as an indented sub-bullet under its edit. With no applied edit
    there is no branch. The human list goes on the last commit made."""
    edits_doc = _need(workdir, "edits.json")
    applied = _need(workdir, "applied.json")
    done = set(applied.get("applied", []))
    links: list[dict[str, Any]] = [u for u in applied.get("link_updates", [])
                                   if u.get("new") is not None]
    gaps = (_optional(workdir, "gaps.json") or {}).get("gaps", [])
    groups: dict[str, list[dict[str, Any]]] = {k: [] for k in KIND_ORDER}
    for edit in edits_doc["edits"]:
        if edit["id"] in done:
            groups["additions" if edit.get("source") == "gap" else "corrections"].append(edit)
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
                edit = {**edit, "gap_kind": _gap_kind(edit, gaps)}
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
        if todo and run_git(root, ["--literal-pathspecs", "add", "--", *todo]) is None:
            raise StepError(f"git add failed; {here} with the edits unstaged", EXIT_COMMIT)
        staged |= docs
        if run_git(root, ["commit", "--allow-empty", "--cleanup=verbatim", "-F",
                          str(path)]) is None:
            raise StepError(f"git commit failed; {here} with the edits staged", EXIT_COMMIT)
        sha = run_git(root, ["rev-parse", "HEAD"])
        if sha is None:
            raise StepError(f"git rev-parse failed after the commit; {here}", EXIT_COMMIT)
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
    parser.add_argument("--scope", default="all")
    parser.add_argument("--trailer", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        run_hunks(args.repo, args.workdir, args.branch, args.run_id, args.scope, args.trailer)
    except StepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
