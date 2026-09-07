"""Decide which scouts run and render their prompts (spec 2.4, 4.6).

Reads ``inventory.json``, ``coupling.json``, ``patterns.json`` and
``rule-findings.json`` from ``--workdir``, applies the adaptive rule, and writes
``scan-plan.json`` plus one ``prompts/scout-<family>.md`` per dispatched family.
SKILL.md (phase 3) dispatches exactly the plan's entries.

**Chunking** (spec 4.6). When source files exceed ``chunking.max_files`` or
source LOC exceeds ``chunking.max_loc``, the repository is split by top-level
directory and each dispatched family's leads are grouped by the module their
path falls under; a module gets an entry, ``prompts/scout-<family>-<module>.md``,
only where that split leaves it at least one lead (which already covers "or a
hotspot-band file there", since the hotspot band is itself a lead kind). The
thresholds halve when the selected set is ``deep`` -- keyed off the same
``set_name`` value ``_resolve_set`` returns for both ``--families deep`` and a
bare ``--deep`` flag (SKILL.md turns that into ``--families deep`` before this
script runs), so the two spellings cannot select different thresholds. Every
module's filename token comes from one shared, plan-wide ``slugs.unique_slugs``
call, so two top-level directories that collide after slugging still get
distinct prompt paths.

Leads are one union of deterministic signals per family (the table in the phase 2
plan), each kind sorted hotspot-band files first. ``KIND_CAPS`` bounds the
pattern, SATD and inventory leads at ``LEAD_CAP`` each, band files first within
each kind (spec 4.6: "40 per family, hotspot-band first" is said of pattern leads
and tool signals; the SATD table and the per-file inventory leads are unbounded
in the documents and are capped here for the same reason). The hotspot band, the
coupled pairs, the artefacts, the cycles and the docs and tests signals are the
remaining kinds and are emitted in full, the band already bounded by
``hotspot_band.max``. Path-class disables from ``families.per_path_class`` drop
leads before the adaptive rule counts them, and the prompt names the disabled
families.

An inventory lead only counts towards the adaptive rule when the family's primary
metric clears a floor: ``max_indent >= 1`` and ``loc >= 1`` hold for every
non-empty file, so without one complex-units and god-classes would be dispatched
on every repository that has any code at all.

Direct-path invocable: `python plan_scan.py --workdir .tech-debt [--families <set>]`.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from categories import FAMILIES, render_scout_prompt
from config import FAMILY_SETS, ConfigError, load_config
from inventory import write_json
from slugs import unique_slugs

SCHEMA_VERSION: Final[int] = 2
LEAD_CAP: Final[int] = 40
# Spec 4.6 caps pattern leads and tool signals at LEAD_CAP; the SATD table and the
# per-file inventory leads are unbounded in the documents and are capped here for the
# same reason (a TODO-heavy or large repository would otherwise fill the prompt). The
# hotspot band is bounded by hotspot_band.max, and the coupling, artefact, cycle, docs
# and tests kinds are bounded by the repository's own structure, so they are emitted whole.
KIND_CAPS: Final[dict[str, int]] = {
    "pattern": LEAD_CAP, "satd": LEAD_CAP, "inventory": LEAD_CAP, "tool": LEAD_CAP,
}
KIND_ORDER: Final[tuple[str, ...]] = (
    "hotspot", "coupling", "pattern", "satd", "artefact", "cycle", "inventory", "tool", "docs",
    "tests",
)
KIND_TITLE: Final[dict[str, str]] = {
    "hotspot": "Hotspot-band files (score)",
    "coupling": "Change-coupled pairs",
    "pattern": "Pattern leads",
    "satd": "Self-admitted debt markers",
    "artefact": "Artefacts",
    "cycle": "Import cycles (approximate, lead only)",
    "inventory": "Inventory signals",
    "tool": "Tool signals",
    "docs": "Documentation and structure signals",
    "tests": "Test signals",
}


@dataclass(slots=True)
class Lead:
    kind: str
    path: str
    line: int | None
    text: str
    score: float = 0.0


@dataclass(slots=True)
class ScanDocs:
    inventory: dict[str, Any]
    coupling: dict[str, Any] = field(default_factory=dict)
    patterns: dict[str, Any] = field(default_factory=dict)
    rules: dict[str, Any] = field(default_factory=dict)
    tool_signals: dict[str, Any] = field(default_factory=dict)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    loaded = json.loads(path.read_bytes())
    return loaded if isinstance(loaded, dict) else {}


def load_docs(workdir: Path) -> ScanDocs:
    """The four phase 1 documents; a missing ``inventory.json`` is fatal, the rest are optional."""
    inventory = _read_json(workdir / "inventory.json")
    if not inventory:
        raise FileNotFoundError(f"{workdir / 'inventory.json'} not found; run inventory.py first")
    return ScanDocs(
        inventory=inventory,
        coupling=_read_json(workdir / "coupling.json"),
        patterns=_read_json(workdir / "patterns.json"),
        rules=_read_json(workdir / "rule-findings.json"),
        tool_signals=_read_json(workdir / "tool-signals.json"),
    )


# --- path classes and disables ----------------------------------------------------


def _path_classes(docs: ScanDocs) -> dict[str, str]:
    classes = {
        str(e["path"]): str(e.get("path_class", "source")) for e in _files(docs)
    }
    for entries in (docs.inventory.get("artefacts") or {}).values():
        for artefact in entries:
            classes.setdefault(str(artefact["path"]), str(artefact.get("path_class", "source")))
    return classes


def disabled_families(config: dict[str, Any], path_class: str) -> set[str]:
    """The families ``families.per_path_class`` switches off for one path class."""
    rule = (config.get("families", {}).get("per_path_class") or {}).get(path_class) or {}
    disable = rule.get("disable", [])
    if disable == "all":
        return set(FAMILIES)
    return {str(name) for name in disable}


def disabled_note(config: dict[str, Any]) -> str:
    """One line per path class with disables, for the prompt's rules section."""
    lines: list[str] = []
    for path_class in sorted(config.get("families", {}).get("per_path_class") or {}):
        names = disabled_families(config, path_class)
        if not names:
            continue
        label = "all families" if names == set(FAMILIES) else ", ".join(sorted(names))
        lines.append(f"Families disabled on {path_class}: {label}")
    return "\n".join(lines) if lines else "No path-class disables are configured."


