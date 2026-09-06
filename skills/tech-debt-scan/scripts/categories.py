"""Scout prompts: the fourteen v2 family blocks and their shared contract (spec 2.3, 4.6).

Data-only module. Each scout is dispatched (via the Agent tool, read-only
Explore semantics) with one family's rendered prompt. Every prompt is written
without reference to any single language's syntax so the same scan works on a
Python, C#, TypeScript, Go, or mixed repository.

``render_scout_prompt`` assembles a prompt from one ``FamilyBlock`` plus the
shared ``SEVERITY_RUBRIC``, ``NEVER_ASSERT`` and ``SCOUT_OUTPUT_CONTRACT``, so
every reply carries a uniform shape regardless of family; ``SCOUT_OUTPUT_SCHEMA``
is the same contract as a JSON schema, for the structured-output flag. A finding
carries ``debt_type`` (taxonomy bucket, SATD / Alves-derived) and ``effort``
(S/M/L tractability, used by ranking) -- and no certainty self-report: tiering is
the verifier's job, not the scout's.

Scouts also receive hotspot guidance: the inventory ranks files by churn x
complexity, and debt located in a hotspot accrues interest fastest (the team
keeps paying it on every change), so it outranks equally-bad debt in cold code.

Spec 3.2: the eight v1 categories (``CATEGORY_PROMPTS``, ``CATEGORIES``,
``CORE_CATEGORIES``, ``get_prompt`` and their ``_OUTPUT_SCHEMA``) were deleted in
phase 3 along with their only consumers, ``build_synthesis_prompt.py`` and
SKILL.md v1. A v1 ``design.md`` still promotes: its ``category`` value is read as
``family`` by ``design_parser``, which never reads a scout prompt.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final


@dataclass(frozen=True, slots=True)
class FamilyBlock:
    """One family's scout block: what to look for, what to distrust, what it may emit."""

    definition: str
    questions: tuple[str, ...]
    traps: tuple[str, ...]
    type_ids: tuple[str, ...]
    debt_types: tuple[str, ...]
    verifier_questions: tuple[str, ...]


FAMILIES: Final[tuple[str, ...]] = (
    "complex-units", "god-classes", "duplication", "dead-code", "error-masking",
    "test-gaps", "half-finished", "migration", "dependency-debt", "doc-drift",
    "architecture", "security", "test-quality", "pipeline-infra",
)

SEVERITY_RUBRIC: Final[str] = """Severity rubric (apply consistently; location is scored later
by a script, not by you):
  5 = active correctness, security, data-loss, or money risk right now
  4 = materially slows or endangers most changes in its area
  3 = recurring friction the team pays regularly
  2 = localized annoyance, rarely on the change path
  1 = cosmetic"""

NEVER_ASSERT: Final[str] = """Never assert any of these without a tool fact you were given:
test coverage numbers, CVE or vulnerability status, end-of-life or currency of a dependency,
library-level deprecation, test flakiness, exploitability of a security pattern. Put such
claims under "not_assessed"."""

