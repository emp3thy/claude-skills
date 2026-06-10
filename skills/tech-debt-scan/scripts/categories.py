"""Eight fixed, language-agnostic scout-category prompts for tech-debt-scan.

Data-only module. Each scout is dispatched (via the Agent tool, read-only
Explore semantics) with one category prompt. Every prompt is written without
reference to any single language's syntax so the same scan works on a Python,
C#, TypeScript, Go, or mixed repository.

Each prompt ends with the shared ScoutFinding JSON output contract so the
synthesis step receives a uniform shape regardless of category. The contract
carries three classification axes on top of the category:

  - ``debt_type``  — taxonomy bucket (SATD / Alves-derived) for reporting
  - ``effort``     — S/M/L tractability estimate, used by the ranking step
  - ``confidence`` — how sure the scout is the evidence is real debt

Scouts also receive hotspot guidance: the inventory ranks files by churn x
complexity, and debt located in a hotspot accrues interest fastest (the team
keeps paying it on every change), so it outranks equally-bad debt in cold code.
"""
from __future__ import annotations

from typing import Final

# Shared output contract appended to every category prompt. Keys here MUST match
# the raw-findings shape consumed by build_synthesis_prompt.py: title, severity,
# category, debt_type, effort, confidence, evidence (list of {file, line, note}),
# suggested_fix.
_OUTPUT_SCHEMA: Final[str] = """
You have READ-ONLY access to the repository (Explore-agent semantics): you may
read and search files but must not modify anything.

The inventory JSON you were given includes per-file `churn` (commits in the
recent window), `complexity` (indentation-based proxy), and a `hotspots` list
ranking files by churn x complexity. Debt in a hotspot file is paid on every
change the team makes there — treat hotspot location as a severity amplifier
(+1, capped at 5) and say so in the evidence note. Debt in code nobody has
touched for years usually deserves a lower severity than it first appears.

Severity rubric (apply consistently):
  5 = active correctness, security, data-loss, or money risk right now
  4 = materially slows or endangers most changes in its area (or 3 + hotspot)
  3 = recurring friction the team pays regularly
  2 = localized annoyance, rarely on the change path
  1 = cosmetic

Emit a JSON array. Each element is one finding with exactly these keys:

  {
    "title": "<=80 chars, one-line summary",
    "severity": 1-5 integer (5 = most damaging, per the rubric above),
    "category": "<this category name>",
    "debt_type": "one of: code, design, architecture, test, documentation,
                  dependency, build, requirement",
    "effort": "S" (under half a day) | "M" (up to ~2 days) | "L" (larger, needs its own plan),
    "confidence": "low" | "medium" | "high" (how sure the evidence is real debt, not intentional),
    "evidence": [{"file": "relative/path", "line": 123, "note": "what is wrong here"}],
    "suggested_fix": "<=500 chars describing the remediation"
  }

Return [] (an empty array) if you find nothing for this category. Do not invent
findings to fill the list. Cap titles at 80 characters and suggested_fix at 500.
"""