# --- lead sources -------------------------------------------------------------------


def _files(docs: ScanDocs) -> list[dict[str, Any]]:
    return [e for e in docs.inventory.get("files", []) if isinstance(e, dict)]


def _source_files(docs: ScanDocs) -> list[dict[str, Any]]:
    return [e for e in _files(docs) if e.get("path_class") == "source"]


def _number(value: Any) -> float | None:
    """A numeric metric value, or None when the field is null or not a number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _band(docs: ScanDocs) -> list[Lead]:
    scores = {str(e["path"]): _number(e.get("hotspot_score")) or 0.0 for e in _files(docs)}
    out: list[Lead] = []
    for raw in docs.inventory.get("hotspot_band", []):
        path = str(raw)
        score = scores.get(path, 0.0)
        out.append(Lead("hotspot", path, None, f"score {score:.2f}", score))
    return out


def _pairs(docs: ScanDocs, *, cross_only: bool = False) -> list[Lead]:
    out: list[Lead] = []
    for pair in docs.coupling.get("pairs", []):
        if cross_only and not pair.get("cross_directory"):
            continue
        text = f"<-> {pair['b']} shared={pair['shared_commits']} ratio={pair['ratio']}"
        out.append(Lead("coupling", str(pair["a"]), None, text, float(pair["ratio"])))
    return out


def _pattern_leads(docs: ScanDocs, family: str, *, rule: str | None = None) -> list[Lead]:
    out: list[Lead] = []
    for item in (docs.patterns.get("leads") or {}).get(family, []):
        if rule is not None and item.get("rule") != rule:
            continue
        out.append(Lead("pattern", str(item["file"]), int(item["line"]),
                        f"{family}:{item['rule']}: {item['quote']}"))
    return out


def _tool_leads(docs: ScanDocs, family: str) -> list[Lead]:
    """Inference-class tool signals for ``family``, as leads (spec 4.6, 4.7).

    Fact-class signals are deliberately excluded: ``merge_findings`` turns
    those into candidates, and a lead as well would put the same fact both in
    front of a scout and in the candidate list. A signal with no file has
    nothing for a scout to open.
    """
    out: list[Lead] = []
    for item in docs.tool_signals.get("signals") or []:
        if not isinstance(item, dict) or item.get("fact"):
            continue
        if str(item.get("family")) != family:
            continue
        path = item.get("file")
        if not isinstance(path, str) or not path:
            continue
        line = item.get("line_start")
        out.append(
            Lead(
                "tool", path, line if isinstance(line, int) else None,
                f"{item.get('tool')}: {item.get('message', '')}",
            )
        )
    return out


def _satd(docs: ScanDocs) -> list[Lead]:
    out: list[Lead] = []
    for item in docs.patterns.get("satd", []):
        text = (f"{item['marker']} age_days={item.get('age_days')} "
                f"ticket={bool(item.get('ticket_ref'))}: {item['quote']}")
        out.append(Lead("satd", str(item["file"]), int(item["line"]), text))
    return out


def _artefacts(docs: ScanDocs, classes: tuple[str, ...]) -> list[Lead]:
    out: list[Lead] = []
    artefacts = docs.inventory.get("artefacts") or {}
    for cls in classes:
        for artefact in artefacts.get(cls, []):
            if artefact.get("skipped_large"):
                continue
            out.append(Lead("artefact", str(artefact["path"]), None, cls))
    return out


def _top_by(
    docs: ScanDocs,
    keys: tuple[str, ...],
    limit: int,
    keep: Callable[[dict[str, Any]], bool],
) -> list[Lead]:
    """The ``limit`` source files ranked by ``keys`` (nulls last) that ``keep`` accepts.

    ``keep`` is the family's floor on its primary metric, not a formality: a
    "any key above zero" test is true of every non-empty file (``max_indent`` and
    ``loc`` are both at least 1 there), which would carry the family past the
    adaptive rule of spec 2.4 on any repository at all.
    """
    def sort_key(entry: dict[str, Any]) -> tuple[float, ...]:
        return tuple(-(_number(entry.get(k)) or 0.0) for k in keys)

    ranked = sorted(_source_files(docs), key=sort_key)[:limit]
    return [
        Lead("inventory", str(e["path"]), None, " ".join(f"{k}={e.get(k)}" for k in keys))
        for e in ranked
        if keep(e)
    ]


def _has_deep_nesting(entry: dict[str, Any]) -> bool:
    """complex-units' floor: a run of nested lines or a line indented past the deep mark."""
    return ((_number(entry.get("longest_indented_run")) or 0.0) > 0
            or (_number(entry.get("deep_indent_lines")) or 0.0) > 0)


