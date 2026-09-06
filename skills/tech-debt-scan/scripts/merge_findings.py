"""Turn scout output and rule findings into one verified candidate list (spec 4.7).

Reads ``scan-plan.json`` (which scout files to expect), ``scouts/<family>.json``,
``rule-findings.json``, ``inventory.json`` and ``patterns.json`` from
``--workdir``, and ``.tech-debt.yaml`` from the repository root. Writes
``candidates.json``. Coupling is not read here: ``coupling_degree`` reaches a
candidate through the inventory signals ``evidence.signals_for`` attaches.

Steps, in order: read each family's scout file (one missing is counted under
``stats[family].missing_file``, one present but unreadable or malformed JSON
under ``stats[family].read_failed``; neither aborts the merge, every other
family's scout file is still read); validate each scout item (malformed items
are dropped and counted, with the reason string collected under
``stats[family].dropped_reasons`` when at least one item was dropped);
normalise paths; verify every quote on disk through
``evidence.find_quote`` (a finding with no verified evidence is diverted to
``open_questions`` with reason ``quote not found``); fingerprint on the primary
evidence; cluster same-family, same-file findings within ``CLUSTER_WINDOW``
lines; corroborate from pattern leads of the candidate's own family, SATD
markers, rule findings, coupling and the hotspot band; attach inventory
signals; apply suppressions and path-class disables; redact every quote, title
and note. ``missing_file``, ``read_failed`` and ``dropped_reasons`` are all
out-of-band stat keys, appended only when they apply.

Rule findings enter as tier A candidates with ``source: "rule"`` and are never
merged into a scout candidate: they corroborate it (``rule:<id>`` in
``confirmed_by``) and stand beside it, so a verified-by-construction fact is
never diluted by a scout claim. Rule findings are not re-checked against
path-class disables here: ``rules.py`` drops disabled-class artefacts before
emitting them, so a rule finding reaching this module has already passed that
filter.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any, Final

from categories import FAMILIES
from config import ConfigError, load_config
from evidence import find_quote, fingerprint, signals_for
from inventory import write_json
from plan_scan import disabled_families
from redaction import redact
from validation import ValidationError, validate_debt_type, validate_effort, validate_type_id

SCHEMA_VERSION: Final[int] = 2
CLUSTER_WINDOW: Final[int] = 10
EFFORT_RANK: Final[dict[str, int]] = {"S": 0, "M": 1, "L": 2}
STAT_KEYS: Final[tuple[str, ...]] = (
    "raw", "dropped", "quote_failed", "clustered", "suppressed", "disabled",
)
TITLE_MAX: Final[int] = 80
NOTE_MAX: Final[int] = 300


def _new_stats() -> dict[str, int]:
    return dict.fromkeys(STAT_KEYS, 0)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_bytes()) if path.is_file() else None


# --- validation -----------------------------------------------------------------------


def _normalise_path(raw: Any) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    rel = raw.replace("\\", "/").strip()
    while rel.startswith("./"):
        rel = rel[2:]
    if rel.startswith("/") or ".." in rel.split("/") or ":" in rel.split("/")[0]:
        return None
    return rel


def _clean_evidence(evidence: list[Any]) -> list[dict[str, Any]]:
    """Evidence items with a usable root-relative path and a quote, others dropped."""
    cleaned: list[dict[str, Any]] = []
    for ev in evidence:
        if not isinstance(ev, dict):
            continue
        rel = _normalise_path(ev.get("file"))
        quote = ev.get("quote")
        start, end = ev.get("line_start"), ev.get("line_end")
        if rel is None or not isinstance(quote, str):
            continue
        cleaned.append({
            "file": rel,
            "line_start": start if isinstance(start, int) and not isinstance(start, bool) else None,
            "line_end": end if isinstance(end, int) and not isinstance(end, bool) else None,
            "quote": quote,
        })
    return cleaned


def _validate(item: Any, family: str) -> dict[str, Any] | str:
    """A cleaned finding, or the reason it was dropped.

    The title and the note are redacted *before* they are cut to their caps,
    the same order ``rules.py`` uses. Every branch of ``redaction``'s
    ``SECRET_TOKEN_RE`` is length-gated, so cutting first and redacting later
    hands the redactor a token already broken in half: it stops matching its
    own pattern and the fragment reaches ``candidates.json``, ``design.md``,
    ``findings.json`` and a promoted ``PBI.md`` verbatim, because every
    write-time ``redact`` downstream is gated identically and misses it too.
    Cutting an already-redacted string can only shorten the ``value[:4] + "***"``
    stub, which carries nothing the stub had not already given away.

    The evidence quotes are *not* redacted here: ``_verify`` has to match them
    against the file first, so they are redacted later, in ``_redact_candidate``.

    The title's internal whitespace is collapsed to single spaces as well as
    stripped at the ends. Every consumer renders it on a line it owns -- the
    verifier prompt's ``title:`` line, ``design.md``'s ``## <title>`` heading,
    the notes prompt's ``## <n>. <title>`` -- so an embedded newline is a
    structural break, not content, and collapsing it here also makes the
    80-character cap count the characters a reader will actually see.
    ``design_writer.heading_text`` collapses it again at write time, so a title
    from a producer that never passed through this module is safe too.
    """
    if not isinstance(item, dict):
        return "not an object"
    title = item.get("title")
    if not isinstance(title, str) or not title.strip():
        return "missing title"
    if item.get("family") != family:
        return f"family {item.get('family')!r} is not {family!r}"
    type_id = item.get("type_id")
    try:
        validate_debt_type(str(item.get("debt_type")))
        validate_effort(str(item.get("effort")))
        if type_id is not None:
            validate_type_id(str(type_id))
    except ValidationError as exc:
        return str(exc)
    severity = item.get("severity")
    if not isinstance(severity, int) or isinstance(severity, bool) or not 1 <= severity <= 5:
        return f"severity {severity!r} out of range"
    evidence = item.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return "no evidence"
    cleaned = _clean_evidence(evidence)
    if not cleaned:
        return "no usable evidence"
    note = item.get("note")
    cited = item.get("signals_cited")
    return {
        "title": redact(" ".join(title.split()))[:TITLE_MAX],
        "family": family,
        "debt_type": str(item["debt_type"]),
        "type_id": str(type_id) if type_id is not None else None,
        "severity": severity,
        "effort": str(item["effort"]),
        "signals_cited": sorted({str(s) for s in cited}) if isinstance(cited, list) else [],
        "evidence": cleaned,
        "note": redact(note.strip() if isinstance(note, str) else "")[:NOTE_MAX],
    }


# --- quote verification ---------------------------------------------------------------


class _Files:
    """Lines of every file read during one merge, cached and decoded once."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._cache: dict[str, list[str] | None] = {}

    def lines(self, rel: str) -> list[str] | None:
        if rel not in self._cache:
            path = self.root / rel
            try:
                raw = path.read_bytes() if path.is_file() else None
            except OSError:
                raw = None
            text = raw.decode("utf-8", errors="replace") if raw is not None else None
            self._cache[rel] = text.splitlines() if text is not None else None
        return self._cache[rel]