CATEGORY_PROMPTS: Final[dict[str, str]] = {
    "god-modules": (
        "You are scanning for GOD MODULES: single files or units that carry far "
        "too much responsibility. Signals to look for:\n"
        "- Files well over 400 lines, or far larger than the repo's typical file.\n"
        "- A single type/class/module mixing unrelated concerns (I/O, business "
        "rules, presentation, persistence all in one place).\n"
        "- Functions or methods with very high branching depth or many parameters.\n"
        "- A file referenced by almost everything (a hub everything depends on).\n"
        "Start from the inventory's hotspots list: a god module that is also a "
        "hotspot is the single highest-interest debt a repo can carry.\n"
        "Prefer the largest, most-coupled offenders; severity tracks size x reach."
        + _OUTPUT_SCHEMA
    ),
    "duplication": (
        "You are scanning for DUPLICATION: the same logic copy-pasted in multiple "
        "places. Signals to look for:\n"
        "- Identical or near-identical blocks repeated across files.\n"
        "- Parallel functions that differ only in a constant or a type name.\n"
        "- Repeated literal values (paths, magic numbers, format strings) that "
        "should be a single shared constant.\n"
        "- Copies of the same validation, parsing, or formatting routine.\n"
        "Severity tracks how many copies exist and how likely they are to drift; "
        "copies that sit in high-churn files drift fastest."
        + _OUTPUT_SCHEMA
    ),
    "dead-code": (
        "You are scanning for DEAD CODE: code that is never reached or never used. "
        "Signals to look for:\n"
        "- Functions, types, or files defined but referenced nowhere.\n"
        "- Unreachable branches (conditions that can never be true, code after an "
        "unconditional return/throw).\n"
        "- Commented-out blocks left in place instead of deleted.\n"
        "- Feature flags or config switches that are always one value.\n"
        "Files with zero churn across the window plus no inbound references are "
        "strong candidates — cite the churn figure in the evidence.\n"
        "Be conservative: public API surfaces and entry points are not dead even "
        "when no in-repo caller exists. Use the confidence field honestly; mark "
        "anything you could not trace end-to-end as low or medium."
        + _OUTPUT_SCHEMA
    ),
    "test-gaps": (
        "You are scanning for TEST GAPS: important behaviour with no automated "
        "coverage. Signals to look for:\n"
        "- Core modules or critical paths with no corresponding test file.\n"
        "- Error-handling and edge-case branches that no test exercises.\n"
        "- Tests that assert nothing meaningful (no assertions, or only that code "
        "ran without error).\n"
        "- High-churn or hotspot files that lack regression tests — these are the "
        "riskiest gaps because the code keeps changing without a safety net.\n"
        "Severity tracks the blast radius of the untested behaviour."
        + _OUTPUT_SCHEMA
    ),
    "doc-drift": (
        "You are scanning for DOC DRIFT: documentation that no longer matches the "
        "code. Signals to look for:\n"
        "- README or usage docs describing flags, commands, or options the code no "
        "longer accepts (or missing ones it does).\n"
        "- Stale code comments contradicting the surrounding implementation.\n"
        "- Examples or snippets that would fail if run as written.\n"
        "- API or schema docs out of sync with the actual signatures.\n"
        "Severity tracks how misleading the drift is to a reader following the doc."
        + _OUTPUT_SCHEMA
    ),
    "half-finished": (
        "You are scanning for HALF-FINISHED WORK: incomplete or abandoned changes, "
        "including self-admitted technical debt. Signals to look for:\n"
        "- TODO / FIXME / HACK / XXX / WORKAROUND markers describing unfinished "
        "work — weigh ones that name a concrete risk or a date over vague notes.\n"
        "- Stub functions that return a placeholder or raise 'not implemented'.\n"
        "- Branches behind a flag that was never enabled, or scaffolding never "
        "wired up.\n"
        "- Partially migrated patterns (old and new approach coexisting — count "
        "how many call sites still sit on the old side).\n"
        "Severity tracks how much risk the unfinished state carries for users."
        + _OUTPUT_SCHEMA
    ),
    "dependency-debt": (
        "You are scanning for DEPENDENCY DEBT: third-party and platform "
        "liabilities. Inspect manifests and lockfiles (package.json, *.csproj, "
        "pyproject.toml, requirements*.txt, go.mod, Cargo.toml, Gemfile, and "
        "their lock counterparts). Signals to look for:\n"
        "- Dependencies pinned far behind their current major version, or to a "
        "version with known end-of-life or security advisories you can identify.\n"
        "- Abandoned or archived packages still in the dependency list.\n"
        "- Two or more packages doing the same job (duplicate HTTP clients, "
        "duplicate date libraries).\n"
        "- Vendored or copy-pasted library code that has diverged from upstream.\n"
        "- Usage of APIs the dependency itself marks deprecated.\n"
        "- Manifest vs lockfile drift, or a missing lockfile entirely.\n"
        "Severity tracks exposure: a stale framework underneath everything beats "
        "a stale dev-only tool. Mark advisory claims you cannot verify as "
        "low confidence rather than asserting them."
        + _OUTPUT_SCHEMA
    ),
    "architecture": (
        "You are scanning for ARCHITECTURE DEBT: structural problems above the "
        "single-file level. Signals to look for:\n"
        "- Circular dependencies between modules or packages.\n"
        "- Layering violations (presentation reaching straight into persistence, "
        "domain logic depending on UI or framework types).\n"
        "- Shotgun surgery: one concept smeared across many files so a single "
        "change fans out everywhere — co-changing files in the churn data are "
        "the tell.\n"
        "- Unstable hubs: modules with both high fan-in and high fan-out that "
        "everything breaks through.\n"
        "- Missing seams: side-effectful code (network, clock, filesystem) woven "
        "directly through logic so nothing can be tested in isolation.\n"
        "- Configuration or feature-flag sprawl with no single owner.\n"
        "Severity tracks how much the structure taxes every future change, not "
        "how ugly it looks. These fixes are usually effort L — say so honestly."
        + _OUTPUT_SCHEMA
    ),
}

CATEGORIES: Final[tuple[str, ...]] = tuple(CATEGORY_PROMPTS)

# The default scan dispatches every category. A quick scan (see SKILL.md) can
# dispatch a subset; CORE_CATEGORIES is the recommended minimum.
CORE_CATEGORIES: Final[tuple[str, ...]] = (
    "god-modules",
    "duplication",
    "test-gaps",
    "half-finished",
)


def get_prompt(name: str) -> str:
    """Return the scout prompt for one category.

    Raises KeyError if name is not one of CATEGORIES.
    """
    return CATEGORY_PROMPTS[name]