def _is_large_or_depended_on(entry: dict[str, Any]) -> bool:
    """god-classes' floor: a file big enough to hide one, or one three files already use."""
    return ((_number(entry.get("loc")) or 0.0) >= 300
            or (_number(entry.get("fan_in_approx")) or 0.0) >= 3)


def _inventory_where(
    docs: ScanDocs, predicate: Callable[[dict[str, Any]], bool], text: str
) -> list[Lead]:
    return [Lead("inventory", str(e["path"]), None, text.format(**e))
            for e in _source_files(docs) if predicate(e)]


def _docs_leads(docs: ScanDocs) -> list[Lead]:
    block = docs.inventory.get("docs") or {}
    out: list[Lead] = []
    for ref in block.get("dangling_refs", []):
        if isinstance(ref, dict):
            out.append(Lead("docs", str(ref.get("file", "README.md")), ref.get("line"),
                            f"dangling: {ref.get('token')}"))
        else:
            out.append(Lead("docs", "README.md", None, f"dangling: {ref}"))
    for doc, days in (block.get("stale_vs_code_days") or {}).items():
        if isinstance(days, int) and not isinstance(days, bool) and days > 0:
            out.append(Lead("docs", str(doc), None, f"stale {days} days behind the code"))
    for flag, label in (("contributing_present", "CONTRIBUTING"),
                        ("adr_dir_present", "ADR directory"),
                        ("changelog_present", "CHANGELOG")):
        if block.get(flag) is False:
            out.append(Lead("docs", "README.md", None, f"missing: {label}"))
    return out