def _verify(finding: dict[str, Any], files: _Files) -> list[dict[str, Any]]:
    verified: list[dict[str, Any]] = []
    for ev in finding["evidence"]:
        lines = files.lines(ev["file"])
        if lines is None:
            continue
        found = find_quote(lines, ev["quote"], ev["line_start"], ev["line_end"])
        if found is None:
            continue
        verified.append({
            "file": ev["file"],
            "line_start": found[0],
            "line_end": found[1],
            "quote": ev["quote"],
            "quote_verified": True,
        })
    return verified


# --- clustering and corroboration ----------------------------------------------------


def _near(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return not (a_start > b_end + CLUSTER_WINDOW or b_start > a_end + CLUSTER_WINDOW)


def _primary(cand: dict[str, Any]) -> dict[str, Any]:
    primary: dict[str, Any] = cand["evidence"][0]
    return primary


def _wins(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Whether ``a`` is the higher-severity member (tie: the lower fingerprint)."""
    return (a["severity"], -int(a["fingerprint"], 16)) > (b["severity"], -int(b["fingerprint"], 16))


def _absorb(keep: dict[str, Any], other: dict[str, Any]) -> None:
    seen = {(e["file"], e["line_start"], e["line_end"]) for e in keep["evidence"]}
    for ev in other["evidence"]:
        key = (ev["file"], ev["line_start"], ev["line_end"])
        if key not in seen:
            keep["evidence"].append(ev)
            seen.add(key)
    if _wins(other, keep):
        keep["title"], keep["note"] = other["title"], other["note"]
        keep["type_id"], keep["debt_type"] = other["type_id"], other["debt_type"]
    keep["severity"] = max(keep["severity"], other["severity"])
    keep["effort"] = min(keep["effort"], other["effort"], key=lambda e: EFFORT_RANK[e])
    keep["signals_cited"] = sorted(set(keep["signals_cited"]) | set(other["signals_cited"]))
    keep["confirmed_by"] = sorted(set(keep["confirmed_by"]) | set(other["confirmed_by"]))


def _clusters_with(keep: dict[str, Any], cand: dict[str, Any]) -> bool:
    k, p = _primary(keep), _primary(cand)
    return (
        keep["family"] == cand["family"]
        and k["file"] == p["file"]
        and _near(k["line_start"], k["line_end"], p["line_start"], p["line_end"])
    )


def _cluster(cands: list[dict[str, Any]], stats: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
    def order(c: dict[str, Any]) -> tuple[Any, ...]:
        p = _primary(c)
        return (c["family"], p["file"], p["line_start"], c["fingerprint"])

    cands.sort(key=order)
    out: list[dict[str, Any]] = []
    for cand in cands:
        for index, keep in enumerate(out):
            if not _clusters_with(keep, cand):
                continue
            if cand["fingerprint"] < keep["fingerprint"]:
                # The member with the lower fingerprint keeps the cluster's identity.
                keep, cand = cand, keep
                out[index] = keep
            _absorb(keep, cand)
            stats[keep["family"]]["clustered"] += 1
            break
        else:
            out.append(cand)
    return out


def _corroborate(
    cand: dict[str, Any],
    patterns: dict[str, Any],
    rules: list[dict[str, Any]],
    inventory: dict[str, Any],
) -> None:
    sources = set(cand["confirmed_by"])
    spans = [(e["file"], e["line_start"], e["line_end"]) for e in cand["evidence"]]

    def hits(path: str, line: Any) -> bool:
        if not isinstance(line, int) or isinstance(line, bool):
            return False
        return any(f == path and _near(s, e, line, line) for f, s, e in spans)

    # A pattern lead only corroborates a candidate of its own family: the leads are
    # keyed by family, and a dead-code lead beside an error-masking catch says
    # nothing about whether that catch masks a failure. SATD markers, rule
    # findings, coupling and the hotspot band stay family-agnostic (spec 4.7).
    for lead in (patterns.get("leads") or {}).get(cand["family"]) or []:
        if hits(str(lead["file"]), lead.get("line")):
            sources.add(f"pattern:{lead['rule']}")
    for marker in patterns.get("satd") or []:
        if hits(str(marker["file"]), marker.get("line")):
            sources.add("satd")
    for rule in rules:
        for ev in rule.get("evidence") or []:
            if ev.get("file") and hits(str(ev["file"]), ev.get("line_start")):
                sources.add(f"rule:{rule['rule_id']}")
    signals = cand["signals"]
    if signals["coupling_degree"]:
        sources.add("coupling")
    if signals["in_hotspot_band"]:
        sources.add("hotspot")
    if cand["family"] == "test-gaps":
        primary = _primary(cand)["file"]
        entry = next((e for e in inventory.get("files", []) if e["path"] == primary), None)
        if entry is not None and not entry.get("mapped_tests"):
            sources.add("signal:no-mapped-tests")
    cand["confirmed_by"] = sorted(sources)


# --- suppressions and disables --------------------------------------------------------


def _suppressed(cand: dict[str, Any], config: dict[str, Any], today: date) -> bool:
    for item in config.get("suppressions") or []:
        if not isinstance(item, dict) or item.get("fingerprint") != cand["fingerprint"]:
            continue
        until = item.get("until")
        if until is None:
            return True
        try:
            return date.fromisoformat(str(until)) >= today
        except ValueError:
            return True
    return False


# --- assembly -------------------------------------------------------------------------


def _candidate(
    finding: dict[str, Any], verified: list[dict[str, Any]], inventory: dict[str, Any]
) -> dict[str, Any]:
    primary = verified[0]
    fp, quote_hash = fingerprint(finding["family"], primary["file"], primary["quote"])
    return {
        "fingerprint": fp,
        "quote_hash": quote_hash,
        "family": finding["family"],
        "debt_type": finding["debt_type"],
        "type_id": finding["type_id"],
        "title": finding["title"],
        "severity": finding["severity"],
        "effort": finding["effort"],
        "source": "scout",
        "rule_id": None,
        "note": finding["note"],
        "evidence": verified,
        "confirmed_by": [f"scout:{finding['family']}"],
        "signals_cited": finding["signals_cited"],
        "signals": signals_for(inventory, primary["file"]),
        "tier": None,
    }


def _redact_candidate(cand: dict[str, Any]) -> None:
    """Redact the verified quotes, and re-assert the title and note.

    The quotes could not be redacted before now: ``_verify`` matches each one
    against the file on disk, and a redacted quote would no longer match. The
    title and note were already redacted in ``_validate``, before their caps
    were applied; ``redact`` is idempotent, so repeating it here costs nothing
    and keeps this the single place a reader can check that every string a
    candidate carries has been through it.
    """
    cand["title"] = redact(cand["title"])
    cand["note"] = redact(cand["note"])
    for ev in cand["evidence"]:
        ev["quote"] = redact(ev["quote"])


def _order(cands: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(c: dict[str, Any]) -> tuple[Any, ...]:
        p = c["evidence"][0] if c["evidence"] else {"file": "", "line_start": 0}
        return (
            FAMILIES.index(c["family"]) if c["family"] in FAMILIES else len(FAMILIES),
            p.get("file") or "",
            p.get("line_start") or 0,
            c["fingerprint"],
        )

    return sorted(cands, key=key)


def merge(
    workdir: Path, root: Path, config: dict[str, Any], *, today: date | None = None
) -> dict[str, Any]:
    """The candidates.json document for the scouts named in the plan."""
    plan = _read_json(workdir / "scan-plan.json")
    inventory = _read_json(workdir / "inventory.json")
    if not isinstance(plan, dict) or not isinstance(inventory, dict):
        raise FileNotFoundError(f"scan-plan.json and inventory.json are required in {workdir}")
    patterns = _read_json(workdir / "patterns.json") or {}
    rules_doc = _read_json(workdir / "rule-findings.json") or {}
    rule_findings = [f for f in rules_doc.get("findings") or [] if isinstance(f, dict)]
    day = today or date.today()
    files = _Files(root.resolve())
    stats: dict[str, dict[str, int]] = {}
    dropped_reasons: dict[str, list[str]] = {}
    scout_cands: list[dict[str, Any]] = []
    open_questions: list[dict[str, Any]] = []
    looks_fine: list[dict[str, Any]] = []
    for entry in plan.get("entries") or []:
        family = str(entry["family"])
        stats.setdefault(family, _new_stats())
        try:
            doc = _read_json(workdir / str(entry["output"]))
        except (OSError, ValueError):
            stats[family]["read_failed"] = 1
            continue
        if not isinstance(doc, dict):
            stats[family]["missing_file"] = 1
            continue
        for question in doc.get("open_questions") or []:
            if isinstance(question, dict):
                open_questions.append({
                    "file": question.get("file"),
                    "line_start": question.get("line_start"),
                    "question": redact(str(question.get("question", ""))),
                    "reason": None,
                })
        for item in doc.get("looks_bad_but_fine") or []:
            if isinstance(item, dict):
                looks_fine.append({
                    "file": item.get("file"),
                    "line_start": item.get("line_start"),
                    "why": redact(str(item.get("why", ""))),
                })
        for raw in doc.get("findings") or []:
            stats[family]["raw"] += 1
            cleaned = _validate(raw, family)
            if isinstance(cleaned, str):
                stats[family]["dropped"] += 1
                dropped_reasons.setdefault(family, []).append(redact(cleaned))
                continue
            verified = _verify(cleaned, files)
            if not verified:
                stats[family]["quote_failed"] += 1
                first = cleaned["evidence"][0]
                open_questions.append({
                    "file": first["file"],
                    "line_start": first["line_start"],
                    "question": redact(cleaned["title"]),
                    "reason": "quote not found",
                })
                continue
            scout_cands.append(_candidate(cleaned, verified, inventory))
    kept: list[dict[str, Any]] = []
    for cand in _cluster(scout_cands, stats):
        _corroborate(cand, patterns, rule_findings, inventory)
        if _suppressed(cand, config, day):
            stats[cand["family"]]["suppressed"] += 1
            continue
        path_class = str(cand["signals"]["path_class"] or "source")
        if cand["family"] in disabled_families(config, path_class):
            stats[cand["family"]]["disabled"] += 1
            continue
        _redact_candidate(cand)
        kept.append(cand)
    rule_kept: list[dict[str, Any]] = []
    for cand in rule_findings:
        family = str(cand["family"])
        stats.setdefault(family, _new_stats())
        if _suppressed(cand, config, day):
            stats[family]["suppressed"] += 1
            continue
        rule_kept.append(cand)
    # dropped_reasons is recorded out-of-band (like missing_file and read_failed) so a
    # family with nothing dropped keeps the exact six pinned stat keys; it is appended
    # last, after missing_file and read_failed.
    final_stats: dict[str, dict[str, Any]] = {}
    for family, counts in stats.items():
        stat_entry: dict[str, Any] = dict(counts)
        if family in dropped_reasons:
            stat_entry["dropped_reasons"] = dropped_reasons[family]
        final_stats[family] = stat_entry
    return {
        "schema_version": SCHEMA_VERSION,
        "candidates": _order(kept) + _order(rule_kept),
        "open_questions": open_questions,
        "looks_bad_but_fine": looks_fine,
        "stats": final_stats,
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Merge scout output and rule findings into candidates.json"
    )
    parser.add_argument("--workdir", default=".tech-debt", help="directory holding the scan files")
    args = parser.parse_args(argv)
    workdir = Path(args.workdir)
    inventory = _read_json(workdir / "inventory.json")
    if not isinstance(inventory, dict) or not (workdir / "scan-plan.json").is_file():
        message = f"error: scan-plan.json and inventory.json are required in {workdir}"
        print(message, file=sys.stderr)
        return 2
    root = Path(str(inventory.get("root", ".")))
    try:
        config = load_config(root)
        doc = merge(workdir, root, config)
    # OSError covers the FileNotFoundError ``merge`` raises; ValueError covers bad JSON.
    except (ConfigError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    write_json(workdir / "candidates.json", doc)
    print(f"{len(doc['candidates'])} candidate(s), {len(doc['open_questions'])} open question(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
