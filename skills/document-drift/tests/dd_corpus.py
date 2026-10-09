"""Shared helpers for the corpus and golden tests: replay a fixture ready for a run, and map a
planted item or decoy to the outcome the pipeline gave it.

An outcome is ``replace:<new text>``, ``delete`` or ``unlink`` (the verb of the provable hunk
that carries the finding, as its first finding or as an ``also`` entry), ``human:<kind>``, or
``none`` (no finding on the line, or only ``summary-only`` ones). Ruling R53 adds two
expectations judged on ``tokens.json``: ``excluded`` (the doc is never scanned: absent from
``docs`` and without any finding) and ``no-token`` (the doc is scanned and the extractor gives
no token on that line).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from dd_make_history import CORPUS_ROOT, replay_fixture

FIXTURES: tuple[str, ...] = ("py-service", "ts-web", "go-cli")
EDIT_VERBS: tuple[str, ...] = ("replace", "delete", "unlink")
TOKEN_KINDS: tuple[str, ...] = ("path", "anchor", "script", "version", "tree")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def prepare_fixture(name: str, dest: Path) -> Path:
    """Replay ``name`` into ``dest`` with local settings that keep the working tree clean.

    The replay itself pins ``core.autocrlf=false`` per command; a later ``git status`` would
    otherwise read the machine's global setting, so it is pinned in the repository too, with
    a fixed identity for the run's own commit.
    """
    repo = replay_fixture(name, dest)
    for key, value in (("core.autocrlf", "false"), ("user.name", "Fixture"),
                       ("user.email", "fixture@example.com"), ("commit.gpgsign", "false")):
        _git(repo, "config", key, value)
    return repo


def load_planted(name: str) -> dict[str, list[dict[str, Any]]]:
    data: dict[str, list[dict[str, Any]]] = json.loads(
        (CORPUS_ROOT / name / "planted.json").read_text(encoding="utf-8"))
    return data


def is_edit(expect: str) -> bool:
    return expect.split(":", 1)[0] in EDIT_VERBS


def finding_outcome(finding: dict[str, Any], hunks: list[dict[str, Any]]) -> str:
    cls = finding["class"]
    if cls == "summary-only":
        return "none"
    if cls == "human":
        return f"human:{finding['human_kind']}"
    for hunk in hunks:
        parts = [{"finding_id": hunk["finding_id"], "verb": hunk["verb"],
                  "new_text": hunk.get("new_text")}, *hunk.get("also", [])]
        for part in parts:
            if part["finding_id"] == finding["id"]:
                verb = str(part["verb"])
                return f"replace:{part['new_text']}" if verb == "replace" else verb
    return f"{cls}-without-hunk"


def outcome_for(item: dict[str, Any], findings: list[dict[str, Any]],
                hunks: list[dict[str, Any]]) -> str:
    """The outcome of the findings on the item's doc and line (and kind and token text, when
    the item names them)."""
    found = [f for f in findings if f["doc"] == item["doc"] and f["line"] == item["line"]
             and all(f[key] == item[key] for key in ("kind", "text") if key in item)]
    outcomes = {o for f in found if (o := finding_outcome(f, hunks)) != "none"}
    return " | ".join(sorted(outcomes)) if outcomes else "none"


def evaluate(item: dict[str, Any], tokens: dict[str, Any], findings: list[dict[str, Any]],
             hunks: list[dict[str, Any]]) -> str:
    """The item's outcome in the vocabulary of its own expectation (ruling R53)."""
    doc = item["doc"]
    if item["expect"] == "excluded":
        if doc in tokens["docs"]:
            return f"scanned:{len(tokens['docs'][doc])} tokens"
        if any(f["doc"] == doc for f in findings):
            return "excluded-but-has-findings"
        return "excluded"
    if item["expect"] == "no-token":
        if doc not in tokens["docs"]:
            return "doc-not-scanned"
        on_line = sorted(f"{t['kind']}:{t['text']}" for t in tokens["docs"][doc]
                         if t["line"] == item["line"])
        return "no-token" if not on_line else "tokens:" + ",".join(on_line)
    return outcome_for(item, findings, hunks)
