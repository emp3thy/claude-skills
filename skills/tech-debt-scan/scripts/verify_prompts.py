"""Select the candidates worth a verifier's time and render their prompts (spec 4.8).

Reads ``candidates.json``, ``inventory.json`` and ``coupling.json`` from
``--workdir`` and ``.tech-debt.yaml`` from the repository root. Writes
``verify-plan.json`` and ``prompts/verify-<nn>.md``; SKILL.md (phase 3)
dispatches one read-only agent per batch and stores its reply at the plan's
``output`` path.

Budget rule: provisional priority (the 4.9 formula at tier B) ranks every
unverified candidate; the top ``max(top_multiple x N, min_candidates)`` plus
every severity-5 and every ``always_families`` candidate are selected, capped
at ``max_candidates``; tier A candidates (rules, tool facts) are never sent;
the rest are listed as ``unverified``. Batches of ``batch_size`` group
candidates by primary file. Each prompt carries the cited spans with
``context_lines`` of context, the change-coupled files, approximate referrers,
the family's verification questions, the family block's own traps and the
repository's traps; every line of repository text is redacted. The verifier
prompt shares no text with the scout prompts beyond the read-only rule and the
family's trap list, restated here on purpose so the verifier can match a known
non-debt shape and reject with ``trap_matched``.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from pathlib import Path
from typing import Any, Final

from categories import FAMILY_BLOCKS
from config import ConfigError, load_config
from evidence import priority_terms
from inventory import write_json
from redaction import redact
from reference_graph import GraphFile, build_reference_graph, file_stem

SCHEMA_VERSION: Final[int] = 2
VERDICT_VALUES: Final[tuple[str, ...]] = ("confirm", "downgrade", "reject", "refer")
# The exploration allowance is prose in both places it appears (the header below
# and the verdict contract), so the cap is spelled as a word, not a numeral.
EXPLORATION_FILES: Final[str] = "three"
# The two trap sections a verifier prompt carries: the family block's own known
# non-debt shapes (spec 2.3, the same list the scout prompt shows) and the traps
# this repository recorded in its config. The family list is rendered first: it is
# the general rule, the repository's is the local exception to it.
FAMILY_TRAPS_HEADER: Final[str] = (
    "known non-debt shapes for this family (a match is a reject with trap_matched):")
REPO_TRAPS_HEADER: Final[str] = (
    "traps recorded for this repository (a match is a reject with trap_matched):")
# `_reference_edges` returns None when the graph cannot be built. `render_verify_prompt`
# treats `edges=None` as "not supplied, build one", so passing that None through would
# rebuild (and re-read every source file) once per batch. build_verify_plan substitutes
# this sentinel instead: an empty edge list that renders "not computed" exactly as a
# failure does, without a second attempt.
GRAPH_FAILED: Final[list[tuple[str, str]]] = []

VERDICT_CONTRACT: Final[str] = """\
Reply with one JSON array, one object per candidate, exactly these keys:

[
  {
    "fingerprint": "<as given>",
    "verdict": "confirm" | "downgrade" | "reject" | "refer",
    "proof": "<=150 words citing line numbers",
    "severity": 1-5,
    "effort": "S" | "M" | "L",
    "trap_matched": "<the trap note you matched, or null>",
    "checked": ["<what you checked, e.g. reflection, string-dispatch>"],
    "opened": ["<every further file you opened, at most three>"]
  }
]

