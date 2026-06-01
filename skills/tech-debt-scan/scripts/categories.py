"""Six fixed, language-agnostic scout-category prompts for tech-debt-scan.

Data-only module. Each scout is dispatched (via the Agent tool, read-only
Explore semantics) with one category prompt. Every prompt is written without
reference to any single language's syntax so the same scan works on a Python,
C#, TypeScript, Go, or mixed repository.

Each prompt ends with the shared ScoutFinding JSON output contract so the
synthesis step receives a uniform shape regardless of category.
"""
from __future__ import annotations

from typing import Final

# Shared output contract appended to every category prompt. Keys here MUST match
# the raw-findings shape consumed by build_synthesis_prompt.py: title, severity,
# category, evidence (list of {file, line, note}), suggested_fix.
_OUTPUT_SCHEMA: Final[str] = """
You have READ-ONLY access to the repository (Explore-agent semantics): you may
read and search files but must not modify anything.

Emit a JSON array. Each element is one finding with exactly these keys:

  {
    "title": "<=80 chars, one-line summary",
    "severity": 1-5 integer (5 = most damaging),
    "category": "<this category name>",
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
        "- A file imported or referenced by almost everything (a hub everything "
        "depends on).\n"
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
        "Severity tracks how many copies exist and how likely they are to drift."
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
        "Be conservative: public API surfaces and entry points are not dead even "
        "when no in-repo caller exists. Note the uncertainty in the evidence."
        + _OUTPUT_SCHEMA
    ),
    "test-gaps": (
        "You are scanning for TEST GAPS: important behaviour with no automated "
        "coverage. Signals to look for:\n"
        "- Core modules or critical paths with no corresponding test file.\n"
        "- Error-handling and edge-case branches that no test exercises.\n"
        "- Tests that assert nothing meaningful (no assertions, or only that code "
        "ran without error).\n"
        "- Recently changed, high-traffic units that lack regression tests.\n"
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
        "You are scanning for HALF-FINISHED WORK: incomplete or abandoned changes. "
        "Signals to look for:\n"
        "- TODO / FIXME / HACK / XXX markers describing unfinished work.\n"
        "- Stub functions that return a placeholder or raise 'not implemented'.\n"
        "- Branches behind a flag that was never enabled, or scaffolding never "
        "wired up.\n"
        "- Partially migrated patterns (old and new approach coexisting).\n"
        "Severity tracks how much risk the unfinished state carries for users."
        + _OUTPUT_SCHEMA
    ),
}

CATEGORIES: Final[tuple[str, ...]] = tuple(CATEGORY_PROMPTS)


def get_prompt(name: str) -> str:
    """Return the scout prompt for one category.

    Raises KeyError if name is not one of CATEGORIES.
    """
    return CATEGORY_PROMPTS[name]