FAMILY_BLOCKS: Final[dict[str, FamilyBlock]] = {
    "complex-units": FamilyBlock(
        definition=(
            "COMPLEX UNITS: single functions, methods or blocks whose branching and nesting make "
            "them hard to change safely. Deep indentation runs and long indented spans in the "
            "leads are the deterministic signal; confirm by reading the unit."
        ),
        questions=(
            "Does the cited span show the branching the lead claims (nested conditions, "
            "long chains)?",
            "Is the unit on a change path (a hotspot-band file or a coupled pair), or cold?",
            "Is the size a symptom of mixed responsibilities that a split would separate?",
            "Would a table, a state machine or a strategy remove the branching?",
        ),
        traps=(
            "A large lookup table, a generated switch or a declarative state machine is long "
            "but cohesive.",
            "Generated or vendored code is not a finding.",
        ),
        type_ids=("TD-01",),
        debt_types=("code", "design"),
        verifier_questions=(
            "Large but cohesive (table, state machine, generated)?",
            "Does the span show the branching claimed?",
            "Is the unit on a change path?",
        ),
    ),
    "god-classes": FamilyBlock(
        definition=(
            "GOD CLASSES: a type, module or file that owns too many reasons to change, plus "
            "inappropriate intimacy (reaching into another unit's internals) and long message "
            "chains. Size, approximate fan-in and coupled pairs in the leads point at candidates."
        ),
        questions=(
            "Does the unit have more than one reason to change? Name the responsibilities.",
            "Do its methods cluster over disjoint sets of fields (two classes in one)?",
            "Is it a hub that most of the repository reaches for?",
            "Does a caller chain through several objects to reach data it should be handed?",
        ),
        traps=(
            "A facade, a DTO, a fluent builder or a thin controller is wide by design.",
            "A large file that is one cohesive concept is a complex-units question, not this one.",
        ),
        type_ids=("TD-11", "TD-20"),
        debt_types=("design", "code"),
        verifier_questions=(
            "One reason to change?",
            "Do methods cluster over disjoint fields?",
            "Facade, DTO or fluent builder trap?",
        ),
    ),
    "duplication": FamilyBlock(
        definition=(
            "DUPLICATION: the same logic in two or more places that must change together. Coupled "
            "pairs in the leads are the change-history signal; tool clone reports arrive when a "
            "clone detector is installed."
        ),
        questions=(
            "Are the copies changed together in history (a coupled pair) or by a tool report?",
            "Do the copies differ only in a constant, a type name or a message?",
            "Would one shared abstraction be simpler than the copies, or would it couple "
            "unrelated code?",
            "How many copies exist and how far apart do they sit?",
        ),
        traps=(
            "Fixture, generated and vendored duplication is intentional.",
            "Repeated literal values alone (magic numbers, strings) are not this family.",
            "Two similar-looking units with different reasons to change are not duplicates.",
        ),
        type_ids=("TD-05",),
        debt_types=("code",),
        verifier_questions=(
            "Copies change-coupled or tool-confirmed?",
            "Path class fixture, generated, vendored?",
            "Would a shared abstraction be simpler than the copies?",
        ),
    ),
    "dead-code": FamilyBlock(
        definition=(
            "DEAD CODE: units with no callers, unreachable branches, commented-out code left in "
            "place, legacy-named leftovers, deprecated units still present, and feature flags that "
            "only ever take one value. Zero approximate fan-in with zero churn on an ordinary "
            "module is the deterministic signal; pattern leads mark the textual cases."
        ),
        questions=(
            "Which dynamic-reference patterns did you check: reflection, string dispatch, "
            "routes, dependency injection, serialisation?",
            "Is the file an entry point, a script run by name, or a test a runner discovers "
            "by convention?",
            "Is the unit part of a public or plugin surface that external code may call?",
            "For a flag: is it a permission, a kill switch, or genuinely permanently off?",
            "For a deprecated unit: does anything in the repository still call it?",
        ),
        traps=(
            "Entry points and runner-discovered tests have no in-repository caller and are alive.",
            "A documented kill switch is deliberately always-on.",
            "A middle-man class that exists for a documented reason.",
        ),
        type_ids=("TD-09", "TD-30", "TD-17", "TD-20"),
        debt_types=("code",),
        verifier_questions=(
            "Which dynamic-reference patterns were checked (reflection, string dispatch, "
            "routes, DI, serialisation)?",
            "Entry point, script run by name, or runner-discovered test?",
            "Public or plugin surface?",
            "Flag is permission or kill-switch?",
        ),
    ),
    "error-masking": FamilyBlock(
        definition=(
            "ERROR MASKING: failures caught and hidden, so nobody learns of them. Empty catch "
            "blocks, catch-everything variants, log-only catches that drop the cause, and "
            "disabled assertions. Pattern leads give the candidate sites; read each body."
        ),
        questions=(
            "What failure is hidden, and who or what would otherwise learn of it?",
            "Is the catch a process boundary, a retry that re-raises, or a cleanup block "
            "(all acceptable)?",
            "When the error is re-thrown or logged, is the cause preserved?",
            "Do assertions still run in the configuration the leads show?",
        ),
        traps=(
            "A catch at a process or request boundary that reports and continues is correct.",
            "A retry loop that re-raises after the last attempt is not masking.",
        ),
        type_ids=("TD-13",),
        debt_types=("code", "defect"),
        verifier_questions=(
            "What failure is hidden and who learns of it?",
            "Process boundary, retry that re-raises, or cleanup block?",
            "Cause preserved on rethrow?",
        ),
    ),
    "test-gaps": FamilyBlock(
        definition=(
            "TEST GAPS: behaviour that changes often with no automated test guarding it. "
            "Hotspot-band files with no mapped test, a high untested-change share, skip "
            "markers and a missing coverage gate are the leads."
        ),
        questions=(
            "Which test paths did you search, and by what naming conventions?",
            "Is there an unconventionally named test that the mapping missed?",
            "Does the mapped test assert behaviour, or only that code ran?",
            "What is the blast radius of the untested behaviour if it regresses?",
        ),
        traps=(
            "A file exercised through an integration or end-to-end suite has coverage the "
            "mapping cannot see.",
            "Glue, configuration and generated code rarely need unit tests.",
        ),
        type_ids=("TD-04",),
        debt_types=("test",),
        verifier_questions=(
            "Which test paths were searched?",
            "Is there an unconventionally named test?",
            "Does the mapped test assert behaviour?",
        ),
    ),
    "half-finished": FamilyBlock(
        definition=(
            "HALF-FINISHED WORK: self-admitted debt markers, stubs that raise or return "
            "placeholders, expected-failure and skip markers, known-bug notes, and calls that "
            "wait forever (no timeout). The SATD list carries each marker's age and whether a "
            "ticket is referenced."
        ),
        questions=(
            "Does the marker name a concrete risk, a date or a ticket, or is it vague?",
            "Is the stub an abstract contract that subclasses fill (not debt) or an "
            "unimplemented path?",
            "Is the named risk still present in the code next to the marker?",
            "For a call without a timeout: what waits when the remote never answers?",
        ),
        traps=(
            "Abstract methods and interface contracts raise not-implemented on purpose.",
            "A marker that documents a deliberate, ticketed deferral is process working as "
            "intended.",
        ),
        type_ids=("TD-22", "TD-28", "TD-32", "TD-34"),
        debt_types=("code", "requirement", "defect"),
        verifier_questions=(
            "Stub is an abstract contract?",
            "Ticket tracks it?",
            "Named risk still present in the code?",
        ),
    ),
    "migration": FamilyBlock(
        definition=(
            "MIGRATION DEBT: two ways of doing one thing coexisting, an old idiom still called "
            "after its replacement landed, and superseded configuration kept beside its "
            "successor. Naming hints, migration commits, dual-manifest leads and deprecation "
            "annotations point at candidates."
        ),
        questions=(
            "Which side has churn: the old, the new, both or neither?",
            "What share of call sites still sit on the old side? Cite the count.",
            "Is the dual arrangement a deliberate multi-backend design?",
            "Is there a plan, ticket or date for finishing the move?",
        ),
        traps=(
            "Deliberate multi-backend or adapter designs keep two paths on purpose.",
            "A compatibility shim with a stated removal date is a finished decision.",
        ),
        type_ids=("TD-06", "TD-17"),
        debt_types=("design", "dependency", "build"),
        verifier_questions=(
            "Churn on old side, new side, both or neither?",
            "Deliberate multi-backend?",
            "Call-site ratio cited?",
        ),
    ),
    "dependency-debt": FamilyBlock(
        definition=(
            "DEPENDENCY DEBT, structural only: manifests without a lockfile or with two "
            "lockfile kinds, two packages doing one job, floating version ranges inside a "
            "library, vendored copies of libraries, and a runtime version file that disagrees "
            "with the manifest. Read the manifest, lockfile, runtime-version and governance "
            "artefacts in the leads."
        ),
        questions=(
            "Is the lockfile missing, or elsewhere (a monorepo root)?",
            "Do two dependencies serve the same purpose (two HTTP clients, two date libraries)?",
            "Is a floating range declared inside a library that others consume?",
            "Does a vendored copy diverge from an upstream that is also declared?",
        ),
        traps=(
            "A library manifest without a lockfile is normal; an application manifest "
            "without one is not.",
            "A duplicate-purpose pair with churn on one side is a migration, not a "
            "dependency finding.",
        ),
        type_ids=("TD-02",),
        debt_types=("dependency",),
        verifier_questions=(
            "Lockfile missing or elsewhere (monorepo)?",
            "Duplicate-purpose pair is a migration?",
            "Floating range inside a library?",
        ),
    ),
    "doc-drift": FamilyBlock(
        definition=(
            "DOC DRIFT: documentation that contradicts the code it describes. Dangling references, "
            "documents older than the code they cover, and missing README, CONTRIBUTING, ADR or "
            "CHANGELOG entries are the leads."
        ),
        questions=(
            "Cite both the document line and the contradicting code line.",
            "Would the documented example still run as written?",
            "Is the reference dangling because the target moved, or was renamed?",
            "For an absence finding, aggregate per module rather than per file.",
        ),
        traps=(
            "A document that describes a planned or external interface is not drift.",
            "Generated API docs regenerate on release; check the generator, not the output.",
        ),
        type_ids=("TD-08",),
        debt_types=("documentation",),
        verifier_questions=(
            "Both the doc line and the contradicting code line cited?",
            "Example still runnable?",
            "Absence findings aggregated per module?",
        ),
    ),
    "architecture": FamilyBlock(
        definition=(
            "ARCHITECTURE DEBT: dependency cycles between modules, code in the wrong "
            "component, and directories whose stability contradicts what depends on them. "
            "Cycle leads, coupled pairs, directory aggregates, unstable edges and any "
            "declared boundary tooling are the signals."
        ),
        questions=(
            "Is the cycle real at the language level, or does the language forbid package "
            "cycles (Go, .NET)?",
            "Is the co-change explained by a declared dependency or by feature work?",
            "Does an ADR, an import contract or a boundary tool state the intended layers?",
            "Which component should own the misplaced code, and what depends on it today?",
        ),
        traps=(
            "Re-export packages create apparent cycles that the compiler resolves.",
            "A cycle inside one cohesive package is a design smell, not an architecture finding.",
        ),
        type_ids=("TD-07", "TD-10"),
        debt_types=("architecture", "design"),
        verifier_questions=(
            "Language forbids package cycles (Go, .NET)?",
            "Co-change explained by a declared dependency or feature work?",
            "ADR or import contract states the layers?",
        ),
    ),
    "security": FamilyBlock(
        definition=(
            "SECURITY DEBT, pattern level: credential-shaped literals, string-built SQL, "
            "dynamic evaluation and shell-out, disabled TLS verification, weak hashes, "
            "wildcard CORS, and suppressed security rules. Pattern leads give the sites; "
            "you judge context, never exploitability."
        ),
        questions=(
            "Is the site under a test, example or fixture path, and does the value look "
            "like a placeholder?",
            "Can user input reach the SQL or shell site, by which path?",
            "Is a suppression justified by a comment nearby?",
            "Is the disabled verification scoped to a local or development target?",
        ),
        traps=(
            "Placeholders, examples and test fixtures are not secrets.",
            "A weak hash used for a cache key or a checksum is not a security finding.",
        ),
        type_ids=("TD-03",),
        debt_types=("security",),
        verifier_questions=(
            "Path class example, fixture or test, and secret entropy?",
            "User input reachable at the SQL or shell site?",
            "Suppression justified nearby?",
        ),
    ),
    "test-quality": FamilyBlock(
        definition=(
            "TEST QUALITY: tests that sleep, read the wall clock, use unseeded randomness, "
            "wrap logic in try or catch, branch on conditions, assert nothing, or assert "
            "against magic numbers. Per-file signal counts, CI retry configuration and "
            "flaky-commit history are the leads."
        ),
        questions=(
            "Is the pattern a table-driven or parametrised idiom rather than conditional logic?",
            "Do fake timers or a frozen clock make the wall-clock read deterministic?",
            "Does the assertion-free test guard a critical path, or is it a smoke test by design?",
            "Does the retry configuration hide a known flaky test?",
        ),
        traps=(
            "Parametrised tests loop by design.",
            "A smoke test that only checks startup is honest about its purpose.",
        ),
        type_ids=("TD-12", "TD-18"),
        debt_types=("test",),
        verifier_questions=(
            "Table-driven or parametrised idiom?",
            "Fake timers or frozen clock?",
            "Does the assertion-free test guard a critical path?",
        ),
    ),
    "pipeline-infra": FamilyBlock(
        definition=(
            "PIPELINE AND INFRASTRUCTURE DEBT, judgement symptoms only (the deterministic "
            "rule findings are produced separately): duplicated pipeline YAML, manual "
            "release steps, dev-only container paths in production use, and stdout writes "
            "where a logger exists."
        ),
        questions=(
            "Is the duplicated YAML generated from a template or hand-copied?",
            "Is the manual step documented as intentional?",
            "Is the dev-only container path used by a production job?",
            "Do the stdout writes sit in a CLI entry point (fine) or in library code with "
            "a logger present?",
        ),
        traps=(
            "A CLI tool prints by design.",
            "A dev-only compose file with a floating tag is expected.",
        ),
        type_ids=("TD-14", "TD-19", "TD-27", "TD-35"),
        debt_types=("build", "infrastructure"),
        verifier_questions=(
            "Dev-only Dockerfile or compose path?",
            "Duplicated YAML generated from a template?",
            "Manual step documented as intentional?",
        ),
    ),
}