confirm: the debt is real as described. downgrade: real but less severe (give the
severity). reject: not debt (say why; a matched trap goes in trap_matched).
refer: you could not decide from the code; a human must look."""

VERDICT_SCHEMA: Final[dict[str, Any]] = {
    "type": "array",
    "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["fingerprint", "verdict", "proof", "severity", "effort", "trap_matched",
                     "checked", "opened"],
        "properties": {
            "fingerprint": {"type": "string"},
            "verdict": {"type": "string", "enum": list(VERDICT_VALUES)},
            "proof": {"type": "string"},
            "severity": {"type": "integer", "minimum": 1, "maximum": 5},
            "effort": {"type": "string", "enum": ["S", "M", "L"]},
            "trap_matched": {"type": ["string", "null"]},
            "checked": {"type": "array", "items": {"type": "string"}},
            "opened": {"type": "array", "items": {"type": "string"}},
        },
    },
}


def _primary(cand: dict[str, Any]) -> dict[str, Any]:
    """The first evidence span: its file drives batching, coupling and the referrer list."""
    primary: dict[str, Any] = cand["evidence"][0]
    return primary


# --- budget rule ------------------------------------------------------------------------


def _pool_maxima(pool: list[dict[str, Any]]) -> dict[str, float | int]:
    """Hotspot, coupling and fan-in maxima over the candidate pool itself.

    Unit maxima let a raw ``coupling_degree`` (which can run into the tens)
    dominate the provisional priority over severity; normalising against the
    pool's own scale keeps the terms comparable. Each maximum is 0 when the
    pool is empty or every value is falsy or null, and ``priority_terms``
    already yields 0 for a zero maximum. Fan-in counts int values only.
    """
    signals = [c.get("signals") or {} for c in pool]
    hotspot = max((float(s.get("hotspot_score") or 0.0) for s in signals), default=0.0)
    coupling = max((int(s.get("coupling_degree") or 0) for s in signals), default=0)
    fan_in = max(
        (int(s["fan_in_approx"]) for s in signals if isinstance(s.get("fan_in_approx"), int)),
        default=0,
    )
    return {"hotspot": hotspot, "coupling": coupling, "fan_in": fan_in}


def select_candidates(
    candidates: list[dict[str, Any]], config: dict[str, Any], top: int
) -> tuple[list[dict[str, Any]], list[str]]:
    """(selected in priority order, unverified fingerprints) per the 4.8 budget rule.

    The provisional ranking normalises H, C and F against the candidate
    pool's own maxima (``_pool_maxima``), not the repository's real maxima —
    those belong to ``rank.py``, which scores the verified findings. Ranking
    against the pool's own scale keeps a large raw signal (e.g. a
    ``coupling_degree`` of 12) from outweighing severity in this provisional
    order.
    """
    vcfg = config["verifier"]
    rcfg = config["ranking"]
    pool = [c for c in candidates if c.get("tier") is None]
    maxima = _pool_maxima(pool)
    provisional = {
        c["fingerprint"]: priority_terms(
            c, maxima, rcfg["weights"], rcfg["tractability"],
            tier="B", fan_in_mode="import-lines",
        )["priority"]
        for c in pool
    }
    pool.sort(key=lambda c: (-provisional[c["fingerprint"]], c["fingerprint"]))
    n = max(int(vcfg["top_multiple"]) * int(top), int(vcfg["min_candidates"]))
    always_families = {str(f) for f in vcfg["always_families"]}
    min_severity = int(vcfg["always_min_severity"])
    always = {
        c["fingerprint"] for c in pool
        if int(c["severity"]) >= min_severity or c["family"] in always_families
    }
    chosen = pool[:n]
    chosen += [c for c in pool[n:] if c["fingerprint"] in always]
    chosen = chosen[: int(vcfg["max_candidates"])]
    selected_fps = {c["fingerprint"] for c in chosen}
    unverified = [c["fingerprint"] for c in pool if c["fingerprint"] not in selected_fps]
    return chosen, unverified


def build_batches(selected: list[dict[str, Any]], batch_size: int) -> list[list[dict[str, Any]]]:
    """Chunk the selection into batches of ``batch_size``, candidates on one file together."""
    order = sorted(selected, key=lambda c: (_primary(c)["file"], c["fingerprint"]))
    return [order[i:i + batch_size] for i in range(0, len(order), batch_size)]


# --- prompt rendering -------------------------------------------------------------------


def _span(root: Path, ev: dict[str, Any], context: int) -> str:
    """The cited lines with ``context`` lines either side, numbered, cited lines marked ``>``."""
    path = root / ev["file"]
    try:
        lines = path.read_bytes().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return f"{ev['file']}: unreadable"
    start, end = int(ev["line_start"]), int(ev["line_end"])
    lo, hi = max(1, start - context), min(len(lines), end + context)
    out = [f"{ev['file']}:{start}-{end}"]
    for number in range(lo, hi + 1):
        marker = ">" if start <= number <= end else " "
        out.append(f"{marker}{number:6d} | {redact(lines[number - 1])}")
    return "\n".join(out)


def _coupled(coupling: dict[str, Any], file: str) -> list[str]:
    """Every change-coupled partner of ``file``, with its shared-commit count and ratio."""
    out = []
    for pair in coupling.get("pairs", []):
        if pair.get("a") == file:
            out.append(f"{pair['b']} shared={pair['shared_commits']} ratio={pair['ratio']}")
        elif pair.get("b") == file:
            out.append(f"{pair['a']} shared={pair['shared_commits']} ratio={pair['ratio']}")
    return sorted(redact(entry) for entry in out)


def _reference_edges(
    root: Path, inventory: dict[str, Any], config: dict[str, Any]
) -> list[tuple[str, str]] | None:
    """The stem graph's (referrer, referenced) edges, or None when it could not be built.

    Built once per plan by ``build_verify_plan`` and passed down to every prompt:
    the graph reads every inventory file, so building it per batch re-read the
    whole repository once for each one. Only the classes the graph uses are read
    — ``build_reference_graph`` takes source files as targets and source or tests
    files as referrers — and a file the inventory's size guard marked
    ``skipped_large`` is never read here either.
    """
    try:
        graph_files = []
        for entry in inventory.get("files", []):
            path = root / str(entry["path"])
            if entry.get("skipped_large") or entry.get("path_class") not in ("source", "tests"):
                continue
            if not path.is_file():
                continue
            graph_files.append(GraphFile(
                str(entry["path"]), str(entry.get("language") or ""), str(entry.get("path_class")),
                path.read_bytes().decode("utf-8", errors="replace"),
                int(entry.get("loc") or 0), int(entry.get("churn") or 0),
            ))
        return build_reference_graph(graph_files, config["fan_in"]).edges
    except Exception:  # noqa: BLE001  (a graph failure must never abort verification)
        return None


def _referrers(edges: list[tuple[str, str]] | None, file: str) -> str:
    """Files whose import lines reference ``file``'s stem; never fatal to a verification.

    ``edges is GRAPH_FAILED`` is an identity check, not ``==``: an empty list the
    graph legitimately built (no edges found) is not the sentinel and must still
    read as "none found", while the sentinel and a bare ``None`` both read as
    "not computed".
    """
    if edges is None or edges is GRAPH_FAILED:
        return "not computed"
    stem = file_stem(file)
    referrers = sorted({src for src, dst in edges if dst == file or file_stem(dst) == stem})
    return redact(", ".join(referrers)) if referrers else "none found"


def _traps(config: dict[str, Any], family: str, file: str) -> list[str]:
    """The configured traps whose family matches and whose glob matches ``file``."""
    out = []
    for trap in config.get("traps") or []:
        if not isinstance(trap, dict) or trap.get("family") != family:
            continue
        if fnmatch.fnmatch(file, str(trap.get("path_glob", "*"))):
            out.append(str(trap.get("note", "")))
    return out


def render_verify_prompt(
    batch: list[dict[str, Any]],
    *,
    root: Path,
    inventory: dict[str, Any],
    coupling: dict[str, Any],
    config: dict[str, Any],
    edges: list[tuple[str, str]] | None = None,
) -> str:
    """One read-only verification prompt covering every candidate in ``batch``.

    ``edges`` is the reference graph ``build_verify_plan`` built once for the whole
    plan; left at None the graph is built here, which is what a single-prompt
    caller wants and what a failed build (``_reference_edges`` returns None) falls
    back to.
    """
    context = int(config["verifier"]["context_lines"])
    if edges is None:
        edges = _reference_edges(root, inventory, config)
    parts = [
        "You are a read-only verifier. Read and search files; change nothing.",
        "For each candidate below decide whether the described debt is real, using the cited "
        "span, the surrounding code and the questions listed. Before giving a verdict you may "
        f"open up to {EXPLORATION_FILES} further files you name, chosen from the referrers, the "
        "change-coupled files or the callees of the cited span; record them in `opened`.",
        "",
    ]
    for index, cand in enumerate(batch, start=1):
        primary = _primary(cand)
        block = FAMILY_BLOCKS[cand["family"]]
        signals = cand["signals"]
        parts += [
            f"## Candidate {index}",
            f"fingerprint: {cand['fingerprint']}",
            f"title: {redact(cand['title'])}",
            f"family: {cand['family']}  severity: {cand['severity']}  effort: {cand['effort']}",
            f"note: {redact(cand['note'])}",
            f"confirmed_by: {', '.join(cand['confirmed_by'])}",
            "signals: "
            f"hotspot_score={signals['hotspot_score']} churn={signals['churn']} "
            f"coupling_degree={signals['coupling_degree']} "
            f"fan_in_approx={signals['fan_in_approx']} path_class={signals['path_class']} "
            f"in_hotspot_band={signals['in_hotspot_band']}",
            "",
        ]
        for ev in cand["evidence"]:
            parts += [_span(root, ev, context), ""]
        coupled = _coupled(coupling, primary["file"])
        parts.append("change-coupled files: " + (", ".join(coupled) if coupled else "none"))
        parts.append("approximate referrers: " + _referrers(edges, primary["file"]))
        parts.append("questions:")
        parts += [f"  - {q}" for q in block.verifier_questions]
        parts.append(FAMILY_TRAPS_HEADER)
        parts += [f"  - {redact(t)}" for t in block.traps]
        traps = _traps(config, cand["family"], primary["file"])
        if traps:
            parts.append(REPO_TRAPS_HEADER)
            parts += [f"  - {redact(t)}" for t in traps]
        parts.append("")
    parts.append(VERDICT_CONTRACT)
    return "\n".join(parts) + "\n"


# --- plan -----------------------------------------------------------------------------------


def build_verify_plan(
    workdir: Path, root: Path, config: dict[str, Any], top: int
) -> tuple[dict[str, Any], dict[str, str]]:
    """The ``verify-plan.json`` document and the prompt text keyed by its relative path.

    Raises ``ValueError`` when ``candidates.json`` is not a document with a
    ``candidates`` list, so the CLI reports it rather than raising a traceback.
    """
    candidates_doc = json.loads((workdir / "candidates.json").read_bytes())
    if not isinstance(candidates_doc, dict) or not isinstance(
        candidates_doc.get("candidates"), list
    ):
        raise ValueError(f"candidates.json in {workdir} has no candidates list")
    inventory = json.loads((workdir / "inventory.json").read_bytes())
    coupling_path = workdir / "coupling.json"
    coupling = json.loads(coupling_path.read_bytes()) if coupling_path.is_file() else {}
    selected, unverified = select_candidates(list(candidates_doc["candidates"]), config, top)
    batches = build_batches(selected, int(config["verifier"]["batch_size"]))
    # One graph for the plan: it reads every source and tests file in the inventory.
    # A failed build becomes GRAPH_FAILED here, once, so every batch's prompt renders
    # "not computed" without render_verify_prompt attempting (and re-reading the whole
    # repository for) a second build per batch.
    edges = _reference_edges(root, inventory, config)
    if edges is None:
        edges = GRAPH_FAILED
    prompts: dict[str, str] = {}
    entries = []
    for number, batch in enumerate(batches, start=1):
        prompt_rel = f"prompts/verify-{number:02d}.md"
        prompts[prompt_rel] = render_verify_prompt(
            batch, root=root, inventory=inventory, coupling=coupling, config=config, edges=edges)
        entries.append({"prompt": prompt_rel, "output": f"verdicts/verify-{number:02d}.json",
                        "fingerprints": [c["fingerprint"] for c in batch]})
    plan = {
        "schema_version": SCHEMA_VERSION,
        "top": int(top),
        "batch_size": int(config["verifier"]["batch_size"]),
        "selected": [fp for e in entries for fp in e["fingerprints"]],
        "unverified": unverified,
        "batches": entries,
    }
    return plan, prompts


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Select candidates for verification and render the prompts")
    parser.add_argument("--workdir", default=".tech-debt",
                        help="directory holding candidates.json")
    parser.add_argument("--top", type=int, default=None,
                        help="findings to report (default: config)")
    args = parser.parse_args(argv)
    workdir = Path(args.workdir)
    if not (workdir / "candidates.json").is_file() or not (workdir / "inventory.json").is_file():
        print(f"error: candidates.json and inventory.json are required in {workdir}",
              file=sys.stderr)
        return 2
    try:
        inventory = json.loads((workdir / "inventory.json").read_bytes())
        if not isinstance(inventory, dict):
            raise ValueError(f"inventory.json in {workdir} is not a JSON object")
        root = Path(str(inventory.get("root", ".")))
        config = load_config(root)
        top = args.top if args.top is not None else int(config["top"])
        plan, prompts = build_verify_plan(workdir, root, config, top)
    # OSError covers an unreadable input; ValueError covers bad JSON and a
    # candidates document without a candidates list; KeyError covers a
    # candidate entry missing a field the budget rule reads.
    except (ConfigError, OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for rel, text in prompts.items():
        target = workdir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))
    # Every batch's ``output`` points into verdicts/; phase 3 dispatches an agent
    # that writes there, so the directory exists before the plan is handed over.
    (workdir / "verdicts").mkdir(parents=True, exist_ok=True)
    write_json(workdir / "verify-plan.json", plan)
    print(f"{len(plan['selected'])} candidate(s) in {len(plan['batches'])} batch(es); "
          f"{len(plan['unverified'])} unverified")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