def _cycles(docs: ScanDocs) -> list[Lead]:
    return [Lead("cycle", str(c["members"][0]), None, "members: " + ", ".join(c["members"]))
            for c in docs.coupling.get("cycles", []) if c.get("members")]


def _structure(docs: ScanDocs) -> list[Lead]:
    out = [Lead("docs", str(e["from"]), None,
                f"-> {e['to']} instability {e['from_instability']} "
                f"depends on {e['to_instability']}")
           for e in docs.coupling.get("unstable_edges", [])]
    out += [Lead("docs", str(name), None, "declared: boundary tooling")
            for name in docs.inventory.get("boundary_tooling", [])]
    return out


def _joined(value: Any) -> str:
    """``tests.coverage_gate`` and ``tests.ci_retry_config`` are lists of artefact paths."""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def _untested(entry: dict[str, Any]) -> bool:
    share = _number(entry.get("untested_change_share"))
    return share is not None and share >= 0.5


def _tests_leads(docs: ScanDocs) -> list[Lead]:
    band = set(docs.inventory.get("hotspot_band", []))
    out = [Lead("tests", str(e["path"]), None, "no mapped test")
           for e in _source_files(docs) if e["path"] in band and not e.get("mapped_tests")]
    out += _inventory_where(docs, _untested, "untested_change_share={untested_change_share}")
    out += _pattern_leads(docs, "half-finished", rule="skip-marker")
    gate = (docs.inventory.get("tests") or {}).get("coverage_gate")
    if gate:
        out.append(Lead("tests", "coverage", None, f"coverage_gate: {_joined(gate)}"))
    return out


def _test_quality_extras(docs: ScanDocs) -> list[Lead]:
    out: list[Lead] = []
    retry = (docs.inventory.get("tests") or {}).get("ci_retry_config")
    if retry:
        out.append(Lead("tests", "ci", None, f"ci_retry_config: {_joined(retry)}"))
    out += _inventory_where(docs, lambda e: (_number(e.get("flaky_commits")) or 0.0) > 0,
                            "flaky_commits={flaky_commits}")
    return out


def _migration_rule_leads(docs: ScanDocs) -> list[Lead]:
    return [
        Lead("artefact", str(item["file"]), item.get("line"),
             f"{item['rule']}: {item['quote']}")
        for item in (docs.rules.get("leads") or {}).get("migration", [])
    ]


