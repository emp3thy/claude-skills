"""Commit the applied edits on a new branch with the owner-parsed message grammar (spec 7.4).

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


def render_message(
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


def run(
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
    message = render_message(findings, hunks, applied["applied"], run_id=run_id, base=base,
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
        run(args.repo, args.workdir, args.branch, args.run_id, args.scope, args.trailer)
    except StepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