SCOUT_OUTPUT_CONTRACT: Final[str] = """Output: one JSON object with exactly these keys.

{
  "family": "<this family>",
  "module": null,
  "findings": [
    {
      "title": "<=80 chars",
      "family": "<this family>",
      "debt_type": "<one of the allowed debt types above>",
      "type_id": "<one of the allowed TD ids above, or null>",
      "severity": 1-5,
      "effort": "S" | "M" | "L",
      "signals_cited": ["hotspot", "pattern:<family>:<rule>", "coupling", "satd"],
      "evidence": [
        {"file": "relative/path", "line_start": 120, "line_end": 123,
         "quote": "verbatim, at most 6 lines"}
      ],
      "note": "<=300 chars on what is wrong; no fix proposals"
    }
  ],
  "open_questions": [{"file": "", "line_start": 0, "question": ""}],
  "looks_bad_but_fine": [{"file": "", "line_start": 0, "why": ""}],
  "not_assessed": ["<claims you could not make>"]
}

Every quote must be copied verbatim from the file; a quote that is not in the file
is discarded by a script, together with the finding. Do not include a certainty
rating field or a fix proposal."""

SCOUT_OUTPUT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["family", "module", "findings", "open_questions",
                 "looks_bad_but_fine", "not_assessed"],
    "properties": {
        "family": {"type": "string"},
        "module": {"type": ["string", "null"]},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "family", "debt_type", "severity", "effort",
                             "signals_cited", "evidence", "note"],
                "properties": {
                    "title": {"type": "string", "maxLength": 80},
                    "family": {"type": "string"},
                    "debt_type": {"type": "string"},
                    "type_id": {"type": ["string", "null"]},
                    "severity": {"type": "integer", "minimum": 1, "maximum": 5},
                    "effort": {"type": "string", "enum": ["S", "M", "L"]},
                    "signals_cited": {"type": "array", "items": {"type": "string"}},
                    "evidence": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["file", "line_start", "line_end", "quote"],
                            "properties": {
                                "file": {"type": "string"},
                                "line_start": {"type": "integer", "minimum": 1},
                                "line_end": {"type": "integer", "minimum": 1},
                                "quote": {"type": "string"},
                            },
                        },
                    },
                    "note": {"type": "string", "maxLength": 300},
                },
            },
        },
        "open_questions": {"type": "array", "items": {"type": "object"}},
        "looks_bad_but_fine": {"type": "array", "items": {"type": "object"}},
        "not_assessed": {"type": "array", "items": {"type": "string"}},
    },
}