def _raw_leads(family: str, docs: ScanDocs) -> list[Lead]:
    if family == "complex-units":
        return (_band(docs) + _top_by(
            docs, ("longest_indented_run", "deep_indent_lines", "max_indent"), 10,
            _has_deep_nesting) + _tool_leads(docs, family))
    if family == "god-classes":
        return (_band(docs)
                + _top_by(docs, ("loc", "fan_in_approx"), 10, _is_large_or_depended_on)
                + _pairs(docs) + _tool_leads(docs, family))
    if family == "duplication":
        return _band(docs) + _pairs(docs) + _tool_leads(docs, family)
    if family == "dead-code":
        dead = _inventory_where(
            docs,
            lambda e: e.get("fan_in_approx") == 0 and (_number(e.get("churn")) or 0.0) == 0,
            "fan_in=0 churn=0",
        )
        return (
            _band(docs) + dead + _pattern_leads(docs, "dead-code")
            + _tool_leads(docs, family)
        )
    if family == "error-masking":
        return (
            _band(docs) + _pattern_leads(docs, "error-masking") + _tool_leads(docs, family)
        )
    if family == "test-gaps":
        return _band(docs) + _tests_leads(docs) + _tool_leads(docs, family)
    if family == "half-finished":
        return (_band(docs) + _satd(docs) + _pattern_leads(docs, "half-finished")
                + _tool_leads(docs, family))
    if family == "migration":
        moved = _inventory_where(
            docs, lambda e: (_number(e.get("migration_commits")) or 0.0) > 0,
            "migration_commits={migration_commits}"
        )
        return (
            _band(docs) + moved + _migration_rule_leads(docs) + _pairs(docs)
            + _tool_leads(docs, family)
        )
    if family == "dependency-debt":
        return (
            _artefacts(docs, ("manifest", "lockfile", "runtime_version", "governance"))
            + _tool_leads(docs, family)
        )
    if family == "doc-drift":
        return _docs_leads(docs) + _tool_leads(docs, family)
    if family == "architecture":
        return (_band(docs) + _cycles(docs) + _pairs(docs, cross_only=True) + _structure(docs)
                + _tool_leads(docs, family))
    if family == "security":
        return _pattern_leads(docs, "security") + _tool_leads(docs, family)
    if family == "test-quality":
        return (
            _pattern_leads(docs, "test-quality") + _test_quality_extras(docs)
            + _tool_leads(docs, family)
        )
    if family == "pipeline-infra":
        return (_pattern_leads(docs, "pipeline-infra")
                + _artefacts(docs, ("ci", "container", "iac"))
                + _tool_leads(docs, family))
    raise KeyError(family)


def leads_for(family: str, docs: ScanDocs, config: dict[str, Any]) -> list[Lead]:
    """Filtered, ordered leads for one family (hotspot-band first, then path).

    ``KIND_CAPS`` bounds the pattern, SATD and inventory leads at ``LEAD_CAP``
    each, band files first within each kind (a kind absent from ``KIND_CAPS`` is
    uncapped). Spec 4.6 says "40 per family, hotspot-band first" of the pattern
    leads and tool signals; the SATD table and the per-file inventory leads are
    unbounded in the documents and are capped here for the same reason. Capping
    per kind rather than the whole block kept together is kind-major, so a
    repository with 40 or more band files (``hotspot_band.max`` is 50) would
    otherwise send a prompt of band lines and no pattern leads at all.
    """
    classes = _path_classes(docs)
    band = set(docs.inventory.get("hotspot_band", []))
    kept = [
        lead for lead in _raw_leads(family, docs)
        if family not in disabled_families(config, classes.get(lead.path, "source"))
    ]
    kept.sort(key=lambda lead: (
        KIND_ORDER.index(lead.kind), lead.path not in band, -lead.score, lead.path, lead.line or 0,
    ))
    out: list[Lead] = []
    counts: dict[str, int] = {}
    for lead in kept:
        cap = KIND_CAPS.get(lead.kind)
        if cap is not None:
            if counts.get(lead.kind, 0) >= cap:
                continue
            counts[lead.kind] = counts.get(lead.kind, 0) + 1
        out.append(lead)
    return out


def render_leads(leads: list[Lead]) -> str:
    """One section per kind present, in ``KIND_ORDER``; ``- <path>[:<line>] <text>`` lines."""
    if not leads:
        return "(no deterministic leads for this family; read the hotspot band and the tree)\n"
    lines: list[str] = []
    current = ""
    for lead in leads:
        if lead.kind != current:
            current = lead.kind
            lines.append(f"{KIND_TITLE[current]}:")
        where = f"{lead.path}:{lead.line}" if lead.line is not None else lead.path
        lines.append(f"- {where} {lead.text}")
    return "\n".join(lines) + "\n"


