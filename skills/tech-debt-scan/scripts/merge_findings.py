"""Turn scout output and rule findings into one verified candidate list (spec 4.7).

Reads ``scan-plan.json`` (which scout files to expect), ``scouts/<family>.json``,
``rule-findings.json``, ``inventory.json``, ``patterns.json`` and
``tool-signals.json`` (absent means no tool signals) from ``--workdir``, and
``.tech-debt.yaml`` from the repository root. Writes ``candidates.json``.
Coupling is not read here: ``coupling_degree`` reaches a candidate through the
inventory signals ``evidence.signals_for`` attaches.

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
markers, rule findings, coupling and the hotspot band; corroborate again from
tool signals of the candidate's own family and file (``tool:<name>`` in
``confirmed_by``, added once per candidate list is settled and before any
tool-derived candidates exist, so a signal can never corroborate the finding
it raised, and skipping a signal whose own path class disables its family --
the same ``families.per_path_class`` disable ``plan_scan`` applies to the lead
built from that signal); attach inventory signals; apply suppressions and
path-class disables; redact every quote, title and note. ``missing_file``,
``read_failed`` and ``dropped_reasons`` are all out-of-band stat keys,
appended only when they apply.

Rule findings enter as tier A candidates with ``source: "rule"`` and are never
merged into a scout candidate: they corroborate it (``rule:<id>`` in
``confirmed_by``) and stand beside it, so a verified-by-construction fact is
never diluted by a scout claim. Rule findings are not re-checked against
path-class disables here: ``rules.py`` drops disabled-class artefacts before
emitting them, so a rule finding reaching this module has already passed that
filter.

Fact-class tool signals earn a candidate the same way (``tool_candidates``, spec
4.5): an osv-scanner advisory enters tier A exactly as a rule finding does (the
manifest or lockfile is the evidence, or -- when osv named a docker image or a
git remote instead of a file -- a null-file repository-level fact, the shape a
path-less rule finding already uses); a gitleaks secret enters untiered, so a
verifier judges whether it is a live credential or a fixture; a hadolint or
actionlint fact merges into a same-file rule finding's ``confirmed_by`` when one
exists, and otherwise enters untiered on its own, both with an *empty*
``confirmed_by`` (spec 2.3's family caps would otherwise read the signal's own
``tool:<name>`` origin as independent corroboration of itself). ``rules.py`` and
these two fact-class tools are the whole producer set for a non-``None`` tier at
merge time: ``verify_prompts.select_candidates`` pools only untiered candidates,
so any other class acquiring one would reach a report with no verifier having
read it -- the invariant ``test_merge_findings.TestTierProducerInvariant`` pins,
over the corpus and over a canned signals file, as spec 4.7 requires.

``tool-signals.json`` is the least validated document this module reads, so every
tool route checks the signal before building anything from it: the family must be
one ``categories.FAMILIES`` knows *and* the tool's own (``_TOOL_FAMILY``), an
untiered route must name a usable root-relative file, and a fingerprint already
raised in the same pass collapses instead of duplicating. Each drop is counted in
``stats`` for the tool's own family, with its reason under ``dropped_reasons``.
Tool candidates are then filtered by both of spec 4.7 step 7's tests -- fingerprint
suppressions and path-class disables -- because unlike rule findings no upstream
pass has applied a user's disables to them.
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
from plan_scan import disabled_families, path_classes
from redaction import redact, strip_url_userinfo
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
    ``findings.json`` and a rendered ``evidence.md`` verbatim, because every
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


def corroborate_with_tools(
    candidates: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    classes: dict[str, str],
    config: dict[str, Any],
) -> None:
    """Add a ``tool:<name>`` token where an inference signal backs a candidate.

    This token is the whole mechanism by which the 2.3 caps lift:
    ``apply_verdicts.family_cap`` returns no cap for duplication, dead-code,
    architecture, test-quality, dependency-debt and security once it is
    present. Matching is same family, same file — a tool that flags the same
    file for the same reason is a second opinion, and line proximity is not
    required because a tool's range and a scout's rarely coincide. A
    candidate is checked against *every* evidence file it cites, not only the
    first: jscpd emits one signal per clone pair naming only its own
    ``firstFile``, and a scout's evidence order need not agree with jscpd's
    (madge and architecture share this shape), so matching only the primary
    evidence item would silently drop corroboration whenever the two
    producers order the same pair's files differently.

    Fact-class signals are excluded: those become candidates in their own
    right, and letting one both raise a finding and vouch for it would make a
    single source look like two.

    A signal on a path whose class disables its family is dropped, through the
    same ``plan_scan.disabled_families`` check ``_filtered_sorted_leads``
    applies to the lead built from that same signal (``classes`` is
    ``plan_scan.path_classes``, the map that function reads too). Without it the
    two ends of one signal disagree: the documented way to say "clones inside
    fixtures are not debt" (``per_path_class: {tests: {disable: [duplication]}}``)
    drops the jscpd lead and then lets the identical signal lift a source-file
    candidate's cap to tier A. Matching every evidence file makes this reachable
    on real input -- this repository's only jscpd signal is on a fixture.
    """
    by_family: dict[tuple[str, str], set[str]] = {}
    for item in signals:
        if not isinstance(item, dict) or item.get("fact"):
            continue
        path, family, tool = item.get("file"), item.get("family"), item.get("tool")
        if not isinstance(path, str) or not path or not family or not tool:
            continue
        if str(family) in disabled_families(config, classes.get(path, "source")):
            continue
        by_family.setdefault((str(family), path), set()).add(str(tool))
    if not by_family:
        return
    for cand in candidates:
        evidence = cand.get("evidence") or []
        if not evidence:
            continue
        family = str(cand.get("family"))
        tools: set[str] = set()
        for ev in evidence:
            tools |= by_family.get((family, str(ev.get("file"))), set())
        if not tools:
            continue
        cand["confirmed_by"] = sorted(set(cand["confirmed_by"]) | {f"tool:{t}" for t in tools})


# --- fact-class tool routings (spec 4.5, 4.7) ------------------------------------------

# Tools whose fact merges into a same-file rule finding of its own family, rather than
# raising a second candidate for a fact rules.py has already reported.
_MERGE_INTO_RULE_TOOLS: Final[frozenset[str]] = frozenset({"hadolint", "actionlint"})
# The one family each fact-class tool may claim. ``tool-signals.json`` is the least
# validated input this module reads (scout findings go through ``_validate``, rule
# findings through an isinstance check), and the family is not cosmetic: it picks the
# 2.3 caps and the rubric a candidate is judged under, while ``debt_type`` and
# ``type_id`` come from ``_TOOL_META`` keyed on the *tool*. Taking the family verbatim
# let a signal claiming ``duplication`` reach a report as a tier-A duplication finding
# carrying a dependency ``type_id`` -- a triple ``categories.FAMILY_BLOCKS`` does not
# allow -- and a signal with no family at all reach it in a family literally named
# ``"None"``. A tier literal closed to osv-scanner is not enough while the family is
# open to anything, so every route checks both that the family is a family the skill
# knows (``categories.FAMILIES``) and that it is this tool's own.
_TOOL_FAMILY: Final[dict[str, str]] = {
    "osv-scanner": "dependency-debt",
    "gitleaks": "security",
    "hadolint": "pipeline-infra",
    "actionlint": "pipeline-infra",
}
# (debt_type, type_id, effort) per tool. osv-scanner, hadolint and actionlint reuse the
# values rules.py's own GROUP_META gives the same fact (manifest, container, ci): a
# lockfile advisory, a Dockerfile gap and a workflow gap are the same debt whether
# rules.py or a tool found them. gitleaks has no rules.py counterpart -- security is
# scout- and tool-only -- so its values come from categories.FAMILY_BLOCKS["security"]
# and the SEVERITY_RUBRIC's own top band. Its effort is M, not the S the other three
# take: a confirmed live credential is not a one-line edit but a rotation, a redeploy,
# an access audit and usually a history rewrite.
_TOOL_META: Final[dict[str, tuple[str, str, str]]] = {
    "osv-scanner": ("dependency", "TD-02", "S"),
    "gitleaks": ("security", "TD-03", "M"),
    "hadolint": ("infrastructure", "TD-19", "S"),
    "actionlint": ("build", "TD-14", "S"),
}
# The closed set of tools whose ``extra["severity"]`` may stand in for the table below.
# Both compute it in their own normaliser from the tool's own data -- hadolint from its
# level (``tool_normalisers.HADOLINT_SEVERITY``), osv-scanner from the advisory's
# published severity (``tool_normalisers.osv_severity``) -- so reading it here is
# reading the tool, not the signals file. It is a closed set rather than "any tool with
# the key" because ``extra`` is unvalidated: letting any tool override the table would
# let a corrupt or hand-edited ``tool-signals.json`` set the severity of a tier-A
# advisory, which no verifier ever revises and which multiplies straight into
# ``rank.priority``.
_EXTRA_SEVERITY_TOOLS: Final[frozenset[str]] = frozenset({"hadolint", "osv-scanner"})
# Severity a fact carries when its tool computed none. gitleaks and actionlint have no
# per-finding severity at all, so a fixed value is all there is: gitleaks (a live
# credential) takes the SEVERITY_RUBRIC's top band; actionlint takes the same baseline
# rules.py's ci group gives an ordinary workflow gap. For hadolint and osv-scanner this
# is only the fallback -- an unrecognised hadolint level, or an advisory that publishes
# no severity of its own, which is where every osv advisory sat before 4b.
_TOOL_SEVERITY: Final[dict[str, int]] = {
    "osv-scanner": 4, "gitleaks": 5, "hadolint": 3, "actionlint": 3,
}


def _tool_severity(sig: dict[str, Any], tool: str) -> int:
    """The 1-5 severity for one fact, from the tool's own scoring where it has one.

    Only ``_EXTRA_SEVERITY_TOOLS`` consult ``extra["severity"]``; every other tool takes
    ``_TOOL_SEVERITY`` unconditionally, so a value in a signals file cannot reach a
    severity the code did not intend. The value is range-checked either way.
    """
    if tool in _EXTRA_SEVERITY_TOOLS:
        extra = sig.get("extra")
        value = extra.get("severity") if isinstance(extra, dict) else None
        if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 5:
            return value
    return _TOOL_SEVERITY.get(tool, 3)


def _fingerprint_span(
    path: str | None, line_start: Any, line_end: Any, *, column: int | None = None
) -> str:
    """The path component ``evidence.fingerprint`` hashes, with the line range folded in.

    ``fingerprint`` hashes family, path and quote, and a fact-class tool emits one
    record per hit whose message repeats verbatim across hits: every
    ``generic-api-key`` hit in one file carries the same
    ``f"{RuleID}: {Description}"``, and hadolint repeats one code's message down a
    Dockerfile. Without the range those hits share one fingerprint --
    ``apply_verdicts.apply`` keys verdicts by fingerprint and the last write wins, so a
    single verdict then decides all of them, and a confirmed live credential inherits a
    placeholder's rejection and never reaches the report. The range is folded into the
    path rather than into the quote so the message a reader sees stays the tool's own.

    ``column`` folds gitleaks' ``StartColumn`` in the same way, when the caller has
    one: two different secrets matched by the same rule on the same line otherwise
    agree on family, path, line range and message too, and would collapse onto this
    one fingerprint exactly as the line-range collision above does.

    The cost, accepted deliberately: a hit that moves by a line (or, now, a column)
    between two scans reads as a new finding to phase 5's baseline. Sharing one id
    between two different hits is the worse failure, because it loses one of them
    silently.
    """
    if line_start is None and line_end is None:
        return path or ""
    span = f"{path or ''}:{line_start}-{line_end}"
    return span if column is None else f"{span}@{column}"


def _usable_line(value: Any) -> int | None:
    """A signal's ``line_start``/``line_end`` coerced to the shape a candidate can
    carry: a plain ``int`` survives, everything else -- ``None``, a ``bool`` (a
    ``bool`` is an ``int`` subclass), a float, or a string like ``"12"`` a
    truncated or hand-edited ``tool-signals.json`` might carry -- becomes ``None``.
    Shared by ``_fact_candidate`` (which builds the coerced shape for
    ``line_start``/``line_end`` and, from ``extra["column"]``, the gitleaks column)
    and ``tool_candidates`` (which must reject that shape on the untiered route
    before it reaches a verifier)."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _fact_candidate(
    sig: dict[str, Any],
    inventory: dict[str, Any],
    *,
    path: str | None,
    tier: str | None,
    confirmed_by: list[str],
) -> dict[str, Any]:
    """One fact-class signal as a candidate, in the rule candidate shape (``rules.py``
    645-671): same keys, same order, with ``tool`` carrying the signal's tool name
    where a rule finding's is always ``None``. ``quote_verified`` is true
    unconditionally -- the tool already found the exact site, and there is no disk
    text left to re-check it against, the same reasoning ``rules.py`` uses for its
    own evidence.

    The quote states the fact rather than quoting a file (spec 4.5's shape for a
    repository-level rule fact, reused here): a tool signal carries a message, not a
    span of source text, so the message *is* the quote, for a real file's evidence
    exactly as for a null one. When the signal names no repository path at all (an
    osv-scanner advisory against a docker image or a git remote, carried with
    ``file: None`` and the source recorded in ``extra`` -- see
    ``tool_normalisers.normalise_osv_scanner``), that source is folded into the message
    before fingerprinting: two such facts about the same advisory but different images
    would otherwise share one empty path and one identical message, and collide onto a
    single fingerprint instead of staying two candidates. A git source is a URL, and a
    URL can carry ``user:password@`` userinfo that neither ``redact`` pattern
    recognises (``CREDENTIAL_RE`` needs a key name and an operator, ``SECRET_TOKEN_RE``
    a known issuer prefix), so the userinfo is dropped before the fold rather than
    relied on to be caught after it -- the host and path are all the fact needs.

    Redaction runs once, on the message, before it is cut into the title and note
    caps -- the order ``_validate`` uses. Cutting first would hand a length-gated
    ``SECRET_TOKEN_RE`` branch a fragment already too short to match its own pattern.
    """
    tool = str(sig.get("tool"))
    family = str(sig.get("family"))
    debt_type, type_id, effort = _TOOL_META[tool]
    extra = sig.get("extra")
    source_path = extra.get("source_path") if isinstance(extra, dict) else None
    raw_message = str(sig.get("message", ""))
    if isinstance(source_path, str) and source_path:
        raw_message = f"{raw_message} (source: {strip_url_userinfo(source_path)})"
    message = redact(raw_message)
    line_start = _usable_line(sig.get("line_start"))
    line_end = _usable_line(sig.get("line_end"))
    column = _usable_line(extra.get("column")) if isinstance(extra, dict) else None
    fp, quote_hash = fingerprint(
        family, _fingerprint_span(path, line_start, line_end, column=column), message
    )
    return {
        "fingerprint": fp,
        "quote_hash": quote_hash,
        "family": family,
        "debt_type": debt_type,
        "type_id": type_id,
        "title": message[:TITLE_MAX],
        "severity": _tool_severity(sig, tool),
        "effort": effort,
        "source": "tool",
        "rule_id": None,
        "tool": tool,
        "note": message[:NOTE_MAX],
        "evidence": [{
            "file": path,
            "line_start": line_start,
            "line_end": line_end,
            "column": column,
            "quote": message,
            "quote_verified": True,
        }],
        "confirmed_by": sorted(confirmed_by),
        "signals_cited": [],
        "signals": signals_for(inventory, path),
        "tier": tier,
    }