def render_scout_prompt(
    family: str,
    *,
    repo_summary: str,
    leads_block: str,
    scout_cap: int,
    disabled_note: str,
) -> str:
    """Shared prefix, then the family block, then the leads block, then the contract (spec 4.6)."""
    block = FAMILY_BLOCKS[family]
    questions = "\n".join(f"  - {q}" for q in block.questions)
    traps = "\n".join(f"  - {t}" for t in block.traps)
    parts = [
        f"You are a read-only scout for one debt family: {family}.",
        "",
        "Repository: " + repo_summary,
        "",
        "Rules: you have read-only access (read and search files; change nothing). Do not invent "
        "findings, files, lines or quotes; every claim cites a file, a line range and a verbatim "
        "quote of at most 6 lines. Report at most "
        f"{scout_cap} findings; that number is a ceiling, and an empty list is a correct answer "
        "when the repository has nothing in this family. Do not propose fixes.",
        "",
        NEVER_ASSERT,
        "",
        disabled_note,
        "",
        SEVERITY_RUBRIC,
        "",
        block.definition,
        "",
        "Questions to answer for every candidate:",
        questions,
        "",
        "Traps (do not report these):",
        traps,
        "",
        f"Allowed debt_type values: {', '.join(block.debt_types)}. "
        f"Allowed type_id values: {', '.join(block.type_ids)}.",
        "",
        "Leads (deterministic signals; start here, then read beyond them if budget allows):",
        leads_block.rstrip("\n"),
        "",
        SCOUT_OUTPUT_CONTRACT,
    ]
    return "\n".join(parts) + "\n"