# --- plan -----------------------------------------------------------------------------


def _resolve_set(config: dict[str, Any], families: str | list[str] | None) -> tuple[str, list[str]]:
    requested: str | list[str] = (
        config["families"]["enabled"] if families is None else families
    )
    if isinstance(requested, list):
        unknown = [f for f in requested if f not in FAMILIES]
        if unknown:
            raise ConfigError(f"unknown families: {unknown}")
        return "explicit", [f for f in FAMILIES if f in requested]
    if "," in requested:
        return _resolve_set(config, [f.strip() for f in requested.split(",") if f.strip()])
    # A bare family name is a list of one: no set is named after a family, so
    # ``--families security`` can only mean the explicit list ``[security]``.
    if requested in FAMILIES:
        return _resolve_set(config, [requested])
    if requested not in FAMILY_SETS:
        raise ConfigError(f"families must be default, quick, deep or a list, got {requested!r}")
    return requested, list(FAMILY_SETS[requested])


def _repo_summary(inventory: dict[str, Any]) -> str:
    languages = ", ".join(str(lang) for lang in inventory.get("languages", [])) or "none detected"
    git = "yes" if inventory.get("git_available") else "no"
    return (f"root: {inventory.get('root')}, {inventory.get('total_files')} files, "
            f"{inventory.get('total_loc')} LOC, languages: {languages}; git: {git}")


# --- chunking (spec 4.6) ----------------------------------------------------------------