def _merge_into_rule(
    rule_findings: list[dict[str, Any]], *, tool: str, family: str, path: str
) -> bool:
    """Fold one fact into a same-file, same-family rule finding's ``confirmed_by``.

    True when a match absorbed it, so the caller raises no candidate for it; False when
    no rule finding covers the file, so the caller raises one of its own. The family
    matched on is the signal's own -- already checked against ``_TOOL_FAMILY`` by the
    caller -- not a literal: hard-coding ``pipeline-infra`` here was correct only for as
    long as both merging tools stayed in that family, and the day either moved the merge
    would silently stop merging and start raising a duplicate candidate beside the rule
    finding, with nothing failing.
    """
    for rule in rule_findings:
        if rule.get("family") != family:
            continue
        if any(ev.get("file") == path for ev in rule.get("evidence") or []):
            rule["confirmed_by"] = sorted(set(rule.get("confirmed_by") or []) | {f"tool:{tool}"})
            return True
    return False


def tool_candidates(
    signals: list[dict[str, Any]],
    inventory: dict[str, Any],
    rule_findings: list[dict[str, Any]],
    *,
    counts: list[tuple[str, str, str | None]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fact-class tool signals as candidates or rule corroboration (spec 4.5).

    Only a ``fact`` signal from one of the four tools in ``_TOOL_META`` ever reaches a
    candidate; an inference-class signal (a lint hint, a complexity count) stays
    corroboration-only, through ``corroborate_with_tools``. Three routings:

    * osv-scanner enters tier A, exactly as a rule finding does -- verification is
      skipped, so its own ``tool:osv-scanner`` token in ``confirmed_by`` is a harmless
      self-reference; a tier-A candidate's tier is never reconsidered.
    * gitleaks, and an uncovered hadolint or actionlint (no same-file rule finding
      exists), enter untiered with an *empty* ``confirmed_by``. A self-reported
      ``tool:<name>`` token here would be read by ``apply_verdicts.family_cap`` and
      ``corroborated`` as independent corroboration of the very thing that raised it --
      neither knows the token names the candidate's own source -- letting a single bare
      "confirm" jump straight to tier A with no second opinion. Leaving it empty is what
      lets the verifier's own judgement, not a self-reference, decide the tier.
    * a covered hadolint or actionlint (spec 4.4's rules.py already reported the same
      file) merges into that rule finding's ``confirmed_by`` instead of raising a
      second candidate for a fact already on the record; the finding stays tier A
      either way, so the merge changes nothing but its provenance trail. The merge is
      tried before the range guard below, not after: it reads no range at all, only
      the file the rule finding and the fact agree on, so a fact with no usable
      ``line_start``/``line_end`` still corroborates a rule finding it covers -- the
      guard exists for the untiered candidate route, which does need a range to build
      evidence, and must not reject a fact that never reaches that route.

    Four things drop a signal that names one of the four tools, each counted through
    ``counts`` so a dropped fact is visible in ``stats`` rather than silent:

    * a family that is not one ``categories.FAMILIES`` knows, or is not this tool's own
      (``_TOOL_FAMILY``) -- see that table for why the family cannot be taken verbatim;
    * an untiered route (gitleaks, hadolint, actionlint) whose ``file`` is missing or is
      not a usable root-relative path. There is nothing for a verifier to read, and the
      candidate would reach ``verify_prompts._span``'s ``root / ev["file"]`` and abort
      the whole scan with a ``TypeError`` rather than lose one finding. The tier-A osv
      route keeps its null-file shape: ``select_candidates`` never pools a tiered
      candidate, so it reaches no verifier, and every downstream consumer already
      handles the path-less rule finding shape;
    * that same untiered route with a ``line_start`` or ``line_end`` that is not a
      plain ``int`` once ``_usable_line`` coerces it -- the same reachability profile
      one field over: ``_span`` does ``int(ev["line_start"])`` right after the
      ``root / ev["file"]`` the file guard closed, so a null, a float or a string
      range aborts the scan exactly as a null file did. Reached only when the merge
      above did not already absorb the fact, since a merged fact raises no candidate
      and so never reaches a verifier or ``_span`` at all. The osv route is exempt for
      the same reason as the file check -- it is decided by which branch a tool
      falls into (``tool == "osv-scanner"`` above), not by inspecting ``tier``, so a
      future tier change to either route cannot silently widen or narrow this guard.
      Spec 4.5's null osv range (a manifest path, not a line) is untouched;
    * a fingerprint already raised in this pass. Two signals that agree on family, path,
      line range, column and message are almost always the same fact reported twice,
      and duplicating them gives two candidates one verdict can no longer tell apart
      (see ``_fingerprint_span``). This is the collapse ``_cluster`` gives scout
      candidates, narrowed to exact identity because a tool's records are already
      deduplicated within a file by everything except repetition.
      ``normalise_gitleaks`` keeps ``StartColumn`` in ``extra["column"]``, and
      ``_fact_candidate`` folds it into the fingerprint span, precisely so two
      *different* secrets matched by the same rule on the same line -- which would
      otherwise agree on every field this compares -- stay two candidates instead of
      collapsing into one (ruling 15).

    ``counts`` collects ``(family, stat key, reason)`` for the caller to fold into
    ``stats`` and ``dropped_reasons``; the family is the tool's own registry family, so
    a drop is counted somewhere a reader will look even when the claimed one was junk.

    Returns ``(new_candidates, rule_findings)``: the rule findings a merge mutated in
    place, returned for convenience, not a copy.
    """
    new: list[dict[str, Any]] = []
    seen: set[str] = set()
    record = counts if counts is not None else []
    for sig in signals:
        if not isinstance(sig, dict) or not sig.get("fact"):
            continue
        tool = str(sig.get("tool"))
        if tool not in _TOOL_META:
            continue
        expected = _TOOL_FAMILY[tool]
        family = str(sig.get("family"))
        if family not in FAMILIES:
            record.append((expected, "dropped", f"{tool} family {family!r} is not a known family"))
            continue
        if family != expected:
            record.append((expected, "dropped", f"{tool} family {family!r} is not {expected!r}"))
            continue
        path = _normalise_path(sig.get("file"))
        if tool == "osv-scanner":
            if sig.get("file") is not None and path is None:
                record.append((family, "dropped", f"{tool} path {sig.get('file')!r} is unusable"))
                continue
            cand = _fact_candidate(
                sig, inventory, path=path, tier="A", confirmed_by=["tool:osv-scanner"]
            )
        else:
            if path is None:
                record.append((family, "dropped", f"{tool} signal names no usable file"))
                continue
            if tool in _MERGE_INTO_RULE_TOOLS and _merge_into_rule(
                rule_findings, tool=tool, family=family, path=path
            ):
                continue
            if (
                _usable_line(sig.get("line_start")) is None
                or _usable_line(sig.get("line_end")) is None
            ):
                record.append(
                    (family, "dropped", f"{tool} signal names no usable line range")
                )
                continue
            cand = _fact_candidate(sig, inventory, path=path, tier=None, confirmed_by=[])
        if cand["fingerprint"] in seen:
            record.append((family, "clustered", None))
            continue
        seen.add(cand["fingerprint"])
        new.append(cand)
    return new, rule_findings


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
        "tool": None,
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
    # Read and routed here, right after rule_findings and before any suppression check,
    # so a hadolint or actionlint fact can still find and merge into the same-file rule
    # finding it corroborates (a fact merged in after the rule suppression loop below
    # would be merging into a finding that pass may have already dropped), and so the
    # new candidates it raises are themselves suppressed like any other, in the loop
    # below that appends them to ``kept``.
    tool_signals = (_read_json(workdir / "tool-signals.json") or {}).get("signals") or []
    tool_counts: list[tuple[str, str, str | None]] = []
    tool_cands, rule_findings = tool_candidates(
        tool_signals, inventory, rule_findings, counts=tool_counts
    )
    day = today or date.today()
    files = _Files(root.resolve())
    stats: dict[str, dict[str, int]] = {}
    dropped_reasons: dict[str, list[str]] = {}
    for tool_family, stat_key, reason in tool_counts:
        stats.setdefault(tool_family, _new_stats())
        stats[tool_family][stat_key] += 1
        if reason is not None:
            dropped_reasons.setdefault(tool_family, []).append(redact(reason))
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
    # Tool corroboration runs over ``kept`` exactly as the scout/pattern/rule pass above
    # left it -- before any fact-class tool signal becomes a candidate of its own
    # (``tool_cands``, appended to ``kept`` right below) and could be read as vouching
    # for the very finding it raised.
    #
    # ``rule_kept`` below is never passed to ``corroborate_with_tools``: a rule finding
    # is already tier A by construction, so ``apply_verdicts.family_cap`` (which this
    # token exists to unlock) is never reached for it. Fact-class tool signals get their
    # own, narrower route into a rule finding's ``confirmed_by`` (``tool_candidates``,
    # above); this is not that mechanism.
    corroborate_with_tools(kept, tool_signals, path_classes(inventory), config)
    # A tool candidate goes through both filters spec 4.7 step 7 names, unlike a rule
    # finding: rules.py drops disabled-class artefacts before emitting them, and the
    # spec exempts rule findings here for exactly that reason, but ``tools_probe``
    # filters only the vendored and generated classes, so no upstream pass has applied a
    # user's per-path-class disables to a tool signal. Without this, a
    # ``tests: {disable: [security]}`` -- the natural way to stop gitleaks reporting
    # fixture credentials -- would be silently ignored.
    for cand in tool_cands:
        family = str(cand["family"])
        stats.setdefault(family, _new_stats())
        if _suppressed(cand, config, day):
            stats[family]["suppressed"] += 1
            continue
        path_class = str(cand["signals"]["path_class"] or "source")
        if family in disabled_families(config, path_class):
            stats[family]["disabled"] += 1
            continue
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
