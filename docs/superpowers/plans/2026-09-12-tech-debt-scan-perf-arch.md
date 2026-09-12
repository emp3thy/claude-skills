# tech-debt-scan: performance family, graph-history join, concern scout — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close three coverage gaps in `tech-debt-scan` without changing its detect-verify-rank shape: a deterministic join of change coupling to the reference graph, a lead-driven `performance` family with tiering honest about what source can prove, and an index-led `concerns` scout for scattered functionality, semantic duplication and drift.

**Architecture:** Every new signal is produced by a deterministic script (`inventory.py`'s pair annotations, a new `concern_index.py`, new `patterns.py` loop-body rules, six more ruff codes) and consumed by the existing scout → verifier → `apply_verdicts` → `rank` chain. Two new `FamilyBlock`s carry the prompts; two new branches in `_family_cap_and_lift` carry the tier rules; `rank.py`, the baseline, the renderer and promote are untouched.

**Tech Stack:** Python 3.11+, pyyaml (only runtime dependency), pytest, ruff, mypy strict. Scripts direct-path invocable (`python scripts/<name>.py`); sibling imports bare.

**Spec:** `docs/superpowers/specs/2026-09-12-tech-debt-scan-perf-arch-design.md`

## Global Constraints

- Work in `C:\Users\gethi\source\claude-skills`. The skill is `skills/tech-debt-scan/`. **Run every gate from the repository root:** `python -m ruff check`, `python -m mypy --strict`, `python -m pytest` (no path arguments), `python skills/tech-debt-scan/scripts/skill_check.py`. Running mypy from inside the skill directory produces a spurious duplicate-module error.
- **Full suite before every commit**, whatever the task's blast-radius analysis names. A brief's file list is a hypothesis about coupling, not a proof of it.
- Python 3.11+; pyyaml the only runtime dependency; add none. Scripts stay direct-path invocable with bare sibling imports (`from categories import FAMILIES`).
- Rendered output LF-only (`write_bytes`); content ASCII-only in generated artifacts.
- Ruff preset `E,F,I,B,UP,SIM`, line length 100. `mypy --strict`.
- Tests never call an LLM; new families are exercised through canned JSON and the fixture corpus.
- Dispatched agents write their own output files and return a receipt (issue #19).
- Branch `feat/tech-debt-scan-perf-arch`, already checked out with the spec committed. Conventional Commits, scope `tech-debt-scan`.

## Deviations from the spec, decided here

1. **`files_read` is an optional schema property.** Spec section 4 says "no schema changes to the scout output", but `SCOUT_OUTPUT_SCHEMA` carries `additionalProperties: False` and the contract text says "exactly these keys", so an undeclared key would contradict what the scout is told to emit. Task 1 adds `files_read` as an optional integer property; no family is required to emit it.
2. **Severity 2 for PERF hits is a scout instruction, not a normaliser field.** ruff signals are `fact: False` — leads for the scout and `tool:ruff` corroboration tokens, never candidates on their own — so the normaliser has no severity to set. The `performance` block tells the scout to file a linter-only smell at severity 2 unless it can name a hot-path reason.
3. **`concern_index.py` exits 2, not 5, on a missing `edges` key.** Every sibling script returns 2 on a bad input (`inventory.py`: 2 on a bad path); exit 5 is SKILL.md's no-improvisation abort for a missing step output, not a script's own code.

---

## File Structure

| Path | Responsibility | Task |
|---|---|---|
| `scripts/validation.py` | `performance` debt type; `_TYPE_ID_MAX = 37` | 1 |
| `scripts/categories.py` | `FAMILIES` + two `FamilyBlock`s; architecture questions/traps; `render_scout_prompt(extra_block=)`; optional `files_read` | 1 |
| `scripts/config.py` | `FAMILY_SETS` default and deep | 1 |
| `scripts/inventory.py` | `_annotate_pairs`; `edges` in `coupling.json` | 2 |
| `scripts/concern_index.py` | **new** — definition-name index, top-40 candidates | 3 |
| `scripts/tools_probe.py`, `scripts/tool_normalisers.py` | six `PERF` codes | 4 |
| `scripts/patterns.py` | `_scan_loops`, four `performance` rules | 4 |
| `scripts/apply_verdicts.py` | two cap branches | 5 |
| `scripts/merge_findings.py` | `files_read` into `stats` | 5 |
| `scripts/plan_scan.py` | `concern_index` doc; three lead kinds; two `_raw_leads` branches; single concerns entry on chunked plans | 6 |
| `tests/fixtures/corpus/*` | planted items and decoys for both families | 7 |
| `tests/golden/*` | canned scout/verdict goldens; regenerated downstream goldens | 7 |
| `SKILL.md`, `docs/architecture.md`, `README.md`, `docs/evaluation-log.md` | documentation | 8 |

---

### Task 1: Taxonomy, family sets and the two family blocks

**Confidence: 95%** — pure data plus one optional keyword parameter; every assertion the existing tests make about blocks (definition length, 4–6 questions, traps, valid type ids and debt types) is known.

**Files:**
- Modify: `skills/tech-debt-scan/scripts/validation.py:15-40`
- Modify: `skills/tech-debt-scan/scripts/categories.py` (`FAMILIES` at `:44`, `FAMILY_BLOCKS["architecture"]`, `SCOUT_OUTPUT_SCHEMA` at `:460`, `SCOUT_OUTPUT_CONTRACT` at `:430`, `render_scout_prompt`)
- Modify: `skills/tech-debt-scan/scripts/config.py:100-118`
- Test: `skills/tech-debt-scan/tests/test_validation.py:91`, `skills/tech-debt-scan/tests/test_categories.py:14-30`

**Interfaces:**
- Produces: `FAMILIES` containing `"performance"` and `"concerns"` after `"security"`; `FAMILY_BLOCKS["performance"]`, `FAMILY_BLOCKS["concerns"]`; `render_scout_prompt(family, *, repo_summary, leads_block, scout_cap, disabled_note, extra_block: str = "")`; `validate_type_id("TD-36")` and `("TD-37")` accepted; `"performance" in VALID_DEBT_TYPES`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_validation.py`, change the parametrisation at `:91` and add a rejection case:

```python
@pytest.mark.parametrize("good", ["TD-01", "TD-13", "TD-35", "TD-36", "TD-37"])
```

and, next to the existing bad-id test:

```python
def test_type_id_38_is_beyond_the_ceiling() -> None:
    with pytest.raises(ValidationError, match="TD-01 to TD-37"):
        validate_type_id("TD-38")


def test_performance_is_a_debt_type() -> None:
    assert "performance" in VALID_DEBT_TYPES
```

In `tests/test_categories.py`, replace `EXPECTED_FAMILIES` and add three tests:

```python
EXPECTED_FAMILIES = (
    "complex-units", "god-classes", "duplication", "dead-code", "error-masking",
    "test-gaps", "half-finished", "migration", "dependency-debt", "doc-drift",
    "architecture", "security", "performance", "concerns", "test-quality", "pipeline-infra",
)


def test_sixteen_families_and_the_sets() -> None:
    assert FAMILIES == EXPECTED_FAMILIES
    assert set(FAMILY_BLOCKS) == set(FAMILIES)
    assert FAMILY_SETS["deep"] == FAMILIES
    assert "performance" in FAMILY_SETS["default"] and "concerns" in FAMILY_SETS["default"]
    assert "performance" not in FAMILY_SETS["quick"] and "concerns" not in FAMILY_SETS["quick"]
    assert len(FAMILY_SETS["quick"]) == 6


def test_performance_block_names_both_type_ids_and_the_tier_rule() -> None:
    block = FAMILY_BLOCKS["performance"]
    assert block.type_ids == ("TD-36", "TD-37")
    assert block.debt_types == ("performance",)
    assert "TD-37" in block.definition and "tier C" in block.definition
    assert any("cache" in q.lower() for q in block.verifier_questions)


def test_concerns_block_and_extra_block_render() -> None:
    block = FAMILY_BLOCKS["concerns"]
    assert "TD-05" in block.type_ids and "TD-10" in block.type_ids
    text = render_scout_prompt(
        "concerns", repo_summary="root: r, 10 files, 100 LOC, languages: python; git: yes",
        leads_block="Recurring definition names (candidates): src/a.py foo\n", scout_cap=6,
        disabled_note="", extra_block="Read budget: at most 60 files to confirm candidates.",
    )
    assert "Read budget: at most 60 files" in text
    assert text.index("Read budget") < text.index("Recurring definition names")
    assert '"files_read"' in categories.SCOUT_OUTPUT_CONTRACT
```

Rename the old `test_fourteen_families_in_dispatch_order` out of the file (its assertions moved into the new test).

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_validation.py skills/tech-debt-scan/tests/test_categories.py -q`
Expected: FAIL — `TD-36` rejected as beyond the ceiling; `EXPECTED_FAMILIES` mismatch; `KeyError: 'performance'`.

- [ ] **Step 3: `validation.py`**

Add `"performance"` to the `VALID_DEBT_TYPES` set literal and delete the comment line saying performance is deliberately absent. Change `_TYPE_ID_MAX: Final[int] = 35` to `37` and the comment above it to `TD-01 to TD-37 (spec 2.1; TD-36 and TD-37 added by the 2026-09-12 amendment)`.

- [ ] **Step 4: `config.py` family sets**

```python
FAMILY_SETS: Final[dict[str, tuple[str, ...]]] = {
    "default": (
        "complex-units", "god-classes", "duplication", "dead-code", "error-masking",
        "test-gaps", "half-finished", "migration", "dependency-debt", "doc-drift",
        "architecture", "security", "performance", "concerns",
    ),
    "quick": (
        "complex-units", "error-masking", "test-gaps", "half-finished",
        "dependency-debt", "security",
    ),
    "deep": (
        "complex-units", "god-classes", "duplication", "dead-code", "error-masking",
        "test-gaps", "half-finished", "migration", "dependency-debt", "doc-drift",
        "architecture", "security", "performance", "concerns", "test-quality", "pipeline-infra",
    ),
}
```

- [ ] **Step 5: `categories.py` — `FAMILIES`, the two blocks, the architecture additions**

`FAMILIES` becomes the sixteen-tuple in `EXPECTED_FAMILIES` above (same order).

Add to `FAMILY_BLOCKS` after `"security"`:

```python
    "performance": FamilyBlock(
        definition=(
            "PERFORMANCE DEBT, static only: work done inside a loop that belongs outside it "
            "(I/O, a process call, a regex compile, a sort, a membership test against a "
            "literal), redundant traversal, and inefficient collection idioms the linter "
            "flags. Two kinds, and you must assign exactly one per finding: TD-36 is a LOCAL "
            "smell provable from the source in front of you; TD-37 is a CARDINALITY claim "
            "(N+1, algorithmic complexity, 'will not scale') that depends on a runtime N "
            "nothing static can see -- a TD-37 finding is capped at tier C whatever you say, "
            "and must state why N could be large (user data, a per-request path, a paginated "
            "source), not just the shape of the loop. A linter-only hit with no hot-path "
            "reason is severity 2. Never report startup-only initialisation, a loop over an "
            "enum or a config list, test or benchmark code, or generated or vendored code."
        ),
        questions=(
            "Does this code run per request, per item or per file, or once at startup?",
            "What bounds N here: user data, a config list, a fixed enum?",
            "Is the expensive call actually inside the loop body, or hoisted above it?",
            "Is there already a cache, a batch, an index or a memo on this path?",
            "For a TD-37 claim: what evidence of scale exists -- a comment, a test with a "
            "large N, an issue reference?",
        ),
        traps=(
            "Initialisation that runs once at import or startup is not a loop cost.",
            "A loop over an enum, a config list or a fixed small collection has a bounded N.",
            "Deliberate simplicity on a cold path is a choice, not debt.",
            "Benchmark, test, generated and vendored code are out of scope.",
        ),
        type_ids=("TD-36", "TD-37"),
        debt_types=("performance",),
        verifier_questions=(
            "Runs per request, per item or per file, or once?",
            "What bounds N -- user data, config, a fixed enum?",
            "Is there already a cache, batch, index or memo on this path?",
            "Is the expensive call inside the loop or hoisted?",
            "TD-37 only: what evidence of scale is cited?",
        ),
    ),
    "concerns": FamilyBlock(
        definition=(
            "CONCERN DEBT: the same functionality implemented in more than one place under "
            "one name (scattered functionality), the same behaviour re-implemented under "
            "different names (semantic duplication, which clone detectors miss), and code "
            "that drifts from a convention the repository has written down. You receive no "
            "file leads: the candidates are definition names that recur across directories, "
            "plus the hotspot band, the coupled pairs and the directory aggregates. Read to "
            "confirm a candidate, not to discover; name every file you open beyond the "
            "candidates and why. TD-05 for semantic duplication, TD-10 for scatter, null "
            "for drift."
        ),
        questions=(
            "Is the recurring name the same concept, or a homonym?",
            "Would consolidating the implementations change behaviour?",
            "Is this a deliberate per-module implementation -- adapter, plugin, backend?",
            "For drift: which written convention does it contradict -- an ADR, README, "
            "CLAUDE.md, a docs/ page -- cited by file and line?",
        ),
        traps=(
            "One function per adapter, plugin or backend under a shared name is a pattern, "
            "not scatter.",
            "Generated code, fixtures and corpora repeat names by construction.",
            "Language idioms (main, init, new, run, setup) recur everywhere and mean nothing.",
            "Drift that contradicts only your taste, with no written convention to cite, "
            "is not a finding.",
        ),
        type_ids=("TD-05", "TD-10"),
        debt_types=("architecture",),
        verifier_questions=(
            "Same concept or a homonym?",
            "Would consolidation change behaviour?",
            "Deliberate per-module implementation?",
            "Which written convention is contradicted, cited by file and line?",
        ),
    ),
```

In `FAMILY_BLOCKS["architecture"]`, append two questions and one trap:

```python
            "Is the co-change explained by a dependency the graph cannot see -- a config "
            "file, a schema, a generated pair, a test and its subject?",
            "Is the high-fan-in side an intentional facade whose dependents are meant to "
            "change with it?",
```
```python
            "A .proto or schema file and its generated code co-change by construction.",
```

Check the architecture block still has at most 6 questions (it has 4 today; 6 after).

- [ ] **Step 6: `categories.py` — `files_read` and `extra_block`**

In `SCOUT_OUTPUT_SCHEMA["properties"]` add, after `"not_assessed"`:

```python
        "files_read": {"type": "integer", "minimum": 0},
```

(`required` is unchanged, so it stays optional.) In `SCOUT_OUTPUT_CONTRACT`, after the `"not_assessed"` line, add:

```
  "files_read": <integer; optional, report it when your prompt asks for a read budget>
```

Change `render_scout_prompt`'s signature to add `extra_block: str = ""` after `disabled_note`, and in `parts` insert, immediately before the `"Leads (deterministic signals; ..."` line:

```python
        *([extra_block, ""] if extra_block else []),
```

- [ ] **Step 7: Run the two test files, then the whole suite**

Run: `python -m pytest skills/tech-debt-scan/tests/test_validation.py skills/tech-debt-scan/tests/test_categories.py -q`
Expected: PASS.

Run: `python -m pytest -q`
Expected: PASS — note that `test_categories.test_every_block_is_complete_and_valid` validates every block's type ids and debt types, which is why `validation.py` changes in the same task.

- [ ] **Step 8: Gates and commit**

Run: `python -m ruff check && python -m mypy --strict`

```bash
git add skills/tech-debt-scan/scripts/validation.py skills/tech-debt-scan/scripts/categories.py skills/tech-debt-scan/scripts/config.py skills/tech-debt-scan/tests/test_validation.py skills/tech-debt-scan/tests/test_categories.py
git commit -m "feat(tech-debt-scan): add the performance and concerns families to the taxonomy

TD-36 (local performance smell) and TD-37 (cardinality claim), a
performance debt type, two family blocks, both families in the default
and deep sets, an optional files_read key on scout output, and an
extra_block slot in the scout prompt for the concerns read budget."
```

---

### Task 2: Graph–history join in `inventory.py`

**Confidence: 93%** — `change_coupling` returns pairs as `{a, b, shared_commits, ratio, cross_directory}` and the graph as `GraphResult` with `edges: list[tuple[str, str]]` and `fan_in: dict[str, int | None]`, both verified; the only judgment is the decile rule, which is specified exactly.

**Files:**
- Modify: `skills/tech-debt-scan/scripts/inventory.py` — a new `_annotate_pairs` above `build_all`; one call before the `coupling: dict[str, Any] = {` literal at `:888`; `"edges"` in that literal
- Test: `skills/tech-debt-scan/tests/test_inventory_v2.py`

**Interfaces:**
- Consumes: `reference_graph.GraphResult` (`edges`, `fan_in`).
- Produces: every `coupling.json` pair gains `has_edge: bool`, `edge_direction: "a->b" | "b->a" | "both" | None`, `lead_kind: "modularity-violation" | "unstable-interface" | None`; `coupling.json` gains `edges: list[list[str]]`. `_annotate_pairs(pairs, graph) -> None` mutates in place.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_inventory_v2.py`:

```python
def _graph(edges: list[tuple[str, str]], fan_in: dict[str, int | None]):
    from reference_graph import GraphResult

    g = GraphResult()
    g.edges = list(edges)
    g.fan_in = dict(fan_in)
    return g


def _pair(a: str, b: str, *, cross: bool = True) -> dict:
    return {"a": a, "b": b, "shared_commits": 4, "ratio": 0.5, "cross_directory": cross}


def test_pair_with_no_edge_is_a_modularity_violation() -> None:
    from inventory import _annotate_pairs

    pairs = [_pair("src/a.py", "lib/b.py")]
    _annotate_pairs(pairs, _graph([], {"src/a.py": 1, "lib/b.py": 1}))
    assert pairs[0]["has_edge"] is False
    assert pairs[0]["edge_direction"] is None
    assert pairs[0]["lead_kind"] == "modularity-violation"


@pytest.mark.parametrize(
    ("edges", "direction"),
    [
        ([("src/a.py", "lib/b.py")], "a->b"),
        ([("lib/b.py", "src/a.py")], "b->a"),
        ([("src/a.py", "lib/b.py"), ("lib/b.py", "src/a.py")], "both"),
    ],
)
def test_pair_with_a_direct_edge_is_never_a_violation(edges, direction) -> None:
    from inventory import _annotate_pairs

    pairs = [_pair("src/a.py", "lib/b.py")]
    _annotate_pairs(pairs, _graph(edges, {"src/a.py": 1, "lib/b.py": 1}))
    assert pairs[0]["has_edge"] is True
    assert pairs[0]["edge_direction"] == direction
    assert pairs[0]["lead_kind"] is None


def test_edge_into_a_top_decile_fan_in_file_is_an_unstable_interface() -> None:
    from inventory import _annotate_pairs

    fan_in = {f"src/f{i}.py": i for i in range(1, 21)}  # 1..20; top decile is >= 19
    fan_in["src/hub.py"] = 40
    fan_in["src/dep.py"] = 1
    pairs = [_pair("src/dep.py", "src/hub.py", cross=False)]
    _annotate_pairs(pairs, _graph([("src/dep.py", "src/hub.py")], fan_in))
    assert pairs[0]["lead_kind"] == "unstable-interface"


def test_decile_ignores_null_fan_in_and_needs_positive_fan_in() -> None:
    from inventory import _annotate_pairs

    fan_in = {"src/a.py": None, "src/b.py": 0, "src/c.py": 0}
    pairs = [_pair("src/a.py", "src/b.py")]
    _annotate_pairs(pairs, _graph([("src/a.py", "src/b.py")], fan_in))
    assert pairs[0]["lead_kind"] is None  # an edge, but no positive fan-in anywhere


def test_same_directory_violation_is_kept_and_flagged() -> None:
    from inventory import _annotate_pairs

    pairs = [_pair("src/a.py", "src/b.py", cross=False)]
    _annotate_pairs(pairs, _graph([], {"src/a.py": 1, "src/b.py": 1}))
    assert pairs[0]["lead_kind"] == "modularity-violation"
    assert pairs[0]["cross_directory"] is False


def test_coupling_document_carries_edges(service_py_repo: Path) -> None:
    from inventory import build_all

    _inventory, coupling = build_all(service_py_repo, churn_months=240)
    assert "edges" in coupling
    assert all(len(e) == 2 for e in coupling["edges"])
    for pair in coupling["pairs"]:
        assert set(pair) >= {"has_edge", "edge_direction", "lead_kind"}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_inventory_v2.py -k "violation or unstable or decile or carries_edges" -q`
Expected: FAIL — `ImportError: cannot import name '_annotate_pairs'`.

- [ ] **Step 3: Implement `_annotate_pairs`**

Add to `inventory.py` directly above `def build_all(`:

```python
def _fan_in_decile_floor(fan_in: dict[str, int | None]) -> int | None:
    """The smallest fan-in in the top decile of non-null, positive values; None when
    nothing is positive. A decile rather than a fixed number because surveyed tools'
    hub thresholds disagree by an order of magnitude (spec 2026-09-12, section 2)."""
    values = sorted(v for v in fan_in.values() if isinstance(v, int) and v > 0)
    if not values:
        return None
    index = max(0, int(math.ceil(0.9 * len(values))) - 1)
    return values[index]


def _annotate_pairs(pairs: list[dict[str, Any]], graph: GraphResult) -> None:
    """Join each change-coupled pair to the reference graph (spec 2026-09-12, section 2).

    ``has_edge`` is a direct edge in either direction -- never transitive, because
    a two-hop path is a declared relation and the literature's signal is the
    absence of any. A pair with no edge is a ``modularity-violation`` lead. A pair
    with an edge where either side's fan-in sits in the repository's top decile is
    an ``unstable-interface`` lead. Mutates ``pairs`` in place.
    """
    forward: set[tuple[str, str]] = set(graph.edges)
    floor = _fan_in_decile_floor(graph.fan_in)
    for pair in pairs:
        a, b = str(pair["a"]), str(pair["b"])
        ab, ba = (a, b) in forward, (b, a) in forward
        pair["has_edge"] = ab or ba
        pair["edge_direction"] = "both" if ab and ba else "a->b" if ab else "b->a" if ba else None
        if not pair["has_edge"]:
            pair["lead_kind"] = "modularity-violation"
            continue
        hub = False
        if floor is not None:
            for side in (a, b):
                value = graph.fan_in.get(side)
                if isinstance(value, int) and value >= floor:
                    hub = True
        pair["lead_kind"] = "unstable-interface" if hub else None
```

Add `import math` to the module imports if absent, and confirm `GraphResult` is imported from `reference_graph` (it is used as a type already; add `from reference_graph import GraphResult` if only the builder is imported).

Immediately before the `coupling: dict[str, Any] = {` literal (`:888`), add:

```python
    _annotate_pairs(pairs, graph)
```

and inside the literal, after `"unstable_edges": graph.unstable_edges,`:

```python
        "edges": [[src, dst] for src, dst in graph.edges],
```

- [ ] **Step 4: Run the tests, then the whole suite**

Run: `python -m pytest skills/tech-debt-scan/tests/test_inventory_v2.py -q` then `python -m pytest -q`
Expected: PASS. If a coupling golden under `tests/golden/*/` fails on the new keys, regenerate with `UPDATE_GOLDENS=1 python -m pytest skills/tech-debt-scan/tests/test_chain_goldens.py -q` and inspect the diff: only `has_edge`, `edge_direction`, `lead_kind` and `edges` may have changed.

- [ ] **Step 5: Gates and commit**

```bash
git add skills/tech-debt-scan/scripts/inventory.py skills/tech-debt-scan/tests/test_inventory_v2.py skills/tech-debt-scan/tests/golden
git commit -m "feat(tech-debt-scan): join change coupling to the reference graph

Every coupled pair now records has_edge, edge_direction and lead_kind:
no direct edge is a modularity-violation lead; an edge into a top-decile
fan-in file is an unstable-interface lead. coupling.json carries the
graph's edges so the join is reproducible from the workdir."
```

---

### Task 3: `concern_index.py`

**Confidence: 90%** — a new pure script over two documents whose shapes are verified; the residual risk is the per-language definition regexes, which are tested line by line against a fixture set in Step 1 so a bad regex fails here rather than in a scout.

**Files:**
- Create: `skills/tech-debt-scan/scripts/concern_index.py`
- Test: `skills/tech-debt-scan/tests/test_concern_index.py`

**Interfaces:**
- Consumes: `inventory.json` (`root`, `files[]` with `path`, `path_class`, `language`, `hotspot_score`, `skipped_large`; `hotspot_band`), `coupling.json` (`pairs`, `directories`, `edges`).
- Produces: `concern-index.json`: `{"schema_version": 1, "directories": [...], "candidates": [{"name", "tokens", "files", "directories", "hotspot_touch", "coupled"}], "stats": {"files_scanned", "names_seen", "candidates"}}`; `build_concern_index(root, inventory, coupling) -> dict`; CLI `python scripts/concern_index.py <repo> --workdir .tech-debt`, exit 2 when `coupling.json` lacks `edges`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_concern_index.py`:

```python
"""concern_index.py: definition-name index and cross-directory candidates (spec 2026-09-12, 4)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from concern_index import (
    STOPLIST,
    _main,
    build_concern_index,
    definition_names,
    normalise_name,
)


@pytest.mark.parametrize(
    ("language", "line", "name"),
    [
        ("python", "def compute_total(x):", "compute_total"),
        ("python", "    async def fetch_page(self):", "fetch_page"),
        ("python", "class RefundLedger:", "RefundLedger"),
        ("typescript", "export function computeTotal(x: number) {", "computeTotal"),
        ("javascript", "const computeTotal = (x) => x", "computeTotal"),
        ("typescript", "export default class Ledger {", "Ledger"),
        ("go", "func computeTotal(x int) int {", "computeTotal"),
        ("go", "func (l *Ledger) Post(x int) {", "Post"),
        ("rust", "pub fn compute_total(x: u32) -> u32 {", "compute_total"),
        ("rust", "impl Ledger {", "Ledger"),
        ("java", "public static int computeTotal(int x) {", "computeTotal"),
        ("csharp", "private async Task<int> ComputeTotal(int x)", "ComputeTotal"),
    ],
)
def test_definition_names_per_language(language: str, line: str, name: str) -> None:
    assert definition_names(language, line + "\n") == [name]


def test_unknown_language_yields_no_names() -> None:
    assert definition_names("markdown", "def looks_like_python():\n") == []


@pytest.mark.parametrize(
    ("raw", "key"),
    [("computeTotal", "compute_total"), ("compute_total", "compute_total"),
     ("ComputeTotal", "compute_total"), ("HTTPClient", "http_client")],
)
def test_normalise_name_joins_camel_and_snake(raw: str, key: str) -> None:
    assert normalise_name(raw) == key


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return tmp_path


def _inventory(files: dict[str, str], band: list[str]) -> dict[str, Any]:
    return {
        "root": "unused",
        "hotspot_band": band,
        "files": [
            {"path": rel, "path_class": "tests" if rel.startswith("tests/") else "source",
             "language": "python", "hotspot_score": 5.0 if rel in band else 0.0,
             "skipped_large": False}
            for rel in files
        ],
    }


def _coupling(pairs: list[tuple[str, str]]) -> dict[str, Any]:
    return {"pairs": [{"a": a, "b": b} for a, b in pairs],
            "directories": [{"path": "src/pay", "files": 2, "loc": 10, "churn": 3,
                             "fan_in": 1, "fan_out": 1, "instability": 0.5}],
            "edges": []}


FILES = {
    "src/pay/utils.py": "def format_amount(x):\n    return x\n",
    "src/billing/format.py": "def formatAmount(x):\n    return x\n",
    "src/pay/parse.py": "def parse_csv(x):\n    return x\n",
    "src/billing/parse.py": "def parse_json(x):\n    return x\n",
    "src/pay/main.py": "def main():\n    pass\n",
    "src/billing/main.py": "def main():\n    pass\n",
    "tests/test_x.py": "def format_amount():\n    pass\n",
}


def test_candidate_needs_two_files_across_two_directories(tmp_path: Path) -> None:
    root = _repo(tmp_path, FILES)
    doc = build_concern_index(root, _inventory(FILES, []), _coupling([]))
    names = [c["name"] for c in doc["candidates"]]
    assert "format_amount" in names          # utils.py + format.py, two directories
    assert "parse_csv" not in names          # one file only
    assert "main" not in names               # stoplist


def test_test_files_do_not_count(tmp_path: Path) -> None:
    files = {"src/pay/a.py": "def only_here(x):\n    pass\n",
             "tests/test_a.py": "def only_here():\n    pass\n"}
    root = _repo(tmp_path, files)
    doc = build_concern_index(root, _inventory(files, []), _coupling([]))
    assert doc["candidates"] == []


def test_hotspot_touch_and_coupled_are_recorded(tmp_path: Path) -> None:
    root = _repo(tmp_path, FILES)
    doc = build_concern_index(
        root, _inventory(FILES, ["src/pay/utils.py"]),
        _coupling([("src/pay/utils.py", "src/billing/format.py")]),
    )
    cand = next(c for c in doc["candidates"] if c["name"] == "format_amount")
    assert cand["hotspot_touch"] is True
    assert cand["coupled"] is True
    assert cand["files"] == ["src/billing/format.py", "src/pay/utils.py"]
    assert cand["directories"] == ["src/billing", "src/pay"]


def test_ranking_and_the_top_forty_cut(tmp_path: Path) -> None:
    files: dict[str, str] = {}
    for i in range(50):
        for d in ("a", "b", "c" if i < 5 else "b"):
            files[f"src/{d}/m{i}.py"] = f"def shared_{i:02d}():\n    pass\n"
    root = _repo(tmp_path, files)
    doc = build_concern_index(root, _inventory(files, []), _coupling([]))
    assert len(doc["candidates"]) == 40
    # three-directory names rank ahead of two-directory names
    assert all(len(c["directories"]) == 3 for c in doc["candidates"][:5])


def test_output_is_deterministic(tmp_path: Path) -> None:
    root = _repo(tmp_path, FILES)
    a = build_concern_index(root, _inventory(FILES, []), _coupling([]))
    b = build_concern_index(root, _inventory(FILES, []), _coupling([]))
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_stoplist_covers_idioms_and_adapter_verbs() -> None:
    for word in ("main", "init", "new", "run", "setup", "teardown", "normalise", "parse",
                 "load", "render", "handle", "build"):
        assert word in STOPLIST


def test_cli_exits_2_without_edges(tmp_path: Path) -> None:
    root = _repo(tmp_path, FILES)
    workdir = tmp_path / ".tech-debt"
    workdir.mkdir()
    (workdir / "inventory.json").write_text(json.dumps(_inventory(FILES, [])), encoding="utf-8")
    coupling = _coupling([])
    del coupling["edges"]
    (workdir / "coupling.json").write_text(json.dumps(coupling), encoding="utf-8")
    assert _main([str(root), "--workdir", str(workdir)]) == 2


def test_cli_writes_the_index(tmp_path: Path) -> None:
    root = _repo(tmp_path, FILES)
    workdir = tmp_path / ".tech-debt"
    workdir.mkdir()
    (workdir / "inventory.json").write_text(json.dumps(_inventory(FILES, [])), encoding="utf-8")
    (workdir / "coupling.json").write_text(json.dumps(_coupling([])), encoding="utf-8")
    assert _main([str(root), "--workdir", str(workdir)]) == 0
    doc = json.loads((workdir / "concern-index.json").read_text(encoding="utf-8"))
    assert doc["schema_version"] == 1 and doc["stats"]["candidates"] >= 1
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_concern_index.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'concern_index'`.

- [ ] **Step 3: Write `scripts/concern_index.py`**

```python
"""Definition-name index for the concerns scout (spec 2026-09-12, section 4).

A deterministic map of the repository the concerns scout reads instead of file
leads: per-directory aggregates (copied from ``coupling.json``, where the
reference graph already writes them), and the definition names that recur
across directories. A name defined in at least two source files across at
least two directories is a candidate for scattered or duplicated
functionality; the scout reads to confirm candidates, not to discover them,
which is what bounds its cost on a large repository -- by candidate count, not
by file count.

Names are extracted with a per-language regex table over definition lines and
normalised so ``computeTotal``, ``compute_total`` and ``ComputeTotal`` are one
key. A stoplist removes language idioms and per-adapter verbs (one
``parse_<format>`` per format is a pattern, not scatter). At most 40
candidates are kept, ranked by directory count then hotspot share.

Reads ``inventory.json`` and ``coupling.json``; writes ``concern-index.json``.
Exit 2 when ``coupling.json`` carries no ``edges`` -- that document was written
by an older ``inventory.py`` and the chain must be re-run from step 1.

Direct-path invocable: ``python scripts/concern_index.py <repo> --workdir .tech-debt``.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Final

from inventory import write_json

SCHEMA_VERSION: Final[int] = 1
MAX_CANDIDATES: Final[int] = 40
MIN_FILES: Final[int] = 2
MIN_DIRECTORIES: Final[int] = 2

# Language idioms that recur everywhere, and per-adapter verbs that name one
# implementation per backend by design. Compared against the normalised key.
STOPLIST: Final[frozenset[str]] = frozenset({
    "main", "init", "new", "run", "setup", "teardown", "test", "str", "repr",
    "normalise", "normalize", "parse", "load", "render", "handle", "build",
})

_PY: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\("),
    re.compile(r"^\s*class\s+(\w+)\b"),
)
_JS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w+)\s*\("),
    re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+(\w+)\b"),
    re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*(?::[^=]+)?=\s*(?:async\s*)?\("),
)
_GO: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?(\w+)\s*\("),
)
_RUST: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+(\w+)\s*[<(]"),
    re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:struct|enum|trait)\s+(\w+)\b"),
    re.compile(r"^\s*impl(?:<[^>]*>)?\s+(?:\w+\s+for\s+)?(\w+)\b"),
)
_CLIKE: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(
        r"^\s*(?:public|private|protected|internal)\s+(?:static\s+)?(?:async\s+)?"
        r"(?:[\w<>\[\],.?]+\s+)+(\w+)\s*\("
    ),
)
DEFINITION_TABLE: Final[dict[str, tuple[re.Pattern[str], ...]]] = {
    "python": _PY,
    "javascript": _JS,
    "typescript": _JS,
    "go": _GO,
    "rust": _RUST,
    "java": _CLIKE,
    "csharp": _CLIKE,
}

_CAMEL_RE: Final[re.Pattern[str]] = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def definition_names(language: str, text: str) -> list[str]:
    """Every definition name in ``text`` for ``language``, in order; [] for unknown languages."""
    patterns = DEFINITION_TABLE.get(language)
    if not patterns:
        return []
    out: list[str] = []
    for line in text.splitlines():
        for pattern in patterns:
            match = pattern.match(line)
            if match:
                out.append(match.group(1))
                break
    return out


def normalise_name(raw: str) -> str:
    """``computeTotal``, ``compute_total`` and ``ComputeTotal`` all become ``compute_total``."""
    parts: list[str] = []
    for chunk in raw.strip("_").split("_"):
        if chunk:
            parts.extend(p.lower() for p in _CAMEL_RE.split(chunk) if p)
    return "_".join(parts)


def _dirname(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else ""


def build_concern_index(
    root: Path, inventory: dict[str, Any], coupling: dict[str, Any]
) -> dict[str, Any]:
    """The index document (see the module docstring)."""
    band = {str(p) for p in inventory.get("hotspot_band") or []}
    coupled_pairs = {
        frozenset((str(p.get("a")), str(p.get("b")))) for p in coupling.get("pairs") or []
    }
    by_key: dict[str, dict[str, Any]] = {}
    scanned = 0
    for entry in inventory.get("files") or []:
        if entry.get("path_class") != "source" or entry.get("skipped_large"):
            continue
        language = str(entry.get("language") or "")
        if language not in DEFINITION_TABLE:
            continue
        rel = str(entry["path"])
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        for raw in definition_names(language, text):
            key = normalise_name(raw)
            if not key or key in STOPLIST:
                continue
            slot = by_key.setdefault(key, {"raw": set(), "files": set()})
            slot["raw"].add(raw)
            slot["files"].add(rel)

    candidates: list[dict[str, Any]] = []
    for key, slot in by_key.items():
        files = sorted(slot["files"])
        directories = sorted({_dirname(f) for f in files})
        if len(files) < MIN_FILES or len(directories) < MIN_DIRECTORIES:
            continue
        hotspot_share = sum(1 for f in files if f in band) / len(files)
        coupled = any(
            frozenset((x, y)) in coupled_pairs
            for i, x in enumerate(files) for y in files[i + 1:]
        )
        candidates.append({
            "name": key,
            "tokens": sorted(slot["raw"]),
            "files": files,
            "directories": directories,
            "hotspot_touch": hotspot_share > 0,
            "hotspot_share": round(hotspot_share, 3),
            "coupled": coupled,
        })
    candidates.sort(key=lambda c: (-len(c["directories"]), -c["hotspot_share"], c["name"]))
    kept = candidates[:MAX_CANDIDATES]
    return {
        "schema_version": SCHEMA_VERSION,
        "directories": list(coupling.get("directories") or []),
        "candidates": kept,
        "stats": {"files_scanned": scanned, "names_seen": len(by_key), "candidates": len(kept)},
    }


def _read(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_bytes())
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} is not a JSON object")
    return loaded


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Index recurring definition names for the concerns scout")
    parser.add_argument("repo", type=Path, help="repository root")
    parser.add_argument("--workdir", type=Path, default=Path(".tech-debt"))
    args = parser.parse_args(argv)
    try:
        inventory = _read(args.workdir / "inventory.json")
        coupling = _read(args.workdir / "coupling.json")
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if "edges" not in coupling:
        print(
            f"error: {args.workdir / 'coupling.json'} has no edges; it was written by an "
            "older inventory.py -- re-run the chain from step 1",
            file=sys.stderr,
        )
        return 2
    doc = build_concern_index(args.repo.resolve(), inventory, coupling)
    out = args.workdir / "concern-index.json"
    write_json(out, doc)
    print(f"wrote {out} ({doc['stats']['candidates']} candidate(s) from "
          f"{doc['stats']['files_scanned']} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
```

`_repo`'s `"unused"` root in the tests is fine: `build_concern_index` takes `root` as an argument and never reads `inventory["root"]`.

- [ ] **Step 4: Run the tests, then the whole suite**

Run: `python -m pytest skills/tech-debt-scan/tests/test_concern_index.py -q` then `python -m pytest -q`
Expected: PASS. If any per-language regex test fails, fix the regex, not the test — the fixture lines are the contract.

- [ ] **Step 5: Gates and commit**

```bash
git add skills/tech-debt-scan/scripts/concern_index.py skills/tech-debt-scan/tests/test_concern_index.py
git commit -m "feat(tech-debt-scan): concern_index.py, the definition-name index for the concerns scout

Definition names per language, normalised across camel and snake case,
a stoplist for idioms and adapter verbs, and at most 40 candidates that
recur across directories, ranked by directory count then hotspot share.
Exits 2 when coupling.json predates the graph join."
```

---

### Task 4: Performance leads — ruff `PERF*` and `_scan_loops`

**Confidence: 92%** — `RUFF_SELECT`/`RUFF_KINDS` have a parity test; `_scan_catches`, `_indented_body` and `_brace_body` are the verified shape for a body-scoped scanner. Residual: the four body regexes over real code, covered by the corpus decoys in Task 7.

**Files:**
- Modify: `skills/tech-debt-scan/scripts/tools_probe.py:326`
- Modify: `skills/tech-debt-scan/scripts/tool_normalisers.py:138-150`
- Modify: `skills/tech-debt-scan/scripts/patterns.py` (new regexes near the other `_RE` constants; `_scan_loops` after `_scan_catches`; four `Rule` entries in `RULES`; `"loop"` in `_HANDLERS`)
- Test: `skills/tech-debt-scan/tests/test_tool_normalisers.py`, `skills/tech-debt-scan/tests/test_patterns.py`

**Interfaces:**
- Produces: `patterns.json` leads under `"performance"` with rules `io-in-loop`, `regex-in-loop`, `sort-in-loop`, `membership-in-loop`, each with `extra["loop_line"]`; ruff signals with `family == "performance"`, `kind == "perf-smell"`, `extra["code"]` one of the six.

- [ ] **Step 1: Write the failing tests**

In `tests/test_tool_normalisers.py`, add:

```python
@pytest.mark.parametrize("code", ["PERF101", "PERF102", "PERF203", "PERF401", "PERF402", "PERF403"])
def test_ruff_perf_codes_map_to_the_performance_family(code: str, tmp_path: Path) -> None:
    from tool_normalisers import normalise_ruff

    payload = [{"code": code, "filename": str(tmp_path / "src" / "a.py"),
                "location": {"row": 7}, "end_location": {"row": 7}, "message": "m"}]
    (signal,) = normalise_ruff(payload, tmp_path)
    assert signal["family"] == "performance" and signal["kind"] == "perf-smell"
    assert signal["extra"]["code"] == code and signal["fact"] is False
```

In `tests/test_patterns.py`, add (using the module's own `RULES` and a direct handler call):

```python
def _perf_rule(name: str):
    return next(r for r in RULES if r.family == "performance" and r.rule == name)


def _scan(text: str, rule_name: str, language: str = "python") -> list[Lead]:
    from patterns import Markers, ScanContext, ScanFile, _HANDLERS, markers_for

    sf = ScanFile(path="src/a.py", path_class="source", scope="source", language=language,
                  text=text, lines=text.splitlines(), markers=markers_for(language))
    rule = _perf_rule(rule_name)
    return _HANDLERS[rule.kind](sf, rule, ScanContext(fan_in={}, logger_present=False))


def test_io_call_inside_a_python_loop_is_a_lead() -> None:
    text = "for row in rows:\n    data = open(row.path).read()\n    total += 1\n"
    (lead,) = _scan(text, "io-in-loop")
    assert lead.line == 2 and lead.extra["loop_line"] == 1


def test_io_call_outside_the_loop_is_not_a_lead() -> None:
    text = "handle = open(path)\nfor row in rows:\n    total += 1\n"
    assert _scan(text, "io-in-loop") == []


def test_brace_language_loop_body_is_scoped_by_braces() -> None:
    text = ("for (const row of rows) {\n  const r = await fetch(row.url);\n}\n"
            "const later = fetch(other);\n")
    (lead,) = _scan(text, "io-in-loop", language="typescript")
    assert lead.line == 2


def test_regex_sort_and_membership_in_loop() -> None:
    text = ("while pending:\n    pat = re.compile(r'x')\n    items = sorted(items)\n"
            "    if x in [1, 2, 3]:\n        pass\n")
    assert [lead.line for lead in _scan(text, "regex-in-loop")] == [2]
    assert [lead.line for lead in _scan(text, "sort-in-loop")] == [3]
    assert [lead.line for lead in _scan(text, "membership-in-loop")] == [4]


def test_nested_loops_report_a_line_once() -> None:
    text = "for a in xs:\n    for b in ys:\n        open(b)\n"
    assert len(_scan(text, "io-in-loop")) == 1
```

If `markers_for` is not the module's comment-marker lookup, use whatever `_scan_files` uses to build `ScanFile.markers` (read `_scan_files` at `patterns.py` for the exact name and import that).

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_tool_normalisers.py -k perf skills/tech-debt-scan/tests/test_patterns.py -k "loop" -q`
Expected: FAIL — the ruff payload yields `[]`; `StopIteration` from `_perf_rule`.

- [ ] **Step 3: ruff codes**

`tools_probe.py:326`:

```python
RUFF_SELECT: Final[str] = (
    "E722,BLE001,S110,S112,C901,PLR0911,PLR0912,PLR0913,PLR0915,F401,UP035,"
    "PERF101,PERF102,PERF203,PERF401,PERF402,PERF403"
)
```

`tool_normalisers.py` `RUFF_KINDS`, after `"UP035"`:

```python
    "PERF101": ("performance", "perf-smell"),
    "PERF102": ("performance", "perf-smell"),
    "PERF203": ("performance", "perf-smell"),
    "PERF401": ("performance", "perf-smell"),
    "PERF402": ("performance", "perf-smell"),
    "PERF403": ("performance", "perf-smell"),
```

- [ ] **Step 4: `_scan_loops` and the four rules**

Add the regexes beside the other `_RE` constants in `patterns.py`:

```python
# performance (spec 2026-09-12, section 3): a loop header, then four body smells.
LOOP_HEADER_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:for\b|while\b|foreach\b|.*\.forEach\s*\()"
)
IO_IN_LOOP_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:open|subprocess\.(?:run|check_output|call|Popen)|requests\.(?:get|post|put|delete|head)"
    r"|fetch|axios\.\w+|urlopen)\s*\(|\.(?:query|execute|fetchone|fetchall|find_one|find)\s*\("
)
REGEX_IN_LOOP_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:re\.compile|new\s+RegExp|Pattern\.compile|regexp\.MustCompile|Regex::new)\s*\("
)
SORT_IN_LOOP_RE: Final[re.Pattern[str]] = re.compile(r"\bsorted\s*\(|\.sort(?:ed|By)?\s*\(")
MEMBERSHIP_IN_LOOP_RE: Final[re.Pattern[str]] = re.compile(r"\bin\s*\[|\.includes\s*\(\s*['\"]")
```

Add after `_scan_catches`:

```python
def _scan_loops(sf: ScanFile, rule: Rule, _ctx: ScanContext) -> list[Lead]:
    """``rule.regex`` matched over the body lines of every loop (spec 2026-09-12, 3).

    The body is delimited the way ``_scan_catches`` delimits a catch body:
    ``_indented_body`` for a header ending in ``:``, ``_brace_body`` for a
    header carrying ``{`` or followed by one. A line inside two nested loops is
    reported once, against the innermost header. Leads carry ``loop_line``.
    """
    leads: list[Lead] = []
    seen: set[int] = set()
    for index, line in enumerate(sf.lines):
        if not LOOP_HEADER_RE.match(line):
            continue
        stripped = line.rstrip()
        if stripped.endswith(":"):
            _body, end = _indented_body(sf.lines, index)
        elif "{" in line:
            _body, end = _brace_body(sf.lines, index, line.find("{"))
        elif index + 1 < len(sf.lines) and sf.lines[index + 1].lstrip().startswith("{"):
            _body, end = _brace_body(sf.lines, index + 1, 0)
        else:
            continue
        for j in range(index + 1, min(end, len(sf.lines) - 1) + 1):
            if j in seen or not rule.regex.search(sf.lines[j]):
                continue
            if LOOP_HEADER_RE.match(sf.lines[j]):
                continue  # a nested header is reported against its own body
            seen.add(j)
            leads.append(Lead(rule.rule, sf.path, j + 1, sf.lines[j].strip(), sf.path_class,
                              {"loop_line": index + 1}))
    return leads
```

Note on "reported once, against the innermost header": the outer loop is scanned first and adds line `j` to `seen`, so the outer header wins; adjust the docstring to "against the outermost header" and keep the once-only behaviour, which is what the test asserts.

In `RULES`, after the `security` group:

```python
    # performance (spec 2026-09-12)
    Rule("performance", "io-in-loop", IO_IN_LOOP_RE, SOURCE, kind="loop"),
    Rule("performance", "regex-in-loop", REGEX_IN_LOOP_RE, SOURCE, kind="loop"),
    Rule("performance", "sort-in-loop", SORT_IN_LOOP_RE, SOURCE, kind="loop"),
    Rule("performance", "membership-in-loop", MEMBERSHIP_IN_LOOP_RE, SOURCE, kind="loop"),
```

In `_HANDLERS`: `"loop": _scan_loops,`.

- [ ] **Step 5: Run the tests, then the whole suite**

Run: `python -m pytest skills/tech-debt-scan/tests/test_tool_normalisers.py skills/tech-debt-scan/tests/test_patterns.py -q` then `python -m pytest -q`
Expected: PASS. `test_tools_probe.py::TestRuffRuleSetsAgree` proves both ruff lists moved together. A `patterns.json` golden may change (new `performance` key with leads over the corpus); regenerate with `UPDATE_GOLDENS=1` and confirm only the `performance` key and `stats.leads_per_family.performance` differ.

- [ ] **Step 6: Gates and commit**

```bash
git add skills/tech-debt-scan/scripts/tools_probe.py skills/tech-debt-scan/scripts/tool_normalisers.py skills/tech-debt-scan/scripts/patterns.py skills/tech-debt-scan/tests/test_tool_normalisers.py skills/tech-debt-scan/tests/test_patterns.py skills/tech-debt-scan/tests/golden
git commit -m "feat(tech-debt-scan): performance leads from ruff PERF rules and loop-body patterns

Six PERF codes map to the performance family; _scan_loops delimits a
loop body the way _scan_catches delimits a catch body and runs four body
regexes over it: I/O or process call, regex compile, sort, membership
test against a literal."
```

---

### Task 5: Tier rules in `apply_verdicts.py`; `files_read` in `merge_findings.py`

**Confidence: 94%** — both are one branch each in functions whose shape and tests are verified (`_family_cap_and_lift` at `:72`, `_cand` factory in `test_apply_verdicts.py`).

**Files:**
- Modify: `skills/tech-debt-scan/scripts/apply_verdicts.py:72-118`
- Modify: `skills/tech-debt-scan/scripts/merge_findings.py` (the scout-document loop at `:870-905`; the `stats[family]` initialisation it uses)
- Test: `skills/tech-debt-scan/tests/test_apply_verdicts.py`, `skills/tech-debt-scan/tests/test_merge_findings.py`

**Interfaces:**
- Produces: `family_cap` for `performance` — `"C"` when `type_id == "TD-37"`, `"B"` without a `tool:` token, `None` otherwise; for `concerns` — `None` (base rule). `stats[family]["files_read"]` when a scout document carries the key.

- [ ] **Step 1: Write the failing tests**

In `tests/test_apply_verdicts.py`:

```python
@pytest.mark.parametrize(
    ("type_id", "confirmed", "verdict", "tier"),
    [
        ("TD-36", ["scout:performance", "tool:ruff"], "confirm", "A"),
        ("TD-36", ["scout:performance", "tool:ruff"], "downgrade", "C"),
        ("TD-36", ["scout:performance", "hotspot"], "confirm", "B"),   # capped: no tool token
        ("TD-36", ["scout:performance"], "confirm", "B"),
        ("TD-37", ["scout:performance", "tool:ruff", "hotspot"], "confirm", "C"),
        ("TD-37", ["scout:performance"], "confirm", "C"),
    ],
)
def test_performance_ladder(type_id, confirmed, verdict, tier) -> None:
    cand = _cand("performance", confirmed=confirmed, type_id=type_id)
    assert earned_tier(cand, _verdict(cand, verdict)) == tier


def test_td37_cap_sentence_names_runtime_evidence() -> None:
    from apply_verdicts import tier_reason

    cand = _cand("performance", confirmed=["scout:performance", "tool:ruff"], type_id="TD-37")
    reason = tier_reason(cand, _verdict(cand, "confirm"), selected=True)
    assert "runtime evidence" in reason and "capped at C" in reason


@pytest.mark.parametrize(
    ("confirmed", "verdict", "tier"),
    [
        (["scout:concerns"], "downgrade", "C"),
        (["scout:concerns"], "confirm", "B"),
        (["scout:concerns", "hotspot"], "confirm", "A"),
        (["scout:concerns", "coupling"], "confirm", "A"),
    ],
)
def test_concerns_ladder(confirmed, verdict, tier) -> None:
    cand = _cand("concerns", confirmed=confirmed, type_id="TD-10")
    assert earned_tier(cand, _verdict(cand, verdict)) == tier
    assert family_cap(cand) is None
```

In `tests/test_merge_findings.py`, find the existing test that runs `merge` over a workdir with a canned scout file (grep `scouts/` in the file) and add beside it, reusing its fixture pattern:

```python
def test_files_read_is_copied_into_stats(tmp_path: Path, corpus_workdir) -> None:
    """The concerns scout reports how many files it opened; merge records it so the
    read budget is auditable (spec 2026-09-12, section 4)."""
    workdir = corpus_workdir  # whatever the existing fixture is named
    scouts = workdir / "scouts"
    scouts.mkdir(exist_ok=True)
    (scouts / "concerns.json").write_text(json.dumps({
        "family": "concerns", "module": None, "findings": [], "open_questions": [],
        "looks_bad_but_fine": [], "not_assessed": [], "files_read": 17,
    }), encoding="utf-8")
    doc = merge(workdir, DEFAULTS)
    assert doc["stats"]["concerns"]["files_read"] == 17
```

Adapt the fixture name and `merge`'s call signature to what the file already uses — read the nearest existing test first.

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_apply_verdicts.py -k "performance or concerns or td37" skills/tech-debt-scan/tests/test_merge_findings.py -k files_read -q`
Expected: FAIL — TD-37 earns A; `KeyError: 'files_read'`.

- [ ] **Step 3: The two cap branches**

In `_family_cap_and_lift`, before `if family in ("doc-drift", "pipeline-infra") ...`:

```python
    if family == "performance":
        # Spec 2026-09-12, section 3. TD-37 is a cardinality claim: N+1, complexity,
        # "will not scale". Nothing static can prove the N, so it is capped at C
        # whatever the verifier says; the lift names what would be needed.
        if cand.get("type_id") == "TD-37":
            return "C", "runtime evidence, which this scan never reads"
        return (None if tool else "B"), "tool corroboration"
    if family == "concerns":
        # No cap: confirm is B, confirm plus a hotspot or coupling token is A --
        # the base rule in _tier_and_reason, stated here so the family is listed.
        return None, None
```

- [ ] **Step 4: `files_read` into stats**

In `merge_findings.py`'s scout-document loop, immediately after the line that reads the document (`doc = ...`) and before the `looks_bad_but_fine` loop, add:

```python
        files_read = doc.get("files_read")
        if isinstance(files_read, int) and not isinstance(files_read, bool):
            stats[family]["files_read"] = files_read
```

Confirm `stats[family]` is already a dict by that point (it is incremented at `:882`); if it is a `Counter`, assignment still works.

- [ ] **Step 5: Run the tests, then the whole suite**

Run: `python -m pytest skills/tech-debt-scan/tests/test_apply_verdicts.py skills/tech-debt-scan/tests/test_merge_findings.py -q` then `python -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Gates and commit**

```bash
git add skills/tech-debt-scan/scripts/apply_verdicts.py skills/tech-debt-scan/scripts/merge_findings.py skills/tech-debt-scan/tests/test_apply_verdicts.py skills/tech-debt-scan/tests/test_merge_findings.py
git commit -m "feat(tech-debt-scan): tier rules for the performance and concerns families

A TD-37 cardinality claim is capped at C with a reason naming runtime
evidence; a TD-36 smell needs a tool token to reach A. Concerns use the
base rule: confirm is B, confirm plus hotspot or coupling is A.
merge_findings records a scout's files_read into stats."
```

---

### Task 6: `plan_scan.py` — the index document, three lead kinds, two families, one concerns entry

**Confidence: 91%** — every touched function is read (`ScanDocs`, `load_docs`, `KIND_ORDER`/`KIND_TITLE`, `_pairs`, `_raw_leads`, `build_plan`'s chunked branch); residual is the chunked-plan exception for concerns, tested directly.

**Files:**
- Modify: `skills/tech-debt-scan/scripts/plan_scan.py` (`KIND_ORDER`/`KIND_TITLE` at `:86-100`; `ScanDocs`/`load_docs` at `:114-143`; `_pairs` at `:217`; `_raw_leads` at `:404`; `build_plan`'s `if chunked and leads:` at `~:770`)
- Test: `skills/tech-debt-scan/tests/test_plan_scan.py`

**Interfaces:**
- Consumes: `FAMILY_BLOCKS["performance"]`, `["concerns"]`; `render_scout_prompt(extra_block=)` (Task 1); `coupling.json` pair annotations (Task 2); `concern-index.json` (Task 3); `patterns.json` `performance` leads and ruff signals (Task 4).
- Produces: `ScanDocs.concern_index`; lead kinds `violation`, `interface`, `candidate`; prompts `prompts/scout-performance.md` and `prompts/scout-concerns.md`; `families_skipped` reason `no leads` for either when empty; exactly one `concerns` entry on a chunked plan.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_plan_scan.py`:

```python
def _docs_with(inventory: dict[str, Any], **extra: dict[str, Any]) -> ScanDocs:
    return ScanDocs(inventory=inventory, **extra)


def _min_inventory() -> dict[str, Any]:
    return {"root": "r", "total_files": 2, "total_loc": 20, "languages": ["python"],
            "git_available": True, "hotspot_band": ["src/hot.py"],
            "files": [{"path": "src/hot.py", "path_class": "source", "hotspot_score": 9.0,
                       "max_indent": 5, "fan_in_approx": 1, "churn": 3},
                      {"path": "src/cold.py", "path_class": "source", "hotspot_score": 0.0,
                       "max_indent": 1, "fan_in_approx": 1, "churn": 0}],
            "boundary_tooling": []}


def test_join_leads_render_under_their_own_headings() -> None:
    coupling = {"pairs": [
        {"a": "src/a.py", "b": "lib/b.py", "shared_commits": 4, "ratio": 0.5,
         "cross_directory": True, "has_edge": False, "edge_direction": None,
         "lead_kind": "modularity-violation"},
        {"a": "src/dep.py", "b": "src/hub.py", "shared_commits": 6, "ratio": 0.6,
         "cross_directory": False, "has_edge": True, "edge_direction": "a->b",
         "lead_kind": "unstable-interface"},
        {"a": "src/x.py", "b": "src/y.py", "shared_commits": 3, "ratio": 0.3,
         "cross_directory": False, "has_edge": True, "edge_direction": "both",
         "lead_kind": None},
    ], "cycles": [], "unstable_edges": [], "directories": [], "edges": []}
    leads = leads_for("architecture", _docs_with(_min_inventory(), coupling=coupling), DEFAULTS)
    kinds = {lead.kind for lead in leads}
    assert {"violation", "interface", "coupling"} <= kinds
    from plan_scan import render_leads
    text = render_leads(leads)
    assert "Co-change with no import edge (modularity violation):" in text
    assert "Co-change into a high-fan-in file (unstable interface):" in text
    assert "src/a.py <-> lib/b.py" in text and "no edge" in text
    assert "src/dep.py -> src/hub.py" in text


def test_performance_leads_come_from_patterns_tools_and_deep_band_files() -> None:
    patterns = {"leads": {"performance": [
        {"file": "src/cold.py", "line": 4, "rule": "io-in-loop", "quote": "open(p)",
         "path_class": "source", "extra": {"loop_line": 3}}]}, "satd": []}
    signals = {"signals": [{"tool": "ruff", "family": "performance", "kind": "perf-smell",
                            "file": "src/cold.py", "line_start": 9, "message": "PERF401",
                            "fact": False}]}
    docs = _docs_with(_min_inventory(), patterns=patterns, tool_signals=signals)
    leads = leads_for("performance", docs, DEFAULTS)
    kinds = [(lead.kind, lead.path) for lead in leads]
    assert ("hotspot", "src/hot.py") in kinds
    assert ("inventory", "src/hot.py") in kinds        # max_indent 5 on a band file
    assert ("inventory", "src/cold.py") not in kinds   # off band
    assert ("pattern", "src/cold.py") in kinds
    assert ("tool", "src/cold.py") in kinds


def test_concerns_leads_are_candidates_band_pairs_and_structure_never_files() -> None:
    index = {"candidates": [{"name": "format_amount", "tokens": ["format_amount", "formatAmount"],
                             "files": ["src/a.py", "lib/b.py"], "directories": ["lib", "src"],
                             "hotspot_touch": True, "hotspot_share": 0.5, "coupled": False}],
             "directories": [], "stats": {}}
    patterns = {"leads": {"performance": [
        {"file": "src/cold.py", "line": 4, "rule": "io-in-loop", "quote": "open(p)",
         "path_class": "source", "extra": {}}]}, "satd": []}
    docs = _docs_with(_min_inventory(), concern_index=index, patterns=patterns)
    leads = leads_for("concerns", docs, DEFAULTS)
    assert any(lead.kind == "candidate" and "format_amount" in lead.text for lead in leads)
    assert all(lead.kind != "pattern" and lead.kind != "tool" for lead in leads)


def test_concerns_prompt_carries_the_read_budget(tmp_path: Path) -> None:
    from inventory import write_json
    write_json(tmp_path / "inventory.json", _min_inventory())
    write_json(tmp_path / "coupling.json", {"pairs": [], "cycles": [], "unstable_edges": [],
                                             "directories": [], "edges": []})
    write_json(tmp_path / "concern-index.json", {"candidates": [
        {"name": "n", "tokens": ["n"], "files": ["src/a.py", "lib/b.py"],
         "directories": ["lib", "src"], "hotspot_touch": False, "hotspot_share": 0.0,
         "coupled": False}], "directories": [], "stats": {}})
    plan, prompts = build_plan(tmp_path, DEFAULTS, families=["concerns"], top=8)
    text = prompts["prompts/scout-concerns.md"]
    assert "at most 60 files" in text and "at most 10" in text and '"files_read"' in text
    assert plan["entries"][0]["output"] == "scouts/concerns.json"


def test_concerns_and_performance_skip_with_no_leads(tmp_path: Path) -> None:
    from inventory import write_json
    inv = _min_inventory()
    inv["hotspot_band"] = []
    inv["files"][0]["max_indent"] = 1
    write_json(tmp_path / "inventory.json", inv)
    plan, _ = build_plan(tmp_path, DEFAULTS, families="default", top=8)
    skipped = {s["family"]: s["reason"] for s in plan["families_skipped"]}
    assert skipped.get("concerns") == "no leads" and skipped.get("performance") == "no leads"


def test_concerns_gets_one_entry_on_a_chunked_plan(tmp_path: Path) -> None:
    from copy import deepcopy
    from inventory import write_json
    inv = _min_inventory()
    inv["files"] = [{"path": f"{d}/f{i}.py", "path_class": "source", "hotspot_score": 1.0,
                     "max_indent": 1, "fan_in_approx": 1, "churn": 1}
                    for d in ("alpha", "beta") for i in range(3)]
    inv["hotspot_band"] = ["alpha/f0.py", "beta/f0.py"]
    write_json(tmp_path / "inventory.json", inv)
    write_json(tmp_path / "coupling.json", {"pairs": [], "cycles": [], "unstable_edges": [],
                                             "directories": [], "edges": []})
    write_json(tmp_path / "concern-index.json", {"candidates": [
        {"name": "n", "tokens": ["n"], "files": ["alpha/f1.py", "beta/f1.py"],
         "directories": ["alpha", "beta"], "hotspot_touch": False, "hotspot_share": 0.0,
         "coupled": False}], "directories": [], "stats": {}})
    config = deepcopy(DEFAULTS)
    config["chunking"]["max_files"] = 2
    plan, prompts = build_plan(tmp_path, config, families=["concerns", "complex-units"], top=8)
    assert plan["chunked"] is True
    concerns = [e for e in plan["entries"] if e["family"] == "concerns"]
    assert len(concerns) == 1 and concerns[0]["module"] is None
    assert "prompts/scout-concerns.md" in prompts
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_plan_scan.py -k "join_leads or performance_leads or concerns" -q`
Expected: FAIL — `KeyError: 'performance'` from `_raw_leads`; `TypeError` on `concern_index`.

- [ ] **Step 3: Documents and kinds**

`ScanDocs` gains `concern_index: dict[str, Any] = field(default_factory=dict)`; `load_docs` reads `_read_json(workdir / "concern-index.json")` into it (docstring: "the five phase-1 documents"; the index is optional).

`KIND_ORDER` becomes:

```python
KIND_ORDER: Final[tuple[str, ...]] = (
    "hotspot", "coupling", "violation", "interface", "candidate", "pattern", "satd",
    "artefact", "cycle", "inventory", "tool", "docs", "tests",
)
```

`KIND_TITLE` gains:

```python
    "violation": "Co-change with no import edge (modularity violation)",
    "interface": "Co-change into a high-fan-in file (unstable interface)",
    "candidate": "Recurring definition names (candidates)",
```

- [ ] **Step 4: `_pairs` renders the join**

Replace `_pairs`:

```python
def _pairs(docs: ScanDocs, *, cross_only: bool = False) -> list[Lead]:
    """Coupled pairs as leads. A pair the graph join labelled gets its own kind
    (spec 2026-09-12, section 2); an unlabelled pair stays a plain coupling lead."""
    out: list[Lead] = []
    for pair in docs.coupling.get("pairs", []):
        if cross_only and not pair.get("cross_directory"):
            continue
        a, b = str(pair["a"]), str(pair["b"])
        shared, ratio = pair["shared_commits"], float(pair["ratio"])
        kind = pair.get("lead_kind")
        if kind == "modularity-violation":
            where = "cross-directory" if pair.get("cross_directory") else "same directory, weaker"
            out.append(Lead("violation", a,
                            None, f"<-> {b} shared={shared} ratio={ratio} no edge ({where})", ratio))
        elif kind == "unstable-interface":
            arrow = "->" if pair.get("edge_direction") in ("a->b", "both") else "<-"
            out.append(Lead("interface", a, None,
                            f"{arrow} {b} shared={shared} ratio={ratio} top-decile fan-in", ratio))
        else:
            out.append(Lead("coupling", a, None, f"<-> {b} shared={shared} ratio={ratio}", ratio))
    return out
```

`cross_only` keeps its meaning for the architecture family's plain pairs; join-labelled pairs are always rendered (the same-directory violation is marked weaker, per the spec).

- [ ] **Step 5: `_raw_leads` branches**

Add before `raise KeyError(family)`:

```python
    if family == "performance":
        band = set(docs.inventory.get("hotspot_band") or [])
        deep = _inventory_where(
            docs, lambda e: e["path"] in band and (_number(e.get("max_indent")) or 0.0) >= 4,
            "max_indent={max_indent} on a hotspot-band file",
        )
        return (_band(docs) + _pattern_leads(docs, "performance") + deep
                + _tool_leads(docs, family))
    if family == "concerns":
        candidates = [
            Lead("candidate", str(c["files"][0]), None,
                 f"{c['name']} ({', '.join(c.get('tokens') or [])}) defined in "
                 f"{len(c['files'])} files across {len(c['directories'])} directories: "
                 f"{', '.join(c['files'])}"
                 + (" [hotspot]" if c.get("hotspot_touch") else "")
                 + (" [coupled]" if c.get("coupled") else ""),
                 float(c.get("hotspot_share") or 0.0))
            for c in docs.concern_index.get("candidates") or []
            if isinstance(c, dict) and c.get("files")
        ]
        return _band(docs) + candidates + _pairs(docs) + _structure(docs)
```

Read `_inventory_where`'s signature at `:320` before using it: it takes `(docs, predicate, text_template)` where the template is formatted with the entry's fields — match that exactly.

- [ ] **Step 6: The concerns prompt block and the chunked-plan exception**

Add a module constant:

```python
CONCERNS_EXTRA_BLOCK: Final[str] = (
    "Read budget: this scout receives no file leads. Read at most 60 files to confirm the "
    "candidates below and at most 10 more of your own choosing for drift, naming each of "
    "those in not_assessed with a one-line reason. Report the total as \"files_read\" in "
    "your output. Report at most 6 findings."
)
```

In `build_plan`, change the dispatch condition `if chunked and leads:` to `if chunked and leads and family != "concerns":` with the comment: `# The concerns index is repository-wide by construction (spec 2026-09-12, 4); scatter across modules is its point, so it never splits.` In both `render_scout_prompt` calls, pass `extra_block=CONCERNS_EXTRA_BLOCK if family == "concerns" else ""`.

- [ ] **Step 7: Run the tests, then the whole suite**

Run: `python -m pytest skills/tech-debt-scan/tests/test_plan_scan.py -q` then `python -m pytest -q`
Expected: PASS. The plan goldens (`tests/golden/chunked-plan-*.json`, per-fixture `scan-plan.json` if present) will change: `families_skipped` gains the two families with `no leads` on fixtures that have no candidates. Regenerate with `UPDATE_GOLDENS=1` and confirm the diff is only those entries.

- [ ] **Step 8: Gates and commit**

```bash
git add skills/tech-debt-scan/scripts/plan_scan.py skills/tech-debt-scan/tests/test_plan_scan.py skills/tech-debt-scan/tests/golden
git commit -m "feat(tech-debt-scan): plan the performance and concerns scouts

Join-labelled pairs render as modularity-violation and unstable-interface
leads; performance leads come from patterns, ruff and deep-nesting band
files; the concerns scout receives the candidate index, band, pairs and
structure, a read budget, and exactly one entry even on a chunked plan."
```

---

### Task 7: Corpus — planted items, decoys, canned goldens

**Confidence: 88%** → mitigated to 91% by the two-part structure below. Residual: `history.yaml` replay re-hashes commits after any edited one, and canned scout replies quote spans — so every new file goes into a **new trailing commit** (the file's own header says so) and the canned replies are written after the fixture is replayed and the real line numbers read.

**Files:**
- Modify: `skills/tech-debt-scan/tests/fixtures/corpus/service-py/{files,history.yaml,planted.json}`, same for `web-ts` and `mixed-decoys`
- Modify: `skills/tech-debt-scan/tests/golden/<fixture>/scouts/{performance,concerns}.json` (new), `verdicts/*`, then the regenerated downstream goldens
- Modify: `skills/tech-debt-scan/tests/test_e2e.py`, `skills/tech-debt-scan/tests/test_chain_goldens.py` (only if a hard-coded family count or planted count exists)

**Interfaces:**
- Consumes: everything from Tasks 1–6.
- Produces: `planted.json` entries with `family` `performance` (TD-36, `expect_tier: A` where ruff fires, else B) and `concerns` (TD-10, `expect_tier: B` or A when coupled); decoys `dN` for each.

- [ ] **Step 1 (7a): Add the fixture files as a new trailing commit per fixture**

`service-py` — append to `history.yaml` a final commit:

```yaml
  - author: "Ada Lovelace <ada@example.com>"
    date: "2025-06-01T10:00:00+00:00"
    subject: "feat: statement export and billing formatter"
    files:
      src/pay/export.py: "@final"
      src/billing/__init__.py: ""
      src/billing/format.py: "@final"
      src/billing/parse.py: "@final"
      src/pay/parse.py: "@final"
```

and create under `files/`:

`src/pay/export.py` — the planted TD-36 (I/O in a loop, ruff-visible manual list comprehension) and the decoy (bounded enum loop, import-time regex):

```python
"""Statement export."""
import re
from enum import Enum

HEADER_RE = re.compile(r"^#")  # compiled once at import: not a loop cost (decoy)


class Kind(Enum):
    CARD = "card"
    BANK = "bank"


def export_statements(paths):
    lines = []
    for path in paths:
        handle = open(path)  # planted TD-36: I/O inside the loop
        for line in handle:
            lines.append(line.strip())
    return lines


def kind_labels():
    labels = []
    for kind in Kind:  # decoy: a loop over an enum has a bounded N
        labels.append(kind.value.upper())
    return labels
```

`src/pay/parse.py` and `src/billing/parse.py` — the concerns decoy (an adapter pattern; `parse` is stoplisted, so `parse_csv`/`parse_json` are the names):

```python
"""CSV statement adapter."""


def parse_csv(text):
    return [row.split(",") for row in text.splitlines()]
```
```python
"""JSON statement adapter."""
import json


def parse_json(text):
    return json.loads(text)
```

`src/billing/format.py` — the planted concerns item: `format_amount` already exists in `src/pay/utils.py`? Read that file first; if it does not define `format_amount`, add to the same trailing commit a one-function change is NOT allowed (it would edit an existing file and re-hash) — instead define the pair in the two NEW files: `src/billing/format.py` with `def format_amount(cents):` and `src/pay/export.py` gains `def format_amount(cents):` (same body, different directory). Both are new files in the trailing commit.

`planted.json` — append to `planted`:

```json
    {"id": "p21", "family": "performance", "type_id": "TD-36", "path": "src/pay/export.py", "lines": [17, 17], "expect_tier": "A"},
    {"id": "p22", "family": "concerns", "type_id": "TD-10", "path": "src/billing/format.py", "lines": [1, 6], "expect_tier": "B"}
```

and to `decoys`:

```json
    {"id": "d9", "family": "performance", "path": "src/pay/export.py", "why": "a loop over an enum has a bounded N; the regex is compiled once at import", "sources": ["scout:performance", "pattern:sort-in-loop", "tool:ruff"]},
    {"id": "d10", "family": "concerns", "path": "src/billing/parse.py", "why": "one parse_<format> per format is an adapter pattern, not scatter", "sources": ["scout:concerns"]}
```

Line numbers in `p21`/`p22` must be read from the file after writing it — do not trust the numbers above.

`web-ts` — the same shape in TypeScript: a trailing commit adding `src/report/export.ts` (a `for...of` with `await fetch(row.url)` inside; a decoy loop over a three-member `const KINDS = [...] as const`), `src/report/format.ts` and `src/cart/format.ts` both exporting `formatAmount`, and `src/report/parseCsv.ts` / `src/report/parseJson.ts` as the adapter decoy. Planted `p*`/decoy `d*` ids continue that fixture's numbering.

`mixed-decoys` — decoys only, one per family (that fixture's role is precision): a bounded-enum loop and an adapter pair, ids continuing its numbering, no planted items.

Replay each fixture (`python skills/tech-debt-scan/tests/helpers/make_history.py <name> <tmp>`) and confirm the files land and `git log` shows the new trailing commit last.

- [ ] **Step 2 (7a): Run the fixture-level tests**

Run: `python -m pytest skills/tech-debt-scan/tests/test_inventory_v2.py skills/tech-debt-scan/tests/test_patterns.py skills/tech-debt-scan/tests/test_concern_index.py -q`
Expected: PASS; `patterns.json` over `service-py` now carries an `io-in-loop` lead at the planted line, and the concern index over `service-py` lists `format_amount` with two directories.

- [ ] **Step 3 (7a): Commit the corpus**

```bash
git add skills/tech-debt-scan/tests/fixtures/corpus
git commit -m "test(tech-debt-scan): plant performance and concerns items and decoys in the corpus

New trailing commits per fixture so no existing commit re-hashes: an
I/O-in-loop smell and a bounded-enum decoy, a cross-directory
format_amount and an adapter-pattern decoy."
```

- [ ] **Step 4 (7b): Write the canned scout and verdict goldens**

For each fixture with planted items (`service-py`, `web-ts`), write `tests/golden/<fixture>/scouts/performance.json` and `scouts/concerns.json` in the exact `SCOUT_OUTPUT_SCHEMA` shape, quoting the planted lines verbatim (copy them from the replayed fixture; `merge_findings` discards a finding whose quote is not on disk). The performance scout reply reports the planted TD-36 with `severity: 3`, `signals_cited: ["pattern:io-in-loop", "tool:ruff"]`, and lists the enum loop and the import-time regex under `looks_bad_but_fine`; the concerns reply reports `format_amount` with `type_id: "TD-10"`, `files_read: 4`, and lists `parse_csv`/`parse_json` under `looks_bad_but_fine`. For `mixed-decoys`, write replies with empty `findings` and the decoys under `looks_bad_but_fine`.

Then run the chain up to `verify_prompts` on each fixture (the `_signals` helper in `test_plan_scan.py` plus `build_plan`, `merge`, `build_verify_plan` — mirror `test_e2e.py`'s sequence) and write `verdicts/verify-NN.json` entries for the new candidates: `confirm` for the planted items, `downgrade` for the decoys with `trap_matched` naming the trap.

- [ ] **Step 5 (7b): Regenerate the downstream goldens and run the chain tests**

Run: `UPDATE_GOLDENS=1 python -m pytest skills/tech-debt-scan/tests/test_chain_goldens.py -q` then `python -m pytest skills/tech-debt-scan/tests/test_chain_goldens.py skills/tech-debt-scan/tests/test_e2e.py skills/tech-debt-scan/tests/test_evaluate.py -q`
Expected: PASS. Inspect `git diff --stat tests/golden`: `candidates.json`, `verified.json`, `ranked.json`, `diff.json`, `findings.json` and `design.md` change on the two planted fixtures; `design.md`'s `families_run` lists both new families; `test_chain_goldens.test_chain_matches_goldens_and_meets_the_corpus_bar` reports the two families' tier-A precision at or above the bar. If a planted TD-36 lands at B because ruff did not fire on the fixture line, change the fixture line to one of the six codes' shapes (a manual list comprehension, `PERF401`) rather than lowering the expectation.

- [ ] **Step 6 (7b): Whole suite, gates, commit**

Run: `python -m pytest -q && python -m ruff check && python -m mypy --strict`

```bash
git add skills/tech-debt-scan/tests/golden skills/tech-debt-scan/tests/test_e2e.py skills/tech-debt-scan/tests/test_chain_goldens.py
git commit -m "test(tech-debt-scan): goldens for the performance and concerns families

Canned scout and verifier replies over the planted items and decoys,
and the regenerated downstream goldens; the corpus bar now covers both
families."
```

---

### Task 8: Documentation and the lint gate

**Confidence: 95%** — prose plus `skill_check.py`, which mechanically verifies every documented command against its script.

**Files:**
- Modify: `skills/tech-debt-scan/SKILL.md` (the overview's "one of fourteen" at `:42`, `--deep` at `:79`, a new step `1a` after step 1 at `:113`, the family list, the token-budget table at `:210-220`, Caveats)
- Modify: `docs/architecture.md` (`:55`, `:156` the plan_scan row, `:564`, `:758`; a new row for `concern_index.py`; the join and the two tier rules under the baseline/tiering prose)
- Modify: `README.md` (`:5`, `:57`, `:231`, `:237`)
- Modify: `docs/evaluation-log.md`

- [ ] **Step 1: SKILL.md**

Insert after step 1:

```markdown
1a. `python scripts/concern_index.py <repo> --workdir .tech-debt` writes
    `concern-index.json`: per-directory aggregates and at most 40 definition
    names that recur across directories, the concerns scout's only leads.
    Exit 2 when `coupling.json` predates the graph join; re-run step 1.
```

Change every "fourteen" to "sixteen" where it counts families (`:42`, `:79`, the budget table's deep column `16, and on a chunked plan at most families x chunking.max_modules (16 x 8)`), the default column of the budget table from `12` to `14`, and add to Caveats:

```markdown
- **Performance is static only.** A TD-36 local smell can reach tier A on a
  linter hit plus a verifier confirm; a TD-37 cardinality claim (N+1,
  complexity, "will not scale") is capped at tier C however confident the
  reader is, because the N lives at runtime and this scan never reads it.
- **The concerns scout reads without file leads**, bounded by the 40-candidate
  index and an instructed 60 + 10 file budget that `merge_findings` records
  as `stats.concerns.files_read` but cannot enforce.
```

- [ ] **Step 2: `docs/architecture.md`, `README.md`, `docs/evaluation-log.md`**

Add a `concern_index.py` row to the chain table beside `inventory.py`'s; describe the join's three pair fields and `edges` under the `coupling.json` prose; add both tier rules under the tiering section; change the family counts. In `docs/evaluation-log.md`, add a dated entry recording the two families' planted items, decoys and the precision numbers from Task 7's run.

- [ ] **Step 3: The gates**

Run: `python skills/tech-debt-scan/scripts/skill_check.py`
Expected: `ok: all SKILL.md commands match their scripts`

Run: `python -m pytest -q && python -m ruff check && python -m mypy --strict`
Expected: all clean.

- [ ] **Step 4: Commit**

```bash
git add skills/tech-debt-scan/SKILL.md docs/architecture.md README.md docs/evaluation-log.md
git commit -m "docs(tech-debt-scan): document the performance and concerns families and the graph join"
```

---

## Self-Review

**Spec coverage.** Section 2 (join) → Task 2 (annotation), Task 6 (rendering), Task 1 (architecture questions and trap). Section 3 (performance) → Task 1 (taxonomy, block, sets), Task 4 (leads), Task 5 (tiering), Task 6 (plan), Task 7 (corpus). Section 4 (concern index and scout) → Task 3, Task 1 (block, `files_read`, `extra_block`), Task 5 (`files_read` into stats), Task 6 (leads, prompt block, chunked exception), Task 7 (corpus). Section 5 (cross-cutting) → Task 8 and the goldens in Tasks 2, 4, 6, 7. Section 6 (tests) → each task's Step 1; `test_skill_check.py` is exercised by Task 8's gate. Section 7's build order is this task order. Section 8 (migration) → Task 3's exit-2 test and Task 6's tolerance of a missing `lead_kind`. Success criterion 8 (a `quick` scan is byte-identical) holds by construction: `quick` is untouched and neither new family is in it.

**Placeholder scan.** No TBD/TODO. Task 5's merge test and Task 6's `_inventory_where` use tell the implementer to read a named neighbouring function for an exact signature rather than guess — that is a verify-before-commit instruction, not a placeholder. Task 7's line numbers are explicitly to be read from the replayed fixture.

**Type consistency.** `render_scout_prompt(extra_block=)` defined in Task 1, used in Task 6. `_annotate_pairs(pairs, graph)` in Task 2, exercised through `build_all` in Task 2's last test and consumed by name (`lead_kind`, `edge_direction`) in Task 6. `build_concern_index(root, inventory, coupling)` and the `candidates[]` field names (`name`, `tokens`, `files`, `directories`, `hotspot_touch`, `hotspot_share`, `coupled`) in Task 3 match what Task 6 reads. Lead kinds `violation`, `interface`, `candidate` are defined in Task 6's `KIND_ORDER` before `_pairs`/`_raw_leads` emit them. `stats[family]["files_read"]` in Task 5 matches the SKILL.md sentence in Task 8.

**Deviation carried through:** the spec's tier table row "TD-36, tool hit, verifier downgrades → B" is wrong against the pipeline's existing rule that a `downgrade` verdict is tier C for every family (`_tier_and_reason`, `apply_verdicts.py:150`); Task 5's ladder asserts C and the spec should be corrected to match in Task 8's docs pass.