def _chunk_thresholds(config: dict[str, Any], set_name: str) -> dict[str, int]:
    """``chunking.max_files``/``max_loc``, halved when ``set_name`` is ``deep``.

    ``set_name`` is the value ``_resolve_set`` already returns for both
    ``--families deep`` and a bare ``--deep`` flag (SKILL.md turns that into
    ``--families deep`` before this script ever runs), so the halving keys off
    the selected set rather than off argv, and the two spellings cannot diverge.
    """
    base = {"max_files": int(config["chunking"]["max_files"]),
            "max_loc": int(config["chunking"]["max_loc"])}
    if set_name != "deep":
        return base
    return {"max_files": base["max_files"] // 2, "max_loc": base["max_loc"] // 2}


def _is_chunked(docs: ScanDocs, thresholds: dict[str, int]) -> bool:
    """True when source files or source LOC exceed either threshold."""
    source = _source_files(docs)
    total_loc = sum(int(_number(e.get("loc")) or 0) for e in source)
    return len(source) > thresholds["max_files"] or total_loc > thresholds["max_loc"]


def _module_of(path: str) -> str:
    """The top-level directory ``path`` lives under; ``"root"`` for a repo-root file."""
    head, sep, _ = path.partition("/")
    return head if sep else "root"


def _leads_by_module(leads: list[Lead]) -> dict[str, list[Lead]]:
    """``leads``, grouped by ``_module_of`` its path, each group in its original order."""
    by_module: dict[str, list[Lead]] = {}
    for lead in leads:
        by_module.setdefault(_module_of(lead.path), []).append(lead)
    return by_module


def build_plan(
    workdir: Path,
    config: dict[str, Any],
    *,
    families: str | list[str] | None,
    top: int | None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """The scan-plan document and every rendered prompt keyed by its relative path."""
    docs = load_docs(workdir)
    set_name, wanted = _resolve_set(config, families)
    explicit = set_name == "explicit"
    disabled = {str(name) for name in config["families"].get("disabled", [])}
    summary = _repo_summary(docs.inventory)
    note = disabled_note(config)
    thresholds = _chunk_thresholds(config, set_name)
    chunked = _is_chunked(docs, thresholds)

    # One pass to decide, per family, whether it is dispatched at all and what its
    # repo-wide leads are; a chunked plan then splits those leads by module below.
    # This dict preserves FAMILIES order (insertion order), so both the entries
    # list and families_run stay ordered exactly as the unchunked path already is.
    family_leads: dict[str, list[Lead]] = {}
    skipped: list[dict[str, str]] = []
    for family in FAMILIES:
        if family in disabled:
            skipped.append({"family": family, "reason": "disabled"})
            continue
        if family not in wanted:
            skipped.append({"family": family, "reason": "not in set"})
            continue
        leads = leads_for(family, docs, config)
        if not leads and not explicit:
            skipped.append({"family": family, "reason": "no leads"})
            continue
        family_leads[family] = leads

    # One slug per module, shared across every family: unique_slugs guarantees the
    # mapping is injective, so two top-level directories that collide after
    # slugging (e.g. "foo_bar" and "foo-bar") still get distinct filename tokens,
    # and the same directory always gets the same token in every family's prompt.
    module_slug: dict[str, str] = {}
    if chunked:
        modules = sorted({
            _module_of(lead.path) for leads in family_leads.values() for lead in leads
        })
        module_slug = dict(zip(modules, unique_slugs(modules), strict=True))

    entries: list[dict[str, Any]] = []
    prompts: dict[str, str] = {}
    for family, leads in family_leads.items():
        if chunked and leads:
            for module, subset in sorted(_leads_by_module(leads).items()):
                token = module_slug[module]
                prompt_path = f"prompts/scout-{family}-{token}.md"
                module_summary = f"{summary}; chunked scan scoped to top-level directory " \
                                  f"'{module}' only"
                prompts[prompt_path] = render_scout_prompt(
                    family, repo_summary=module_summary, leads_block=render_leads(subset),
                    scout_cap=int(config["scout_cap"]), disabled_note=note,
                )
                entries.append({"family": family, "module": module, "prompt": prompt_path,
                                "output": f"scouts/{family}-{token}.json", "leads": len(subset)})
        else:
            prompt_path = f"prompts/scout-{family}.md"
            prompts[prompt_path] = render_scout_prompt(
                family, repo_summary=summary, leads_block=render_leads(leads),
                scout_cap=int(config["scout_cap"]), disabled_note=note,
            )
            entries.append({"family": family, "module": None, "prompt": prompt_path,
                            "output": f"scouts/{family}.json", "leads": len(leads)})

    plan: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "set": set_name,
        "top": int(top if top is not None else config["top"]),
        "chunked": chunked,
        "thresholds": thresholds,
        "entries": entries,
        "families_run": [f for f in FAMILIES if f in family_leads],
        "families_skipped": skipped,
    }
    return plan, prompts


def write_plan(workdir: Path, plan: dict[str, Any], prompts: dict[str, str]) -> None:
    """LF-only prompt files under ``prompts/`` and the plan document.

    ``scouts/`` is created here even when it stays empty: each entry's ``output``
    points into it, and phase 3 dispatches an agent that writes there.
    """
    for rel, text in prompts.items():
        target = workdir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))
    (workdir / "scouts").mkdir(parents=True, exist_ok=True)
    write_json(workdir / "scan-plan.json", plan)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan the scout dispatch and render its prompts")
    parser.add_argument("--workdir", default=".tech-debt",
                        help="directory holding the signal files")
    parser.add_argument("--families", default=None,
                        help="default, quick, deep or a comma-separated list (default: config)")
    parser.add_argument("--top", type=int, default=None,
                        help="findings to report (default: config)")
    args = parser.parse_args(argv)
    workdir = Path(args.workdir)
    try:
        docs = load_docs(workdir)
        config = load_config(Path(str(docs.inventory.get("root", "."))))
        plan, prompts = build_plan(workdir, config, families=args.families, top=args.top)
    # OSError covers a missing or unreadable signal file (FileNotFoundError is one);
    # ValueError covers a signal file that is not JSON; KeyError covers a document
    # missing a field a lead source reads.
    except (ConfigError, OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    write_plan(workdir, plan, prompts)
    print(f"planned {len(plan['entries'])} scout(s); skipped {len(plan['families_skipped'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
