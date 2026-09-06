# tech-debt-scan v2 Phase 3 (report and cut-over) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the ranked chain into `design.md` and `findings.json`, promote v2 findings into PBI bundles, and cut `/tech-debt-scan` and `/tech-debt-promote` over to v2 without tools or baseline.

**Architecture:** `design_writer.py render` reads `ranked.json`, `verified.json`, `candidates.json`, `scan-plan.json`, `notes.json` and the inventory from `--workdir` and writes `design.md` (frontmatter, top N, below the cut, four negative-space sections) plus `findings.json`, self-checking through `design_parser.parse_design`. `design_writer.py notes-prompt` renders `prompts/notes.md` for the one remediation-note agent. `design_parser.py` ends a finding section at an H1 as well as an H2 so the negative-space sections never land in a PBI body. `bundle_writer.py` and `promote.py` carry the v2 anchor keys and body sections. SKILL.md becomes the v2 fourteen-step scan and four-step promote list, `build_synthesis_prompt.py` and `validate_confidence` are deleted, and the v1 golden is kept as the compatibility case.

**Tech Stack:** Python 3.11+, pyyaml (only runtime dependency), pytest, ruff, mypy strict.

**Spec:** `docs/superpowers/specs/2026-09-04-tech-debt-scan-v2-design.md` (binding). Sections 4.11 (design_writer and the parser boundary), 4.12 (promote and bundle_writer), 4.13 (validation), 5 (SKILL.md v2), 6 (tests), 8 (compatibility), 11 (phase 3 scope). Two amendments this plan makes are named in Task 3 and Task 4.

**Branch:** `feat/tech-debt-scan-v2-phase-3`, already created off `main` (2b4499c) and checked out in the main checkout at `C:/Users/gethi/source/claude-skills` (no linked worktree: the standards doc records Windows worktree-removal hazards).

## Global Constraints

Copied from spec sections 0, 3.3 and 5; every task's requirements include these.

- Python 3.11+; pyyaml is the only runtime dependency; every script uses the standard library plus `yaml`.
- Every script is direct-path invocable as `python scripts/<name>.py` from `skills/tech-debt-scan/`; sibling imports are flat top-level imports (`from evidence import fingerprint`), never package imports.
- Every v2 script accepts `--workdir` (default `.tech-debt`) and reads and writes the pinned file names inside it.
- Rendered output is LF-only: build text as `"\n".join(parts) + "\n"` and write with `write_bytes(text.encode("utf-8"))`. JSON goes through `inventory.write_json`.
- JSON keys are emitted in the spec's pinned order; tests pin the order with `list(doc)` assertions.
- `skill_check.py` constraints (spec 5): any script with subcommands keeps every `choices=` option on a subparser, because the lint takes the first `{a,b}` group in the top-level help as the subcommand list; flag names stay distinct within a script, because flag matching is substring-based.
- Language-agnostic rule (spec 0(d), 3.3): the extension map in `inventory.py` is the only language-aware table; any per-language branch anywhere else is a defect. `test_no_script_branches_on_a_language_name` globs every script.
- No live LLM in tests; the `live` pytest marker never runs in CI. This phase runs no live agent at all.
- CLI convention established in phase 2: `_main` wraps its work in `try/except (ConfigError, OSError, ValueError, KeyError)` printing `error: ...` to stderr and returning 2, with `isinstance` guards raising `ValueError` for valid-JSON-but-wrong-shape inputs.
- Gate for every task and for the PR, from the repository root: `python -m ruff check .`, `python -m mypy`, `python skills/tech-debt-scan/scripts/skill_check.py`, `python -m pytest -q`; all green.
- Windows-safe: list argv everywhere; forward-slashed paths in output.
- Docs ship with code (spec 0(c)): `docs/architecture.md`, `README.md` and `SKILL.md` are updated in the same task as the code they describe; every token verified against the code.
- Commit trailers: every `git commit` message ends with the line `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`. Conventional-commit subjects.
- Compatibility (spec 8): any v1 `design.md` still parses and promotes byte-identically to `tests/golden/bundle/`; `category` is read as the family; a v1 `confidence` anchor value is parsed and discarded.

## Guardrails (from project memory and standards)

- [[keep-docs-in-sync]] (confidence 0.95, useful 29x): SKILL.md, README and architecture rows change in the same commit as the code; verify every token in a rewritten doc line against the source; `skill_check.py` is the automated half and `test_real_skill_md_passes` is its gate.
- [[redaction-invariant]] (phase 2, twice): every string that reaches a durable output passes through `redaction.redact` unless a later stage must match it raw. `design.md` and `findings.json` are durable and shared, so every quote, proof, note and question they carry is redacted at write. Their inputs are already redacted; redacting again is idempotent and is the last writer's job.
- [[verify-red-is-red]] (confidence 0.75): every RED step below names the exact failure expected; where an earlier layer could already satisfy the assertion, the step says so.
- [[cli-guard-convention]] (phase 2, twice): a new or touched `_main` gets the exception tuple and the shape guards; `json.loads(...)[key]` on a list raises `TypeError`, which escapes a `(OSError, ValueError)` net.
- Dismissed: worktree-on-Windows hazards (no worktree used); the `claude -p` harness lessons (no live agent this phase); mkstemp/fdopen (no fd handling); TypeScript Partial (no TypeScript).

## File structure

| File | Task | Responsibility |
|---|---|---|
| `skills/tech-debt-scan/scripts/plan_scan.py` | 1 | per-kind bounds on SATD and inventory leads |
| `skills/tech-debt-scan/scripts/verify_prompts.py` | 1 | a sentinel so a failed reference graph is not rebuilt per batch |
| `skills/tech-debt-scan/scripts/merge_findings.py` | 1 | a corrupt scout file is counted, not fatal; docstring note on rule findings and path-class disables |
| `skills/tech-debt-scan/scripts/validation.py` | 2 | `validate_confidence` and `VALID_CONFIDENCES` deleted |
| `skills/tech-debt-scan/scripts/design_parser.py` | 2 | H1 section boundary; `OPTIONAL_KEYS` extended |
| `skills/tech-debt-scan/scripts/slugs.py` | 3 | leaf module: deterministic `slugify` and `unique_slugs` |
| `skills/tech-debt-scan/scripts/design_writer.py` | 3, 4, 5 | `render` (frontmatter, header, top N; then the negative-space sections and `findings.json`) and `notes-prompt` |
| `skills/tech-debt-scan/scripts/bundle_writer.py` | 6 | v2 PBI frontmatter keys and body sections; `PLAN.md` acceptance criteria |
| `skills/tech-debt-scan/scripts/promote.py` | 6 | v2 statuses documented; exit code 6 reserved for phase 5 |
| `skills/tech-debt-scan/SKILL.md` | 8 | the v2 fourteen-step scan and four-step promote lists, without steps 4 and 11 |
| `skills/tech-debt-scan/scripts/build_synthesis_prompt.py` | 8 | deleted |
| `skills/tech-debt-scan/tests/golden/design-v1.md`, `.../golden/<fixture>/design.md`, `.../golden/<fixture>/findings.json`, `.../golden/notes-prompt.md` | 2, 7 | the v1 compatibility document and the v2 per-fixture goldens |
| `skills/tech-debt-scan/tests/test_design_parser.py`, `test_design_writer.py`, `test_bundle_writer.py`, `test_promote.py`, `test_e2e.py`, `test_validation.py`, `test_skill_check.py` | 2, 3 to 8 | rewritten or extended per the spec's test lists |
| `docs/architecture.md`, `README.md` | 1, 3 to 9 | script table, output-formats table, status paragraph |

## Task overview and confidence

Every task is at or above the 92 percent floor after the mitigations embedded in its text.

| Task | Deliverable | Confidence |
|---|---|---|
| 1 | phase 2 carry-forwards (lead bounds, graph sentinel, corrupt scout file) | 95% |
| 2 | `validation.py` cleanup, `design_parser.py` H1 boundary and keys, `design-v1.md` | 95% |
| 3 | `slugs.py`; `design_writer render` frontmatter, header and the top-N sections | 93% |
| 4 | `design_writer render` below-the-cut and the four negative-space sections; `findings.json` | 93% |
| 5 | `design_writer notes-prompt`; notes wired into `render` | 94% |
| 6 | `bundle_writer.py` and `promote.py` v2 | 94% |
| 7 | per-fixture `design.md` and `findings.json` goldens; the e2e test | 92% |
| 8 | SKILL.md v2; delete `build_synthesis_prompt.py`; docs rewrite | 93% |
| 9 | full gate, docs sweep, PR preparation | 96% |

**The single largest mitigation** is the worked example in Task 3, Step 0: the exact bytes of a small v2 `design.md`, written out in full. Tasks 3, 4, 5 and 7 transcribe against it rather than inventing a layout, and Task 7's goldens are regenerated from it. Read it before writing any renderer code.

---

### Task 1: phase 2 carry-forwards

**Files:**
- Modify: `skills/tech-debt-scan/scripts/plan_scan.py` (`leads_for`, around the `KIND_ORDER` sort and the pattern cap)
- Modify: `skills/tech-debt-scan/scripts/verify_prompts.py` (`_reference_edges`, `render_verify_prompt`, `build_verify_plan`)
- Modify: `skills/tech-debt-scan/scripts/merge_findings.py` (`_read_json` use in `merge`, module docstring)
- Test: `skills/tech-debt-scan/tests/test_plan_scan.py`, `test_verify_prompts.py`, `test_merge_findings.py`
- Modify: `docs/architecture.md` (the `plan_scan.py` and `merge_findings.py` rows)

**Interfaces:**
- Consumes: `LEAD_CAP` (40) and `KIND_ORDER` in `plan_scan.py`; `_reference_edges` returning `list[tuple[str, str]] | None`; `merge_findings._read_json`.
- Produces: `KIND_CAPS: dict[str, int]` in `plan_scan.py` (`{"satd": 40, "inventory": 40}`, every other kind uncapped); `GRAPH_FAILED: list[tuple[str, str]]` sentinel in `verify_prompts.py`; a `read_failed` stat key in `merge_findings` stats.

**Confidence:** 95% (three independent, small, guarded changes against code read at plan-write time; each has one named test and none crosses a module boundary).

- [ ] **Step 1: Write the failing tests**

In `tests/test_plan_scan.py`, add:

```python
def test_satd_and_inventory_leads_are_capped_per_kind(
    corpus_workdirs: dict[str, tuple[Path, Path]]
) -> None:
    """A TODO-heavy repository must not blow the prompt: SATD and inventory leads cap too."""
    from copy import deepcopy

    from plan_scan import KIND_CAPS, LEAD_CAP, ScanDocs, leads_for, load_docs

    _, workdir = corpus_workdirs["service-py"]
    docs = load_docs(workdir)
    inflated = ScanDocs(
        inventory=docs.inventory,
        coupling=docs.coupling,
        patterns=deepcopy(docs.patterns),
        rules=docs.rules,
    )
    inflated.patterns["satd"] = [
        {"marker": "TODO", "file": f"src/z{i}.py", "line": 1, "quote": "# TODO x",
         "ticket_ref": False, "age_days": None, "commits_since": None, "path_class": "source"}
        for i in range(80)
    ] + list(inflated.patterns["satd"])
    leads = leads_for("half-finished", inflated, DEFAULTS)
    by_kind: dict[str, int] = {}
    for lead in leads:
        by_kind[lead.kind] = by_kind.get(lead.kind, 0) + 1
    assert by_kind["satd"] == KIND_CAPS["satd"] == LEAD_CAP
    assert by_kind.get("pattern", 0) <= LEAD_CAP
    assert by_kind["hotspot"] == len(docs.inventory["hotspot_band"]), "the band is never capped"
```

In `tests/test_verify_prompts.py`, add:

```python
def test_a_failed_graph_is_not_rebuilt_for_every_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A graph build that fails once must not be retried per batch (it re-reads every file)."""
    import verify_prompts as vp

    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    for name in ("alpha", "bravo", "charlie"):
        (repo / "src" / f"{name}.py").write_text("\n".join(f"line {i}" for i in range(1, 40)) + "\n",
                                                 encoding="utf-8")
    inventory, coupling = build_all(repo, config=DEFAULTS)
    workdir = tmp_path / "wd"
    write_outputs(inventory, coupling, workdir)
    cands = [_cand("dead-code", f"src/{n}.py", i, 2)
             for n in ("alpha", "bravo", "charlie") for i in range(1, 4)]
    write_json(workdir / "candidates.json", {"schema_version": 2, "candidates": cands,
                                             "open_questions": [], "looks_bad_but_fine": [],
                                             "stats": {}})
    calls: list[int] = []

    def boom(*_args: Any, **_kwargs: Any) -> Any:
        calls.append(1)
        raise RuntimeError("graph unavailable")

    monkeypatch.setattr(vp, "build_reference_graph", boom)
    plan, prompts = vp.build_verify_plan(workdir, repo, DEFAULTS, top=5)
    assert len(plan["batches"]) >= 2
    assert len(calls) == 1, "the failed build must be attempted once, not once per batch"
    assert all("approximate referrers: not computed" in text for text in prompts.values())
```

In `tests/test_merge_findings.py`, add:

```python
def test_a_corrupt_scout_file_is_counted_not_fatal(tmp_path: Path) -> None:
    """One malformed scout document must not discard thirteen good ones."""
    repo, workdir = _repo(tmp_path)
    _scout(workdir, "error-masking", [
        _finding("error-masking", "swallowed", "src/pay.py", 7, 8, "except Exception:\n        pass"),
    ])
    (workdir / "scouts" / "security.json").write_bytes(b'{"family": "security", "findings": [')
    doc = merge(workdir, repo, DEFAULTS)
    assert [c["title"] for c in doc["candidates"] if c["source"] == "scout"] == ["swallowed"]
    assert doc["stats"]["security"]["read_failed"] == 1
    assert doc["stats"]["security"]["raw"] == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

```
python -m pytest skills/tech-debt-scan/tests/test_plan_scan.py -k capped_per_kind -q
python -m pytest skills/tech-debt-scan/tests/test_verify_prompts.py -k failed_graph -q
python -m pytest skills/tech-debt-scan/tests/test_merge_findings.py -k corrupt_scout -q
```
Expected: `ImportError: cannot import name 'KIND_CAPS'`; `assert 2 == 1` (the graph is rebuilt per batch); `json.decoder.JSONDecodeError` escaping `merge` (the corrupt file aborts the whole run today).

- [ ] **Step 3: `plan_scan.py` per-kind caps**

Add beside `LEAD_CAP`:

```python
# Spec 4.6 caps pattern leads and tool signals at LEAD_CAP; the SATD table and the
# per-file inventory leads are unbounded in the documents and are capped here for the
# same reason (a TODO-heavy or large repository would otherwise fill the prompt). The
# hotspot band is bounded by hotspot_band.max, and the coupling, artefact, cycle, docs
# and tests kinds are bounded by the repository's own structure, so they are emitted whole.
KIND_CAPS: Final[dict[str, int]] = {"pattern": LEAD_CAP, "satd": LEAD_CAP, "inventory": LEAD_CAP}
```

In `leads_for`, replace the pattern-only cap with a per-kind counter over `KIND_CAPS` (a kind absent from the mapping is uncapped), keeping the existing sort so band-first ordering inside each kind is unchanged. Update the `leads_for` docstring and the module docstring's cap sentence.

- [ ] **Step 4: `verify_prompts.py` graph sentinel**

Add beside the other constants:

```python
# `_reference_edges` returns None when the graph cannot be built. `render_verify_prompt`
# treats `edges=None` as "not supplied, build one", so passing that None through would
# rebuild (and re-read every source file) once per batch. build_verify_plan substitutes
# this sentinel instead: an empty edge list that renders "not computed" exactly as a
# failure does, without a second attempt.
GRAPH_FAILED: Final[list[tuple[str, str]]] = []
```

In `build_verify_plan`, when `_reference_edges` returns `None`, pass `GRAPH_FAILED`. In `_referrers`, an empty edge list already yields no referrers; make it render `not computed` rather than `none found` when the list is `GRAPH_FAILED` (compare with `is`, not `==`, and say so in a comment). Update the docstring.

- [ ] **Step 5: `merge_findings.py` corrupt scout file**

In `merge`, wrap the per-entry scout read in `try/except (OSError, ValueError)`; on failure set `stats[family]["read_failed"] = 1` and continue, exactly as the missing-file path does. Add `read_failed` to the docstring's stats list beside `missing_file` and `dropped_reasons` (all three are out-of-band keys, appended only when they apply). Add the ruled sentence to the module docstring: rule findings are not re-checked against path-class disables here because `rules.py` drops disabled-class artefacts before emitting them.

- [ ] **Step 6: Run the tests to verify they pass**

```
python -m pytest skills/tech-debt-scan/tests/test_plan_scan.py skills/tech-debt-scan/tests/test_verify_prompts.py skills/tech-debt-scan/tests/test_merge_findings.py skills/tech-debt-scan/tests/test_chain_goldens.py -q
```
The chain goldens must stay byte-identical: no fixture has 40 SATD or inventory leads for any family, and no fixture's graph fails. If a golden does move, stop and report which and why rather than regenerating.

- [ ] **Step 7: Docs, gate, commit**

`docs/architecture.md`: the `plan_scan.py` row states that pattern, SATD and inventory leads are each capped at 40 band-first while the other kinds are emitted whole; the `merge_findings.py` row states that an unreadable or malformed scout file is counted under `read_failed` and never aborts the merge. Run the gate. Commit:

```
fix(tech-debt-scan): cap SATD and inventory leads, keep a failed graph from rebuilding, survive a corrupt scout file
```

---

### Task 2: `validation.py` cleanup, the parser's H1 boundary, and the v1 golden

**Files:**
- Modify: `skills/tech-debt-scan/scripts/validation.py` (delete `validate_confidence`, `VALID_CONFIDENCES`)
- Modify: `skills/tech-debt-scan/scripts/design_parser.py` (`OPTIONAL_KEYS`, the section-end condition, docstring)
- Rename: `skills/tech-debt-scan/tests/golden/design.md` to `skills/tech-debt-scan/tests/golden/design-v1.md` (`git mv`)
- Modify: `skills/tech-debt-scan/tests/test_validation.py`, `test_design_parser.py`, `test_design_writer.py`, `test_e2e.py` (golden path only, until Task 7 rewrites the last two)

**Interfaces:**
- Consumes: `validate_slug`, `validate_status` (unchanged).
- Produces: `OPTIONAL_KEYS = ("debt_type", "effort", "confidence", "family", "fingerprint", "tier", "priority", "type_id", "diff", "reason", "until")`; `parse_design` ends a finding section at the next `## ` **or** the next `# ` heading.

**Confidence:** 95% (the parser change is one condition with a named helper; the deletion's only caller is `build_synthesis_prompt.py`, which Task 8 deletes, so Step 3 keeps a shim-free import list by checking the grep first).

- [ ] **Step 1: Confirm the deletion is safe, then write the failing tests**

Run `grep -rn "validate_confidence\|VALID_CONFIDENCES" skills/tech-debt-scan/`. Expected callers: `scripts/validation.py` (the definition), `scripts/build_synthesis_prompt.py` (deleted in Task 8), `tests/test_validation.py`, `tests/test_build_synthesis_prompt.py` (deleted in Task 8). If any other caller appears, stop and report it.

Because `build_synthesis_prompt.py` still imports `validate_confidence` until Task 8, this task removes the *validator* and leaves the import working by deleting the import line in `build_synthesis_prompt.py` too (a two-line edit in a file Task 8 deletes wholesale; `validate_confidence(...)` calls in it become no-ops by deleting the call, and its own test's confidence cases are dropped). State that in the report.

In `tests/test_design_parser.py`, add:

```python
def test_a_finding_section_ends_at_an_h1(tmp_path: Path) -> None:
    """Spec 4.11: negative-space sections must never land in a finding's body (and its PBI)."""
    path = tmp_path / "design.md"
    path.write_bytes(
        "\n".join([
            "## Only finding",
            "",
            "```yaml",
            "status: pending",
            "slug: only-finding",
            "severity: 3",
            "category: error-masking",
            "```",
            "",
            "### Proof",
            "",
            "the body",
            "",
            "# Considered and rejected",
            "",
            "- not part of the body",
            "",
        ]).encode("utf-8")
    )
    parsed = parse_design(path)
    assert len(parsed["findings"]) == 1
    body = parsed["findings"][0]["body_md"]
    assert "the body" in body
    assert "Considered and rejected" not in body
    assert "not part of the body" not in body


def test_v2_optional_anchor_keys_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "design.md"
    path.write_bytes(
        "\n".join([
            "## A finding",
            "",
            "```yaml",
            "status: accepted",
            "slug: a-finding",
            "severity: 4",
            "category: security",
            "family: security",
            "fingerprint: 0123456789abcdef",
            "tier: B",
            "priority: 3.5",
            "debt_type: security",
            "type_id: TD-03",
            "effort: S",
            "diff: NEW",
            "reason: accepted until the rewrite",
            "until: 2027-01-31",
            "```",
            "",
            "body",
            "",
        ]).encode("utf-8")
    )
    finding = parse_design(path)["findings"][0]
    assert finding["status"] == "accepted"
    for key, value in {
        "family": "security", "fingerprint": "0123456789abcdef", "tier": "B", "priority": "3.5",
        "debt_type": "security", "type_id": "TD-03", "effort": "S", "diff": "NEW",
        "reason": "accepted until the rewrite", "until": "2027-01-31",
    }.items():
        assert finding[key] == value, key


def test_a_v1_confidence_value_is_parsed_and_kept_for_the_writer_to_discard(tmp_path: Path) -> None:
    path = tmp_path / "design.md"
    path.write_bytes(
        "\n".join([
            "## V1 finding", "", "```yaml", "status: pending", "slug: v1-finding",
            "severity: 2", "category: god-modules", "confidence: high", "```", "", "body", "",
        ]).encode("utf-8")
    )
    assert parse_design(path)["findings"][0]["confidence"] == "high"
```

In `tests/test_validation.py`, delete the `validate_confidence` cases and add `import pytest` guards only if the file loses its last use of a name.

- [ ] **Step 2: Run the tests to verify they fail**

```
python -m pytest skills/tech-debt-scan/tests/test_design_parser.py -k "ends_at_an_h1 or optional_anchor" -q
```
Expected: `test_a_finding_section_ends_at_an_h1` fails with `assert 'Considered and rejected' not in body` (today the H1 is absorbed); `test_v2_optional_anchor_keys_round_trip` fails with `KeyError: 'family'`. The third test passes already (the key is in today's `OPTIONAL_KEYS`); say so in the report rather than claiming a red.

- [ ] **Step 3: Change the parser**

Add beside `_is_h2`:

```python
def _is_h1(line: str) -> bool:
    """True for a level-1 heading (``# ``), which never starts a finding (spec 4.11).

    A finding section therefore ends at the next H2 *or* the next H1, so the negative-space
    sections that follow the last finding are not absorbed into its body and copied into a PBI.
    """
    return line.startswith("# ")


def _ends_section(line: str) -> bool:
    return _is_h2(line) or _is_h1(line)
```

**Fence awareness (amended after the Task 2 review).** A finding's body carries fenced
code blocks, and an evidence quote's first line is often a comment (`# TODO: ...`), so a
bare line test would end the section inside a fence and silently truncate the body. The
inner scan therefore tracks fences: a line whose stripped text starts with ``` toggles
`in_fence`, and `_ends_section` is consulted only when `in_fence` is False. The same
guard covers the H2 boundary, which had the latent form of this bug already. Two tests
pin it: an evidence fence whose first line is `# TODO(#42): delete once finance moves`,
and a hand-edited ```python block containing `# this is a comment`.

Use the fence-aware scan for the inner `while` that collects a finding's section, leaving the outer `while` (which finds the next heading to start a finding) keyed on `_is_h2`. Extend `OPTIONAL_KEYS` to the eleven names above. Update the module docstring's structure list to name the H1 boundary.

- [ ] **Step 4: Delete the confidence validator**

Remove `VALID_CONFIDENCES` and `validate_confidence` from `validation.py`; remove the import and call from `build_synthesis_prompt.py`; drop the confidence cases from `test_validation.py` and `test_build_synthesis_prompt.py`.

- [ ] **Step 5: Rename the v1 golden**

```bash
git mv skills/tech-debt-scan/tests/golden/design.md skills/tech-debt-scan/tests/golden/design-v1.md
```

Update every reference (`grep -rn "golden/design.md\|GOLDEN / \"design.md\"" skills/tech-debt-scan/tests/`) to `design-v1.md`, and add a comment at each use site saying this is the v1 compatibility document (spec 8), not the v2 golden Task 7 adds.

- [ ] **Step 6: Run the tests to verify they pass**

```
python -m pytest skills/tech-debt-scan/tests -q
```

- [ ] **Step 7: Gate and commit**

Run the gate. Commit:

```
feat(tech-debt-scan): design_parser ends a finding at an H1 and carries the v2 anchor keys
```

---
### Task 3: `slugs.py`, and `design_writer render` frontmatter, header and top N

**Files:**
- Create: `skills/tech-debt-scan/scripts/slugs.py`
- Modify: `skills/tech-debt-scan/scripts/design_writer.py` (replace `render_design_md` and the `render` subparser; keep `mark_promoted` and `_status_line_index` untouched)
- Test: `skills/tech-debt-scan/tests/test_slugs.py` (new), `skills/tech-debt-scan/tests/test_design_writer.py` (rewritten in this task and extended in Tasks 4 and 5)
- Modify: `docs/architecture.md` (the `design_writer.py` row), `README.md` (the `design.md` output row)

**Interfaces:**
- Consumes: `ranked.json`, `verified.json`, `candidates.json`, `scan-plan.json`, `inventory.json`, `coupling.json` from `--workdir`; `redaction.redact`; `design_parser.parse_design` for the self-check; `inventory.write_json`.
- Produces: `slugs.slugify(title: str) -> str` and `slugs.unique_slugs(titles: Sequence[str]) -> list[str]`; in `design_writer.py`: `RenderInputs` (a dataclass holding the six loaded documents plus `notes` and `diff`), `load_inputs(workdir: Path) -> RenderInputs`, `render_design(inputs: RenderInputs, scan_date: str) -> str`, `write_design(inputs, scan_date, out_path) -> None` (writes, then self-checks through `parse_design`), and `SECTION_ORDER` naming the seven body sections. Tasks 4 and 5 fill `render_design`'s later sections; this task lands frontmatter, header and the top-N block, and emits the later H1 headings with an empty body so the document shape and the parser boundary are exercised from the first commit.

**Confidence:** 93%. The one risk is layout drift between this task and the goldens of Task 7. Mitigation, embedded below: Step 0 is the exact expected output for a pinned small input, Step 1's test compares against it byte for byte, and Tasks 4, 5 and 7 extend the same document rather than inventing one.

- [ ] **Step 0: Read the worked example (the layout this phase renders)**

For the input documents of Step 1 (`_inputs()`), `render_design(inputs, "2026-09-06")` produces exactly these bytes. The empty `# Below the cut` through `# Not assessed` bodies are filled by Tasks 4 and 5; every other byte is final.

````markdown
---
schema_version: 2
scan_date: 2026-09-06
root: /abs/path/to/repo
total_files: 100
total_loc: 12000
languages:
- python
preset: balanced
families_run:
- error-masking
- security
families_skipped:
- family: duplication
  reason: no leads
tools_run: []
tools_absent: []
git_available: true
counts:
  candidates: 3
  quote_failed: 1
  verified: 2
  tier_a: 1
  tier_b: 1
  tier_c: 1
  unverified: 1
  rejected: 0
  suppressed: 0
---

# Tech-debt scan - 2026-09-06

Scanned `/abs/path/to/repo` - 100 files, 12000 LOC across: python.

Review each finding below. To act on one, change its `status:` from `pending` to
`approved`, `rejected`, or `accepted` (add a `reason:` and an optional `until:` ISO
date), then run `/tech-debt-promote`.

Top hotspots: `src/pay/refund.py` (80.0), `src/pay/gateway.py` (45.0).

Top coupled pairs: `src/pay/refund.py` <-> `src/pay/gateway.py` (shared 4, ratio 0.8).

# Top 1

## Refund failure swallowed by a bare except

```yaml
status: pending
slug: refund-failure-swallowed-by-a-bare-except
fingerprint: 0123456789abcdef
tier: A
priority: 6.3
family: error-masking
category: error-masking
debt_type: defect
type_id: TD-13
severity: 4
effort: M
diff: NEW
```

### Proof

The catch at lines 120 to 123 returns on any failure and logs nothing.

### Evidence

- `src/pay/refund.py:120-123`

```
    except Exception:
        pass
```

### Signals

- hotspot score 80.0, churn 4, coupling pairs 1, fan-in 2 (approximate)
- confirmed by: hotspot, pattern:swallowed-catch, scout:error-masking

### Remediation

remediation note not available

### Acceptance criteria

remediation note not available

# Below the cut

# Below the cut: tier C and unverified

# Considered and rejected

# Looks bad but is fine

# Open questions for the maintainer

# Not assessed
````

**Two spec amendments this layout makes, to be written into spec 4.11 in Step 5:**

1. Spec 4.11 body item 3 puts the tier C table inside `# Below the cut`, after the compact H2 sections. A table after the last H2 in that section is inside that finding's body under the parser's own rules, so it would be copied into that finding's PBI. The table therefore gets its own H1, `# Below the cut: tier C and unverified`, immediately after the compact sections. Reading order is unchanged; the parser boundary is explicit.
2. Spec 4.11 lists `### Remediation` and `### Acceptance criteria` as note-agent sections. They are rendered for every top-N finding whether or not a note exists, with the placeholder `remediation note not available` (spec 4.11's own wording) when it does not, so a finding's section shape does not depend on the agent having answered.

- [ ] **Step 1: Write the failing tests**

Create `skills/tech-debt-scan/tests/test_slugs.py`:

```python
"""slugs.py: deterministic, validator-clean slugs from finding titles."""
from __future__ import annotations

import pytest
from slugs import slugify, unique_slugs
from validation import ValidationError, validate_slug


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Refund failure swallowed by a bare except", "refund-failure-swallowed-by-a-bare-except"),
        ("  Mixed CASE and  spaces  ", "mixed-case-and-spaces"),
        ("punctuation: it's a (test) -- really!", "punctuation-it-s-a-test-really"),
        ("123 leading digits", "f-123-leading-digits"),
        ("", "finding"),
        ("---", "finding"),
        ("Ünïcode tïtle", "n-code-t-tle"),
    ],
)
def test_slugify_is_deterministic_and_valid(title: str, expected: str) -> None:
    assert slugify(title) == expected
    validate_slug(slugify(title))


def test_slugify_truncates_to_the_validator_limit() -> None:
    slug = slugify("word " * 40)
    assert len(slug) <= 64 and not slug.endswith("-")
    validate_slug(slug)


def test_unique_slugs_deduplicates_in_order() -> None:
    assert unique_slugs(["Same title", "Same title", "Other", "Same title"]) == [
        "same-title", "same-title-2", "other", "same-title-3",
    ]
    for slug in unique_slugs(["x" * 70, "x" * 70]):
        validate_slug(slug)


def test_unique_slugs_rejects_nothing_the_validator_would() -> None:
    titles = ["", "---", "9", "A" * 200, "réfund"]
    for slug in unique_slugs(titles):
        try:
            validate_slug(slug)
        except ValidationError as exc:  # pragma: no cover - the assert carries the message
            raise AssertionError(f"{slug!r}: {exc}") from exc
```

Rewrite `skills/tech-debt-scan/tests/test_design_writer.py` (this task's half; Tasks 4 and 5 append):

```python
"""design_writer.py v2: render design.md and findings.json from the ranked chain (spec 4.11)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from design_parser import parse_design
from design_writer import DesignWriteError, load_inputs, render_design, write_design
from inventory import write_json

SCAN_DATE = "2026-09-06"
GOLDEN = Path(__file__).parent / "golden"

TOP_FP = "0123456789abcdef"
CUT_FP = "fedcba9876543210"
TIER_C_FP = "aaaabbbbccccdddd"


def _inventory() -> dict[str, Any]:
    return {
        "schema_version": 2, "root": "/abs/path/to/repo", "total_files": 100,
        "total_loc": 12000, "languages": ["python"], "git_available": True,
        "hotspots": [
            {"path": "src/pay/refund.py", "churn": 4, "complexity": 20, "loc": 100, "score": 80.0},
            {"path": "src/pay/gateway.py", "churn": 2, "complexity": 9, "loc": 40, "score": 45.0},
        ],
        "hotspot_band": ["src/pay/refund.py"],
        "files": [
            {"path": "src/pay/refund.py", "path_class": "source", "hotspot_score": 80.0,
             "churn": 4, "coupling_degree": 1, "fan_in_approx": 2, "fan_in_mode": "import-lines"},
            {"path": "src/pay/gateway.py", "path_class": "source", "hotspot_score": 45.0,
             "churn": 2, "coupling_degree": 1, "fan_in_approx": 0, "fan_in_mode": "import-lines"},
        ],
    }


def _coupling() -> dict[str, Any]:
    return {"schema_version": 2, "pairs": [
        {"a": "src/pay/refund.py", "b": "src/pay/gateway.py", "shared_commits": 4,
         "ratio": 0.8, "cross_directory": False}
    ], "degree": {}, "cycles": [], "directories": [], "unstable_edges": []}


def _plan() -> dict[str, Any]:
    return {
        "schema_version": 2, "set": "default", "top": 5, "chunked": False, "thresholds": {},
        "entries": [], "families_run": ["error-masking", "security"],
        "families_skipped": [{"family": "duplication", "reason": "no leads"}],
    }


def _finding(
    fingerprint: str, family: str, title: str, file: str, start: int, end: int, quote: str,
    *, tier: str | None, verdict: str, severity: int = 4, effort: str = "M",
    debt_type: str = "defect", type_id: str | None = "TD-13", proof: str = "",
    confirmed: list[str] | None = None, signals: dict[str, Any] | None = None,
    trap: str | None = None, verified: bool = True,
) -> dict[str, Any]:
    return {
        "fingerprint": fingerprint, "quote_hash": "0" * 40, "family": family,
        "debt_type": debt_type, "type_id": type_id, "title": title, "severity": severity,
        "effort": effort, "source": "scout", "rule_id": None, "note": "n",
        "evidence": [{"file": file, "line_start": start, "line_end": end, "quote": quote,
                      "quote_verified": True}],
        "confirmed_by": confirmed if confirmed is not None else [f"scout:{family}"],
        "signals_cited": [],
        "signals": signals if signals is not None else {
            "hotspot_score": 80.0, "churn": 4, "coupling_degree": 1, "fan_in_approx": 2,
            "path_class": "source", "in_hotspot_band": True},
        "tier": tier, "verdict": verdict, "proof": proof, "checked": [], "opened": [],
        "trap_matched": trap, "verified": verified,
    }


def _verified() -> dict[str, Any]:
    return {"schema_version": 2, "findings": [
        _finding(TOP_FP, "error-masking", "Refund failure swallowed by a bare except",
                 "src/pay/refund.py", 120, 123, "    except Exception:\n        pass",
                 tier="A", verdict="confirm",
                 proof="The catch at lines 120 to 123 returns on any failure and logs nothing.",
                 confirmed=["hotspot", "pattern:swallowed-catch", "scout:error-masking"]),
        _finding(CUT_FP, "security", "Hard-coded credential in the gateway client",
                 "src/pay/gateway.py", 11, 11, 'token = "sk_l***"',
                 tier="B", verdict="confirm", severity=5, effort="S",
                 debt_type="security", type_id="TD-03",
                 proof="A credential-shaped literal sits in source, not in configuration.",
                 confirmed=["scout:security"],
                 signals={"hotspot_score": 45.0, "churn": 2, "coupling_degree": 1,
                          "fan_in_approx": 0, "path_class": "source", "in_hotspot_band": False}),
        _finding(TIER_C_FP, "dead-code", "Unused helper in the ledger module",
                 "src/pay/ledger.py", 40, 41, "def unused_helper():\n    return None",
                 tier="C", verdict="unverified", severity=2, effort="S",
                 debt_type="code", type_id="TD-09", verified=False,
                 signals={"hotspot_score": 0.0, "churn": 0, "coupling_degree": 0,
                          "fan_in_approx": 0, "path_class": "source", "in_hotspot_band": False}),
    ], "stats": {"selected": 2, "verdicts": 2, "unknown_fingerprint": 0, "missing_verdict": 1,
                 "tier_a": 1, "tier_b": 1, "tier_c": 1, "rejected": 0}}


def _ranked() -> dict[str, Any]:
    terms = {"severity": 4, "H": 0.8, "C": 0.4, "F": 0.2, "interest": 2.1,
             "tier_weight": 1.0, "tractability": 0.75, "priority": 6.3}
    return {
        "schema_version": 2, "formula_version": 1, "preset": "balanced", "top": 5,
        "weights": {"wH": 1.0, "wC": 0.5, "wF": 0.5},
        "tractability": {"S": 1.0, "M": 0.75, "L": 0.5},
        "top_n": [TOP_FP],
        "findings": [
            {"fingerprint": TOP_FP, "rank": 1, "priority": 6.3, "terms": terms, "tier": "A",
             "in_top_n": True, "spread_capped": False},
            {"fingerprint": CUT_FP, "rank": 2, "priority": 3.5, "terms": dict(terms, priority=3.5),
             "tier": "B", "in_top_n": False, "spread_capped": False},
            {"fingerprint": TIER_C_FP, "rank": 3, "priority": 0.7,
             "terms": dict(terms, priority=0.7), "tier": "C", "in_top_n": False,
             "spread_capped": False},
        ],
    }


def _candidates() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "candidates": [
            {"fingerprint": TOP_FP}, {"fingerprint": CUT_FP}, {"fingerprint": TIER_C_FP},
        ],
        "open_questions": [
            {"file": "src/pay/refund.py", "line_start": 51,
             "question": "Is audit_trail() wired into a production caller?", "reason": None},
            {"file": "src/pay/ledger.py", "line_start": 12,
             "question": "Ledger rounding drifts on partial refunds", "reason": "quote not found"},
        ],
        "looks_bad_but_fine": [
            {"file": "src/pay/gateway.py", "line_start": 19,
             "why": "One multi-line call, not nested branching."},
        ],
        "stats": {"error-masking": {"raw": 2, "dropped": 0, "quote_failed": 1, "clustered": 0,
                                    "suppressed": 0, "disabled": 0}},
    }


def _write_workdir(workdir: Path, **overrides: Any) -> Path:
    docs = {
        "inventory.json": _inventory(), "coupling.json": _coupling(), "scan-plan.json": _plan(),
        "verified.json": _verified(), "ranked.json": _ranked(), "candidates.json": _candidates(),
    }
    docs.update(overrides)
    for name, doc in docs.items():
        if doc is not None:
            write_json(workdir / name, doc)
    return workdir


def _inputs(tmp_path: Path, **overrides: Any) -> Any:
    return load_inputs(_write_workdir(tmp_path / "wd", **overrides))


# --- frontmatter, header, top N -------------------------------------------------


def test_render_matches_the_worked_example(tmp_path: Path) -> None:
    """The exact bytes of the plan's Step 0 example (Tasks 4 and 5 fill the empty sections)."""
    text = render_design(_inputs(tmp_path), SCAN_DATE)
    expected = (GOLDEN / "design-worked-example.md").read_bytes().decode("utf-8")
    assert text == expected


def test_document_parses_and_carries_one_top_finding(tmp_path: Path) -> None:
    out = tmp_path / "design.md"
    write_design(_inputs(tmp_path), SCAN_DATE, out)
    raw = out.read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    parsed = parse_design(out)
    assert parsed["metadata"]["schema_version"] == 2
    assert parsed["metadata"]["counts"]["tier_a"] == 1
    assert [f["slug"] for f in parsed["findings"]] == [
        "refund-failure-swallowed-by-a-bare-except"
    ]
    finding = parsed["findings"][0]
    assert finding["category"] == finding["family"] == "error-masking"
    assert finding["tier"] == "A" and finding["diff"] == "NEW" and finding["priority"] == "6.3"
    assert "Considered and rejected" not in finding["body_md"]


def test_git_absent_omits_the_hotspot_and_coupling_summary(tmp_path: Path) -> None:
    inventory = _inventory()
    inventory["git_available"] = False
    inventory["hotspots"] = []
    inventory["hotspot_band"] = []
    text = render_design(_inputs(tmp_path, **{"inventory.json": inventory,
                                              "coupling.json": {"schema_version": 2, "pairs": []}}),
                         SCAN_DATE)
    assert "Top hotspots:" not in text and "Top coupled pairs:" not in text
    assert "git_available: false" in text
    assert "No git history: churn is 0 and the interest signal is absent." in text


def test_counts_come_from_the_documents(tmp_path: Path) -> None:
    text = render_design(_inputs(tmp_path), SCAN_DATE)
    for line in ("  candidates: 3", "  quote_failed: 1", "  verified: 2", "  tier_a: 1",
                 "  tier_b: 1", "  tier_c: 1", "  unverified: 1", "  rejected: 0",
                 "  suppressed: 0"):
        assert line in text, line
    assert "  new:" not in text and "  resolved:" not in text, "no diff.json in phase 3"


def test_every_written_string_is_redacted(tmp_path: Path) -> None:
    secret = "sk_live_51H8f2kL9mN3pQ7rS4tU6vW"
    verified = _verified()
    verified["findings"][0]["proof"] = f'the literal token = "{secret}" sits here'
    verified["findings"][0]["evidence"][0]["quote"] = f'token = "{secret}"'
    text = render_design(_inputs(tmp_path, **{"verified.json": verified}), SCAN_DATE)
    assert secret not in text and "sk_l***" in text


def test_missing_input_document_is_an_error(tmp_path: Path) -> None:
    workdir = _write_workdir(tmp_path / "wd")
    (workdir / "ranked.json").unlink()
    with pytest.raises((DesignWriteError, FileNotFoundError)):
        load_inputs(workdir)
```

Write the worked example of Step 0 verbatim to `skills/tech-debt-scan/tests/golden/design-worked-example.md` (LF-only, ending with one newline).

- [ ] **Step 2: Run the tests to verify they fail**

```
python -m pytest skills/tech-debt-scan/tests/test_slugs.py skills/tech-debt-scan/tests/test_design_writer.py -q
```
Expected: `ModuleNotFoundError: No module named 'slugs'` and `ImportError: cannot import name 'load_inputs' from 'design_writer'`.

- [ ] **Step 3: Write `slugs.py`**

```python
"""Deterministic slugs for design findings.

A finding's slug is its identity in ``design.md``, in a PBI bundle id and in
``findings.json``. It is derived from the title so a reader can match the two,
and it always satisfies ``validation.validate_slug`` (start with a lowercase
letter, then at most 63 more of ``[a-z0-9-]``, never ending in a hyphen).

A leaf module: standard library only, no sibling imports.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

MAX_LENGTH: Final[int] = 64
FALLBACK: Final[str] = "finding"
_NON_SLUG: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    """A validator-clean slug for ``title``; ``finding`` when nothing survives."""
    lowered = title.strip().lower()
    slug = _NON_SLUG.sub("-", lowered).strip("-")
    if not slug:
        return FALLBACK
    if not slug[0].isalpha():
        slug = f"f-{slug}"
    slug = slug[:MAX_LENGTH].rstrip("-")
    return slug or FALLBACK


def unique_slugs(titles: Sequence[str]) -> list[str]:
    """One slug per title, in order, with ``-2``, ``-3`` suffixes on collisions."""
    seen: dict[str, int] = {}
    out: list[str] = []
    for title in titles:
        base = slugify(title)
        count = seen.get(base, 0) + 1
        seen[base] = count
        slug = base if count == 1 else f"{base[: MAX_LENGTH - len(str(count)) - 1].rstrip('-')}-{count}"
        out.append(slug)
    return out
```

Note on the non-ASCII case: `_NON_SLUG` strips any character outside `[a-z0-9]`, so `Ünïcode tïtle` becomes `n-code-t-tle` (each accented letter becomes a separator, not a transliteration; verified at plan-write time). That is the pinned behaviour; no `unicodedata` normalisation is added.

- [ ] **Step 4: Write the v2 `render` half of `design_writer.py`**

Replace `render_design_md`, `_render_frontmatter`, `_render_header`, `_render_evidence` and `_render_finding` with the v2 versions below; keep `mark_promoted`, `_status_line_index`, `DesignWriteError` and the `mark-promoted` subparser exactly as they are.

```python
SECTION_ORDER: Final[tuple[str, ...]] = (
    "Top", "Below the cut", "Below the cut: tier C and unverified",
    "Considered and rejected", "Looks bad but is fine",
    "Open questions for the maintainer", "Not assessed",
)
NOTE_PLACEHOLDER: Final[str] = "remediation note not available"


@dataclass(slots=True)
class RenderInputs:
    workdir: Path
    inventory: dict[str, Any]
    coupling: dict[str, Any]
    plan: dict[str, Any]
    verified: dict[str, Any]
    ranked: dict[str, Any]
    candidates: dict[str, Any]
    notes: list[dict[str, Any]]
    diff: dict[str, Any] | None


def load_inputs(workdir: Path) -> RenderInputs:
    """Load every render input; the six required documents must exist and be objects."""
    def required(name: str) -> dict[str, Any]:
        path = workdir / name
        if not path.is_file():
            raise DesignWriteError(f"{path} not found; run the chain first")
        loaded = json.loads(path.read_bytes())
        if not isinstance(loaded, dict):
            raise DesignWriteError(f"{path} is not a JSON object")
        return loaded

    notes_path = workdir / "notes.json"
    notes_raw = json.loads(notes_path.read_bytes()) if notes_path.is_file() else []
    diff_path = workdir / "diff.json"
    return RenderInputs(
        workdir=workdir,
        inventory=required("inventory.json"),
        coupling=required("coupling.json"),
        plan=required("scan-plan.json"),
        verified=required("verified.json"),
        ranked=required("ranked.json"),
        candidates=required("candidates.json"),
        notes=[n for n in notes_raw if isinstance(n, dict)] if isinstance(notes_raw, list) else [],
        diff=json.loads(diff_path.read_bytes()) if diff_path.is_file() else None,
    )
```

Counting, ordering and rendering:

- `_counts(inputs)` returns the frontmatter counts dict in the pinned order `candidates, quote_failed, verified, tier_a, tier_b, tier_c, unverified, rejected, suppressed`, then `new` and `resolved` only when `inputs.diff` is not None. `candidates` is `len(inputs.candidates["candidates"])`; `quote_failed` and `suppressed` are summed over `inputs.candidates["stats"]`; `verified` counts findings with `verified` true; `tier_a`, `tier_b`, `tier_c` count findings by `tier`; `unverified` counts `verdict == "unverified"`; `rejected` counts `verdict == "reject"`.
- `_ordered(inputs)` returns `[(rank_entry, finding)]` in `ranked["findings"]` order, joining on `fingerprint`; a ranked fingerprint with no verified finding is skipped and counted for the report; a verified finding with no rank entry is appended after the ranked ones with `priority` `null` (it cannot be in the top N).
- Slugs come from `unique_slugs([f["title"] for _, f in _ordered(inputs)])` so a finding's slug does not change when another finding is added below it.
- `_diff_for(fingerprint)` is `"NEW"` when `inputs.diff` is None, else `inputs.diff["status"][fingerprint]["diff"]` with `"NEW"` as the fallback.
- Every rendered string passes through `redact` at the point of writing: title, proof, quote, note, question, why, remediation, acceptance criterion.

Frontmatter, in the spec's order, written as literal YAML lines (never `yaml.dump`, so the byte layout is pinned):

```python
def _frontmatter(inputs: RenderInputs, scan_date: str) -> list[str]:
    inv, plan = inputs.inventory, inputs.plan
    lines = [
        "---",
        "schema_version: 2",
        f"scan_date: {scan_date}",
        f"root: {inv['root']}",
        f"total_files: {inv['total_files']}",
        f"total_loc: {inv['total_loc']}",
        "languages:",
        *[f"- {lang}" for lang in inv.get("languages", [])],
        f"preset: {inputs.ranked.get('preset', 'balanced')}",
        "families_run:",
        *[f"- {name}" for name in plan.get("families_run", [])],
        "families_skipped:",
    ]
    for item in plan.get("families_skipped", []):
        lines += [f"- family: {item['family']}", f"  reason: {item['reason']}"]
    lines += [
        "tools_run: []",      # the tool probe lands in phase 4; both lists stay empty here
        "tools_absent: []",
        f"git_available: {str(bool(inv.get('git_available'))).lower()}",
        "counts:",
        *[f"  {key}: {value}" for key, value in _counts(inputs).items()],
        "---",
    ]
    return lines
```

An empty `languages`, `families_run` or `families_skipped` list renders the key with no items beneath it, which `yaml.safe_load` reads as `None`; the frontmatter test asserts `parse_design` accepts that. When a list is empty, emit `key: []` on one line instead, and say so in the docstring.

Header (`_header`): a blank line, `# Tech-debt scan - <date>`, the scanned line, the three-line review instruction of the worked example, then, only when `git_available` is true, `Top hotspots:` (up to five, `` `path` (score) ``, comma-separated) and `Top coupled pairs:` (up to five, `` `a` <-> `b` (shared N, ratio R) ``). When it is false, one line instead: `No git history: churn is 0 and the interest signal is absent.`

Top-N block (`_top_section`): `# Top <count>` where count is the number of findings whose fingerprint is in `ranked["top_n"]`, then one `_finding_section(...)` each in ranked order. `_finding_section` emits the H2 title, the anchor in the pinned key order of the worked example, then `### Proof` (the verifier's proof, or `no verifier proof` when empty), `### Evidence` (one `- \`file:start-end\`` line then the quote in an unlabelled fenced block, per evidence item), `### Signals` (the two bullet lines of the example; `fan-in <n> (approximate)` renders `fan-in not computed (approximate)` when `fan_in_approx` is null), and, for a top-N finding only, `### Remediation` and `### Acceptance criteria` (Task 5 fills these from `notes.json`; this task renders the placeholder).

`render_design` assembles frontmatter, header, the top-N block, then the six remaining H1 headings with an empty body, joined with `"\n"` plus a trailing newline. `write_design` writes the bytes and re-parses through `parse_design`, raising `DesignWriteError` on failure.

CLI: replace the `render` subparser's `--top5` and `--inventory` with `--workdir` (default `.tech-debt`), `--scan-date` (required) and `--out` (default `<workdir>/design.md`); keep every `choices=` off the top-level parser. `_main`'s `render` branch calls `load_inputs`, `write_design`, prints the path, and catches `(DesignWriteError, DesignParseError, OSError, ValueError, KeyError)` returning 2.

- [ ] **Step 5: Run the tests, then amend the spec**

```
python -m pytest skills/tech-debt-scan/tests/test_slugs.py skills/tech-debt-scan/tests/test_design_writer.py -q
```

Then write the two amendments of Step 0 into spec 4.11: the tier C table's own H1 in body item 3, and the always-rendered note sections with their placeholder.

- [ ] **Step 6: Docs, gate, commit**

`docs/architecture.md`: the `design_writer.py` row becomes `design_writer.py render --workdir .tech-debt --scan-date <date> [--out <path>]` with its inputs (`ranked.json`, `verified.json`, `candidates.json`, `scan-plan.json`, `inventory.json`, `coupling.json`, optional `notes.json`, optional `diff.json`) and outputs (`design.md`, `findings.json`). `README.md`'s `design.md` row states the v2 frontmatter and the seven body sections. The suite will still fail in `test_e2e.py` until Task 8 rewrites it; if it does, mark those tests `pytest.mark.skip(reason="v1 synthesis path; rewritten in Task 8 of the phase 3 plan")` in this commit and delete the skip there. Run the gate. Commit:

```
feat(tech-debt-scan): design_writer renders the v2 frontmatter, header and top-N sections
```

---
### Task 4: below the cut, the four negative-space sections, and `findings.json`

**Files:**
- Modify: `skills/tech-debt-scan/scripts/design_writer.py` (fill the six H1 sections; add `render_findings_json`; `write_design` writes both files)
- Modify: `skills/tech-debt-scan/tests/test_design_writer.py` (append), `skills/tech-debt-scan/tests/golden/design-worked-example.md` (fill the sections)
- Modify: `README.md` (the `findings.json` output row)

**Interfaces:**
- Consumes: Task 3's `RenderInputs`, `_ordered`, `_counts`, `_finding_section`, `SECTION_ORDER`, `NOTE_PLACEHOLDER`, `slugs.unique_slugs`.
- Produces: `render_findings_json(inputs: RenderInputs) -> dict[str, Any]` returning `{"schema_version": 2, "findings": [...]}`; `write_design(inputs, scan_date, out_path)` also writes `findings.json` beside `design.md` in the workdir.

**Confidence:** 93%. The layout risk is retired by Step 0's exact expected bytes (an extension of Task 3's worked example); the remaining risk is the tier C table's reason wording, which Step 0 pins.

- [ ] **Step 0: The sections this task fills**

Against Task 3's `_inputs()`, the six empty H1 bodies become exactly this (the `# Below the cut` heading line and everything after it replaces Task 3's empty headings; the frontmatter, header and top-N block are unchanged):

````markdown
# Below the cut

## Hard-coded credential in the gateway client

```yaml
status: pending
slug: hard-coded-credential-in-the-gateway-client
fingerprint: fedcba9876543210
tier: B
priority: 3.5
family: security
category: security
debt_type: security
type_id: TD-03
severity: 5
effort: S
diff: NEW
```

### Proof

A credential-shaped literal sits in source, not in configuration.

### Evidence

- `src/pay/gateway.py:11-11`

```
token = "sk_l***"
```

# Below the cut: tier C and unverified

| slug | family | file | reason |
| --- | --- | --- | --- |
| unused-helper-in-the-ledger-module | dead-code | src/pay/ledger.py | unverified |

# Considered and rejected

_None._

# Looks bad but is fine

- `src/pay/gateway.py:19` - One multi-line call, not nested branching.

# Open questions for the maintainer

- `src/pay/refund.py:51` - Is audit_trail() wired into a production caller?
- `src/pay/ledger.py:12` - quote not found: Ledger rounding drifts on partial refunds

# Not assessed

- Families not run: duplication (no leads)
- Tools: the tool probe lands in phase 4, so currency, end-of-life and vulnerability claims are not assessed
- Runtime-only: coverage numbers, flake confirmation, model staleness, rollout state, deploy frequency
- By design: magic literals, convention violations, and class-level metrics that need a parser
````

Rules the example pins:

- **Below the cut** carries a compact H2 per tier A or B finding that is not in the top N: the same anchor as a top-N finding, then `### Proof` and `### Evidence` only. No Signals, no note sections; the finding is still promotable because the anchor is complete.
- **The tier C table** lists every finding whose tier is `C` or whose verdict is `unverified`, one row per finding, columns `slug | family | file | reason`. `file` is the primary evidence file. `reason` is the verdict: `unverified`, `downgrade`, or `refer`; a rejected finding never appears here (it is in "Considered and rejected"). An empty table renders `_None._` instead of a header row.
- **Considered and rejected** lists every finding whose verdict is `reject`, as `- **<title>** - \`<file>\` - <proof>`; when a `trap_matched` is present it replaces the proof and the entry also appears under "Looks bad but is fine".
- **Looks bad but is fine** merges `candidates.json`'s `looks_bad_but_fine` entries with the `trap_matched` rejections, each `- \`<file>:<line>\` - <why>`; a trap entry's `why` is its `trap_matched` text. Order: the candidates' entries first (document order), then the trap rejections (ranked order).
- **Open questions** lists `candidates.json`'s `open_questions`, each `- \`<file>:<line_start>\` - <question>`, with `quote not found: ` prefixed to the question when `reason` is `quote not found`.
- **Not assessed** always renders the four bullets of the example. The first names every skipped family with its reason (or `none` when the list is empty); the other three are fixed text.
- Every empty section renders `_None._` on its own line, so no section is a bare heading.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_design_writer.py`:

```python
# --- below the cut, negative space, findings.json --------------------------------


def test_render_matches_the_full_worked_example(tmp_path: Path) -> None:
    text = render_design(_inputs(tmp_path), SCAN_DATE)
    assert text == (GOLDEN / "design-worked-example.md").read_bytes().decode("utf-8")


def test_below_the_cut_findings_are_promotable_and_carry_no_note_sections(tmp_path: Path) -> None:
    out = tmp_path / "design.md"
    write_design(_inputs(tmp_path), SCAN_DATE, out)
    findings = {f["slug"]: f for f in parse_design(out)["findings"]}
    cut = findings["hard-coded-credential-in-the-gateway-client"]
    assert cut["tier"] == "B" and cut["status"] == "pending" and cut["category"] == "security"
    assert "### Proof" in cut["body_md"] and "### Evidence" in cut["body_md"]
    assert "### Signals" not in cut["body_md"]
    assert "### Remediation" not in cut["body_md"]
    assert "tier C and unverified" not in cut["body_md"], "the H1 boundary holds"
    assert "unused-helper-in-the-ledger-module" not in findings, "tier C is a table row, not a finding"


def test_tier_c_table_and_empty_sections(tmp_path: Path) -> None:
    text = render_design(_inputs(tmp_path), SCAN_DATE)
    assert "| slug | family | file | reason |" in text
    assert "| unused-helper-in-the-ledger-module | dead-code | src/pay/ledger.py | unverified |" in text
    assert text.count("_None._") == 1, "only 'Considered and rejected' is empty here"


def test_rejected_and_trap_findings_land_in_their_sections(tmp_path: Path) -> None:
    verified = _verified()
    verified["findings"].append(
        _finding("1111222233334444", "dead-code", "Entry point looks unreferenced",
                 "src/pay/cli.py", 3, 3, "def main():", tier=None, verdict="reject",
                 proof="It is the console entry point declared in pyproject.",
                 trap="Entry points have no in-repository caller and are alive."))
    ranked = _ranked()
    ranked["findings"].append({"fingerprint": "1111222233334444", "rank": 4, "priority": 0.0,
                               "terms": {}, "tier": None, "in_top_n": False,
                               "spread_capped": False})
    text = render_design(_inputs(tmp_path, **{"verified.json": verified, "ranked.json": ranked}),
                         SCAN_DATE)
    rejected = text.split("# Considered and rejected")[1].split("# Looks bad but is fine")[0]
    assert "**Entry point looks unreferenced**" in rejected
    assert "Entry points have no in-repository caller" in rejected
    fine = text.split("# Looks bad but is fine")[1].split("# Open questions")[0]
    assert "One multi-line call, not nested branching." in fine
    assert "Entry points have no in-repository caller" in fine, "a trap rejection appears in both"


def test_open_questions_flag_the_quote_failures(tmp_path: Path) -> None:
    text = render_design(_inputs(tmp_path), SCAN_DATE)
    section = text.split("# Open questions for the maintainer")[1].split("# Not assessed")[0]
    assert "- `src/pay/refund.py:51` - Is audit_trail() wired into a production caller?" in section
    assert "- `src/pay/ledger.py:12` - quote not found: Ledger rounding drifts" in section


def test_findings_json_is_the_machine_readable_twin(tmp_path: Path) -> None:
    workdir = _write_workdir(tmp_path / "wd")
    write_design(load_inputs(workdir), SCAN_DATE, workdir / "design.md")
    doc = json.loads((workdir / "findings.json").read_bytes())
    assert list(doc) == ["schema_version", "findings"]
    assert [f["fingerprint"] for f in doc["findings"]] == [TOP_FP, CUT_FP, TIER_C_FP]
    top = doc["findings"][0]
    assert list(top) == ["fingerprint", "slug", "title", "family", "debt_type", "type_id",
                         "severity", "effort", "evidence", "signals", "confirmed_by", "tier",
                         "verdict", "proof", "priority", "terms", "in_top_n", "spread_capped",
                         "diff"]
    assert top["slug"] == "refund-failure-swallowed-by-a-bare-except"
    assert top["in_top_n"] is True and top["diff"] == "NEW" and top["priority"] == 6.3
    assert doc["findings"][2]["in_top_n"] is False
    raw = (workdir / "findings.json").read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")


def test_findings_json_feeds_evaluate(tmp_path: Path) -> None:
    """evaluate.load_findings prefers findings.json; the writer must satisfy it."""
    from evaluate import load_findings

    workdir = _write_workdir(tmp_path / "wd")
    write_design(load_inputs(workdir), SCAN_DATE, workdir / "design.md")
    findings, name = load_findings(workdir)
    assert name == "findings.json" and len(findings) == 3
    assert {f["tier"] for f in findings} == {"A", "B", "C"}
```

- [ ] **Step 2: Run the tests to verify they fail**

```
python -m pytest skills/tech-debt-scan/tests/test_design_writer.py -q
```
Expected: `test_render_matches_the_full_worked_example` fails on the empty sections (the golden file is updated in Step 3 before the renderer, so run this after updating it and expect a diff); `test_findings_json_is_the_machine_readable_twin` fails with `FileNotFoundError` on `findings.json`.

- [ ] **Step 3: Extend the golden and write the sections**

Replace the six empty headings in `tests/golden/design-worked-example.md` with Step 0's block. Then implement in `design_writer.py`:

- `_below_the_cut(inputs, rows)`: the compact H2 sections for tier A and B findings outside the top N, then the H1 `# Below the cut: tier C and unverified` with the table (or `_None._`).
- `_considered_and_rejected(rows)`, `_looks_bad_but_fine(inputs, rows)`, `_open_questions(inputs)`, `_not_assessed(inputs)`: each returns its H1 and body per Step 0's rules, with `_None._` when empty.
- `_finding_section(..., compact: bool = False)`: `compact` drops the Signals and note sections.
- `render_findings_json(inputs)`: one entry per finding in `_ordered` order with the nineteen keys of the test, `priority` and `terms` from the rank entry (`null` and `{}` when absent), `in_top_n` from `ranked["top_n"]` membership, `diff` from `_diff_for`.
- `write_design` writes `design.md`, then `findings.json` through `write_json` into `out_path.parent`, then self-checks the markdown through `parse_design`.

- [ ] **Step 4: Run the tests to verify they pass**

```
python -m pytest skills/tech-debt-scan/tests/test_design_writer.py -q
```

- [ ] **Step 5: Docs, gate, commit**

`README.md` gains the `findings.json` output row with the nineteen keys. Run the gate. Commit:

```
feat(tech-debt-scan): design_writer renders the negative-space sections and findings.json
```

---

### Task 5: `notes-prompt` and the remediation notes

**Files:**
- Modify: `skills/tech-debt-scan/scripts/design_writer.py` (`notes-prompt` subcommand, `render_notes_prompt`, notes wired into `_finding_section`)
- Create: `skills/tech-debt-scan/tests/golden/notes-prompt.md`
- Modify: `skills/tech-debt-scan/tests/test_design_writer.py` (append), `docs/architecture.md`, `README.md`

**Interfaces:**
- Consumes: `RenderInputs`, `ranked["top_n"]`, `verified["findings"]`, `NOTE_PLACEHOLDER`, `redact`.
- Produces: `render_notes_prompt(inputs: RenderInputs) -> str`; `NOTES_CONTRACT: str`; `notes_by_fingerprint(inputs) -> dict[str, dict[str, Any]]` (top-N fingerprints only; entries for other fingerprints are ignored).
- CLI: `python scripts/design_writer.py notes-prompt --workdir .tech-debt --top <n>` writes `prompts/notes.md`; `--top` narrows the top N below `ranked["top"]` and never widens it.

**Confidence:** 94% (a pure string renderer over documents already loaded, plus a lookup in `_finding_section`; the contract text is pinned by the golden).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_design_writer.py`:

```python
# --- notes ----------------------------------------------------------------------


def test_notes_prompt_matches_its_golden(tmp_path: Path) -> None:
    from design_writer import render_notes_prompt

    text = render_notes_prompt(_inputs(tmp_path))
    assert text == (GOLDEN / "notes-prompt.md").read_bytes().decode("utf-8")
    assert TOP_FP in text and CUT_FP not in text, "the note agent sees the top N only"
    assert "120 words" in text and '"acceptance_criteria"' in text


def test_notes_prompt_cli_writes_the_file(tmp_path: Path) -> None:
    from design_writer import _main

    workdir = _write_workdir(tmp_path / "wd")
    assert _main(["notes-prompt", "--workdir", str(workdir), "--top", "5"]) == 0
    raw = (workdir / "prompts" / "notes.md").read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    assert _main(["notes-prompt", "--workdir", str(tmp_path / "none")]) == 2


def test_a_note_fills_the_remediation_sections(tmp_path: Path) -> None:
    notes = [{"fingerprint": TOP_FP, "remediation": "Re-raise after logging the cause.",
              "acceptance_criteria": ["The failure path re-raises", "A regression test covers it"]}]
    workdir = _write_workdir(tmp_path / "wd")
    write_json(workdir / "notes.json", notes)
    text = render_design(load_inputs(workdir), SCAN_DATE)
    assert "Re-raise after logging the cause." in text
    assert "- [ ] The failure path re-raises" in text
    assert "- [ ] A regression test covers it" in text
    assert NOTE_PLACEHOLDER not in text


def test_a_note_for_a_finding_outside_the_top_n_is_ignored(tmp_path: Path) -> None:
    notes = [{"fingerprint": CUT_FP, "remediation": "should not appear",
              "acceptance_criteria": ["nor this"]}]
    workdir = _write_workdir(tmp_path / "wd")
    write_json(workdir / "notes.json", notes)
    text = render_design(load_inputs(workdir), SCAN_DATE)
    assert "should not appear" not in text and "nor this" not in text
    assert text.count(NOTE_PLACEHOLDER) == 2, "the top-N finding keeps both placeholders"


def test_a_malformed_notes_document_does_not_stop_the_render(tmp_path: Path) -> None:
    workdir = _write_workdir(tmp_path / "wd")
    (workdir / "notes.json").write_bytes(b'{"not": "a list"}')
    text = render_design(load_inputs(workdir), SCAN_DATE)
    assert NOTE_PLACEHOLDER in text


def test_notes_are_redacted(tmp_path: Path) -> None:
    secret = "sk_live_51H8f2kL9mN3pQ7rS4tU6vW"
    workdir = _write_workdir(tmp_path / "wd")
    write_json(workdir / "notes.json", [{"fingerprint": TOP_FP,
                                         "remediation": f'move token = "{secret}" to config',
                                         "acceptance_criteria": [f'no token = "{secret}" in source']}])
    text = render_design(load_inputs(workdir), SCAN_DATE)
    assert secret not in text and "sk_l***" in text
```

Note on `NOTE_PLACEHOLDER` import: add it to the module's import line at the top of the test file.

- [ ] **Step 2: Run the tests to verify they fail**

```
python -m pytest skills/tech-debt-scan/tests/test_design_writer.py -k notes -q
```
Expected: `ImportError: cannot import name 'render_notes_prompt'`.

- [ ] **Step 3: Write the prompt renderer and the golden**

```python
NOTES_CONTRACT: Final[str] = """Reply with one JSON array, one object per finding, exactly these keys:

[
  {
    "fingerprint": "<as given>",
    "remediation": "<=120 words on how to pay this debt down, no code>",
    "acceptance_criteria": ["<one checkable statement>", "..."]
  }
]

Write for the engineer who will do the work: what to change and in what order, not why
the debt matters. Two to five acceptance criteria, each checkable by reading a diff or
running a test. Do not restate the finding, do not propose a schedule, do not include a
fix in code."""


def render_notes_prompt(inputs: RenderInputs) -> str:
    """One prompt for the single remediation-note agent, over the top N only (spec 4.11)."""
```

The prompt body, in order: a one-line role sentence naming the repository root; the read-only rule; then per top-N finding, in ranked order, `## <n>. <title>` with `fingerprint`, `family`, `severity`, `effort`, the proof, and each evidence item as `` `file:start-end` `` followed by its quote in a fenced block; then `NOTES_CONTRACT`. Every string redacted. Write the rendered output for Task 3's `_inputs()` to `tests/golden/notes-prompt.md`.

In `_finding_section`, take the note from `notes_by_fingerprint(inputs)`: `### Remediation` renders the note's `remediation` (or `NOTE_PLACEHOLDER`), `### Acceptance criteria` renders `- [ ] <criterion>` lines (or `NOTE_PLACEHOLDER`). `notes_by_fingerprint` keeps only entries whose `fingerprint` is in `ranked["top_n"]`, whose `remediation` is a non-empty string and whose `acceptance_criteria` is a list of strings; anything else is dropped silently, so a malformed `notes.json` renders placeholders rather than failing.

CLI: add the `notes-prompt` subparser with `--workdir` (default `.tech-debt`) and `--top` (int, optional); it writes `<workdir>/prompts/notes.md` and prints the path. Keep every `choices=` off the top-level parser.

- [ ] **Step 4: Run the tests to verify they pass**

```
python -m pytest skills/tech-debt-scan/tests/test_design_writer.py -q
```

- [ ] **Step 5: Docs, gate, commit**

`docs/architecture.md` gains the `design_writer.py notes-prompt` row; `README.md`'s output table gains `prompts/notes.md` and `notes.json`. Run the gate. Commit:

```
feat(tech-debt-scan): design_writer notes-prompt and the remediation sections
```

---

### Task 6: `bundle_writer.py` and `promote.py` v2

**Files:**
- Modify: `skills/tech-debt-scan/scripts/bundle_writer.py` (frontmatter keys, `PLAN.md` acceptance criteria)
- Modify: `skills/tech-debt-scan/scripts/promote.py` (docstring, reserved exit code 6)
- Modify: `skills/tech-debt-scan/tests/test_bundle_writer.py`, `test_promote.py`
- Add: `skills/tech-debt-scan/tests/golden/bundle-v2/chore-<slug>-<date>/` (`PBI.md`, `PLAN.md`, `HISTORY.md`)

**Interfaces:**
- Consumes: a parsed finding from `design_parser.parse_design` (the anchor keys plus `body_md`).
- Produces: `write_bundle` unchanged in signature; `PBI_OPTIONAL_KEYS: tuple[str, ...] = ("fingerprint", "tier", "type_id", "family", "debt_type", "effort")`; `acceptance_criteria(body_md: str) -> list[str]`; `promote.EXIT_WRITE_BACK: int = 6` (reserved; phase 5 returns it).

**Confidence:** 94% (additive frontmatter keys behind a presence check, one small parser over the body's own `### Acceptance criteria` block, and a docstring change; the v1 golden pins that nothing moves for a v1 design).

- [ ] **Step 1: Write the failing tests**

In `tests/test_bundle_writer.py`, keep every existing test (they pin the v1 shape) and add:

```python
def test_v2_finding_carries_the_new_frontmatter_keys(tmp_path: Path) -> None:
    finding = {
        "title": "Refund failure swallowed by a bare except",
        "status": "approved", "slug": "refund-failure-swallowed", "severity": 4,
        "category": "error-masking", "family": "error-masking", "fingerprint": "0123456789abcdef",
        "tier": "A", "type_id": "TD-13", "debt_type": "defect", "effort": "M", "priority": "6.3",
        "body_md": "\n".join([
            "### Proof", "", "p", "", "### Evidence", "", "- `src/pay/refund.py:120-123`", "",
            "```", "    except Exception:", "        pass", "```", "", "### Remediation", "",
            "Re-raise after logging.", "", "### Acceptance criteria", "",
            "- [ ] The failure path re-raises", "- [ ] A regression test covers it",
        ]),
    }
    bundle = write_bundle(finding, out_root=tmp_path, source_design="d.md", date="2026-09-06")
    pbi = (bundle / "PBI.md").read_text(encoding="utf-8")
    for line in ("category: error-masking", "fingerprint: 0123456789abcdef", "tier: A",
                 "type_id: TD-13", "family: error-masking", "debt_type: defect", "effort: M"):
        assert line in pbi, line
    assert "priority:" not in pbi, "priority is not a PBI key"
    assert pbi.index("category:") < pbi.index("fingerprint:"), "v1 keys keep their order first"
    assert "### Acceptance criteria" in pbi and "    except Exception:" in pbi
    plan = (bundle / "PLAN.md").read_text(encoding="utf-8")
    assert "- [ ] 1. The failure path re-raises" in plan
    assert "- [ ] 2. A regression test covers it" in plan
    assert "Address the tech-debt finding" not in plan, "criteria replace the one-step stub"


def test_a_finding_without_acceptance_criteria_keeps_the_one_step_plan(tmp_path: Path) -> None:
    finding = {"title": "T", "status": "approved", "slug": "t", "severity": 3,
               "category": "security", "body_md": "### Proof\n\np"}
    bundle = write_bundle(finding, out_root=tmp_path, source_design="d.md", date="2026-09-06")
    plan = (bundle / "PLAN.md").read_text(encoding="utf-8")
    assert "- [ ] 1. Address the tech-debt finding described in PBI.md." in plan


def test_v1_finding_still_writes_the_v1_golden_bytes(tmp_path: Path) -> None:
    """Spec 8: a v1 design promotes byte-identically."""
    finding = {"title": "Finding 0 title", "status": "approved", "slug": "finding-0",
               "severity": 5, "category": "god-modules",
               "body_md": "### Evidence\n\n- foo\n\n### Suggested fix\n\nbar"}
    bundle = write_bundle(finding, out_root=tmp_path, source_design="d.md", date="2026-05-31")
    for name in ("PBI.md", "PLAN.md", "HISTORY.md"):
        expected = (GOLDEN / "bundle" / "chore-finding-0-2026-05-31" / name).read_bytes()
        assert (bundle / name).read_bytes() == expected, name


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("### Acceptance criteria\n\n- [ ] one\n- [ ] two", ["one", "two"]),
        ("### Acceptance criteria\n\n- [ ] one\n\n# Next section\n\n- [ ] not mine", ["one"]),
        ("### Acceptance criteria\n\nremediation note not available", []),
        ("### Proof\n\np", []),
        ("", []),
    ],
)
def test_acceptance_criteria_parser(body: str, expected: list[str]) -> None:
    from bundle_writer import acceptance_criteria

    assert acceptance_criteria(body) == expected
```

In `tests/test_promote.py`, add:

```python
def test_accepted_is_counted_and_never_pending(tmp_path: Path) -> None:
    design = tmp_path / "design.md"
    design.write_bytes("\n".join([
        "## Accepted finding", "", "```yaml", "status: accepted", "slug: accepted-finding",
        "severity: 3", "category: security", "reason: waiting for the rewrite",
        "until: 2027-01-31", "```", "", "body", "",
        "## Pending finding", "", "```yaml", "status: pending", "slug: pending-finding",
        "severity: 2", "category: security", "```", "", "body", "",
    ]).encode("utf-8"))
    result = run_promote(design, out_root=tmp_path / "out", date="2026-09-06")
    assert result.accepted_count == 1 and result.pending_count == 1
    assert result.emitted_count == 0 and result.exit_code == 0


def test_write_back_exit_code_is_reserved() -> None:
    from promote import EXIT_WRITE_BACK

    assert EXIT_WRITE_BACK == 6
```

- [ ] **Step 2: Run the tests to verify they fail**

```
python -m pytest skills/tech-debt-scan/tests/test_bundle_writer.py skills/tech-debt-scan/tests/test_promote.py -q
```
Expected: `assert 'fingerprint: 0123456789abcdef' in pbi` fails; `ImportError: cannot import name 'acceptance_criteria'`; `ImportError: cannot import name 'EXIT_WRITE_BACK'`. The `accepted` test passes already (promote counts it since phase 1); say so in the report.

- [ ] **Step 3: Implement**

`bundle_writer.py`: extend the optional-key loop from `("debt_type", "effort")` to `PBI_OPTIONAL_KEYS` in that order, appended after `category` so the v1 key order is untouched. Add:

```python
_CRITERIA_HEADING: Final[str] = "### Acceptance criteria"
_CRITERION_RE: Final[re.Pattern[str]] = re.compile(r"^\s*-\s*\[[ xX]\]\s*(?P<text>.+?)\s*$")


def acceptance_criteria(body_md: str) -> list[str]:
    """The checklist items under ``### Acceptance criteria``, in order.

    Stops at the next heading of any level, so a later section's checkboxes are
    never absorbed. Returns [] when the section is absent or holds the writer's
    placeholder rather than a list.
    """
```

`_render_plan` uses them: when `acceptance_criteria(body_md)` is non-empty, the plan's steps are `- [ ] <n>. <criterion>` in order; otherwise the existing one-step stub stands. The closing two prose lines stay in both forms.

`promote.py`: add `EXIT_WRITE_BACK: Final[int] = 6` with a comment that phase 5's baseline write-back returns it and nothing does yet; extend the module docstring's exit-code list to `0, 2, 4, 6` and name the v2 statuses.

- [ ] **Step 4: Run the tests, write the v2 bundle golden**

```
python -m pytest skills/tech-debt-scan/tests/test_bundle_writer.py skills/tech-debt-scan/tests/test_promote.py -q
```
Then write the bundle produced by `test_v2_finding_carries_the_new_frontmatter_keys` to `tests/golden/bundle-v2/chore-refund-failure-swallowed-2026-09-06/` and add a test comparing the three files byte for byte, so the PBI shape is pinned the way the v1 one is.

- [ ] **Step 5: Docs, gate, commit**

`docs/architecture.md`'s promote row and `README.md`'s bundle row name the new PBI keys and the acceptance-criteria plan. Run the gate. Commit:

```
feat(tech-debt-scan): PBI bundles carry the v2 anchor keys and the acceptance criteria
```

---
### Task 7: per-fixture `design.md` and `findings.json` goldens, and the e2e test

**Files:**
- Create: `skills/tech-debt-scan/tests/golden/<fixture>/notes.json` (hand-written, three files)
- Create: `skills/tech-debt-scan/tests/golden/<fixture>/design.md` and `.../findings.json` (regenerated)
- Modify: `skills/tech-debt-scan/tests/test_chain_goldens.py` (the chain now ends at the render)
- Rewrite: `skills/tech-debt-scan/tests/test_e2e.py`

**Interfaces:**
- Consumes: `test_chain_goldens._chain` (which already writes `candidates.json`, `verify-plan.json`, `verified.json`, `ranked.json` into a temporary workdir per fixture and compares each against its golden), `design_writer.load_inputs`, `write_design`, `promote.run_promote`, `design_writer.mark_promoted`.
- Produces: two more golden comparisons per fixture inside `_chain`; `test_e2e.py` covering scouts to promote for one fixture.

**Confidence:** 92%. Two risks, both mitigated in the steps: the renderer's layout (retired by Tasks 3 and 4's worked example, which these goldens extend rather than invent), and non-determinism from `date.today()` reaching a golden (Step 1 pins `scan_date` and the promote date as literals, and asserts a second run is byte-identical).

- [ ] **Step 1: Write the hand-written notes and the failing chain assertions**

For each fixture, write `tests/golden/<fixture>/notes.json` as a JSON array covering exactly that fixture's `ranked.json` `top_n` fingerprints (five each), each `{"fingerprint": ..., "remediation": "<=120 words>", "acceptance_criteria": [two or three items]}`. Read the fixture's top-N findings from its `verified.json` golden and write a note that names the real file and the real change; a note that could apply to any finding is a defect in this step. Leave exactly one fixture's last top-N fingerprint out of the file, so the placeholder path is exercised by a real golden, and say which in the report.

In `tests/test_chain_goldens.py`, extend `_chain` after the `ranked` comparison:

```python
    from design_writer import load_inputs, write_design

    shutil.copy(golden / "notes.json", workdir / "notes.json")
    write_design(load_inputs(workdir), SCAN_DATE, workdir / "design.md")
    _check_text("design.md", (workdir / "design.md").read_bytes().decode("utf-8"),
                golden / "design.md", root)
    _check("findings.json", json.loads((workdir / "findings.json").read_bytes()),
           golden / "findings.json", root)
```

with `SCAN_DATE = "2026-09-06"` beside the other pinned clocks and `_check_text` the text twin of `_check` (same `UPDATE_GOLDENS` behaviour, same root canonicalisation, LF-only bytes). Add to `test_chain_matches_goldens_and_meets_the_corpus_bar`:

```python
    design = (tmp_path / "wd" / "design.md")
    parsed = parse_design(design)
    assert parsed["metadata"]["schema_version"] == 2
    top_slugs = [f["slug"] for f in parsed["findings"] if f["tier"] in ("A", "B")]
    assert top_slugs and len(top_slugs) == len(set(top_slugs)), "slugs are unique"
    for finding in parsed["findings"]:
        assert finding["category"] == finding["family"]
        assert "# Not assessed" not in finding["body_md"], "the H1 boundary holds on real data"
    assert set(ranked["top_n"]) >= {f["fingerprint"] for f in parsed["findings"]
                                    if "### Signals" in f["body_md"]}
```

and a determinism assertion: render a second time into a fresh path and compare bytes.

Rewrite `tests/test_e2e.py`:

```python
"""End-to-end: canned scouts and verdicts through the whole v2 chain to a PBI bundle.

No mocking and no agent: the scout and verdict files are the corpus goldens (real
agent output from the phase 2 live runs), and every other stage is the real script
in the order SKILL.md v2 prescribes. Covers the scan side (signals to design.md),
a user edit, and the promote side (bundle, mark_promoted, idempotent re-run).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from apply_verdicts import apply
from config import DEFAULTS
from design_parser import parse_design
from design_writer import load_inputs, write_design
from inventory import build_all, write_json, write_outputs
from merge_findings import merge
from patterns import run_patterns
from plan_scan import build_plan, write_plan
from promote import run_promote
from rank import rank
from rules import run_rules
from verify_prompts import build_verify_plan

GOLDEN = Path(__file__).parent / "golden" / "service-py"
CORPUS = Path(__file__).parent / "fixtures" / "corpus" / "service-py"
SCAN_DATE = "2026-09-06"
PROMOTE_DATE = "2026-09-06"


def _scan(repo: Path, workdir: Path) -> None:
    planted = json.loads((CORPUS / "planted.json").read_bytes())
    inventory, coupling = build_all(repo, churn_months=int(planted["churn_months"]),
                                    config=DEFAULTS)
    write_outputs(inventory, coupling, workdir)
    patterns, inline = run_patterns(repo, inventory, DEFAULTS, blame=False)
    for entry in inventory["files"]:
        entry["inline_disables"] = inline.get(entry["path"], 0)
    write_json(workdir / "inventory.json", inventory)
    write_json(workdir / "patterns.json", patterns)
    findings, leads = run_rules(repo, inventory, DEFAULTS)
    write_json(workdir / "rule-findings.json",
               {"schema_version": 2, "findings": findings, "leads": leads})
    plan, prompts = build_plan(workdir, DEFAULTS, families="deep", top=5)
    write_plan(workdir, plan, prompts)
    for entry in plan["entries"]:
        shutil.copy(GOLDEN / entry["output"], workdir / entry["output"])
    write_json(workdir / "candidates.json", merge(workdir, repo, DEFAULTS))
    vplan, _ = build_verify_plan(workdir, repo, DEFAULTS, 5)
    write_json(workdir / "verify-plan.json", vplan)
    verdicts = {}
    for batch in vplan["batches"]:
        shutil.copy(GOLDEN / batch["output"], workdir / batch["output"])
        verdicts[batch["output"]] = json.loads((workdir / batch["output"]).read_bytes())
    candidates = json.loads((workdir / "candidates.json").read_bytes())["candidates"]
    verified = apply(candidates, vplan, verdicts)
    write_json(workdir / "verified.json", verified)
    write_json(workdir / "ranked.json",
               rank(verified, inventory, DEFAULTS, preset="balanced", top=5))
    shutil.copy(GOLDEN / "notes.json", workdir / "notes.json")
    write_design(load_inputs(workdir), SCAN_DATE, workdir / "design.md")


def test_scan_to_promote_over_the_corpus(service_py_repo: Path, tmp_path: Path) -> None:
    workdir = tmp_path / "wd"
    _scan(service_py_repo, workdir)
    design = workdir / "design.md"
    parsed = parse_design(design)
    assert parsed["metadata"]["schema_version"] == 2
    assert (workdir / "findings.json").is_file()

    # The user approves the first finding and accepts the second.
    text = design.read_bytes().decode("utf-8")
    first, second = parsed["findings"][0]["slug"], parsed["findings"][1]["slug"]
    lines = text.splitlines()
    for slug, status in ((first, "approved"), (second, "accepted")):
        anchor = next(i for i, line in enumerate(lines) if line.strip() == f"slug: {slug}")
        status_line = next(i for i in range(anchor, 0, -1) if lines[i].startswith("status:"))
        lines[status_line] = f"status: {status}"
    if second:
        anchor = next(i for i, line in enumerate(lines) if line.strip() == f"slug: {second}")
        lines.insert(anchor + 1, "reason: waiting for the payments rewrite")
    design.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))

    out = tmp_path / "pbis"
    result = run_promote(design, out_root=out, date=PROMOTE_DATE)
    assert result.exit_code == 0
    assert result.emitted_count == 1 and result.accepted_count == 1
    bundle = out / f"chore-{first}-{PROMOTE_DATE}"
    pbi = (bundle / "PBI.md").read_text(encoding="utf-8")
    assert "type: feature" in pbi and "status: inbox" in pbi and "target_repo:" in pbi
    assert "fingerprint: " in pbi and "tier: " in pbi
    assert (bundle / "PLAN.md").is_file() and (bundle / "HISTORY.md").is_file()

    # A second promote is a no-op: the finding is now `promoted`.
    again = run_promote(design, out_root=out, date=PROMOTE_DATE)
    assert again.emitted_count == 0 and again.already_promoted_count == 1
    assert again.accepted_count == 1 and again.exit_code == 0


def test_a_v1_design_still_promotes(tmp_path: Path) -> None:
    """Spec 8: the v1 document keeps working after the cut-over."""
    design = tmp_path / "design.md"
    shutil.copy(Path(__file__).parent / "golden" / "design-v1.md", design)
    text = design.read_bytes().decode("utf-8").replace("status: pending", "status: approved", 1)
    design.write_bytes(text.encode("utf-8"))
    result = run_promote(design, out_root=tmp_path / "out", date="2026-05-31")
    assert result.exit_code == 0 and result.emitted_count == 1
    bundle = tmp_path / "out" / "chore-finding-0-2026-05-31"
    for name in ("PBI.md", "PLAN.md", "HISTORY.md"):
        expected = (Path(__file__).parent / "golden" / "bundle"
                    / "chore-finding-0-2026-05-31" / name).read_bytes()
        assert (bundle / name).read_bytes() == expected, name
```

- [ ] **Step 2: Run to verify they fail**

```
python -m pytest skills/tech-debt-scan/tests/test_chain_goldens.py skills/tech-debt-scan/tests/test_e2e.py -q
```
Expected: `FileNotFoundError` on the missing `notes.json` goldens first (write those in Step 1 before running), then `missing golden .../design.md`.

- [ ] **Step 3: Generate and inspect the goldens**

```
UPDATE_GOLDENS=1 python -m pytest skills/tech-debt-scan/tests/test_chain_goldens.py -q
python -m pytest skills/tech-debt-scan/tests/test_chain_goldens.py skills/tech-debt-scan/tests/test_e2e.py -q
```
(PowerShell: `$env:UPDATE_GOLDENS="1"; python -m pytest ...; Remove-Item Env:UPDATE_GOLDENS`.)

Then **read each generated `design.md`** before accepting it and report, per fixture: the top-N count, whether any section is `_None._` that should not be, whether the tier C table has rows, and whether the "Not assessed" families list matches that fixture's `families_skipped`. A golden that renders an empty top N or an empty evidence block is a renderer defect, not a golden to accept.

- [ ] **Step 4: Gate and commit**

Run the gate. Commit:

```
test(tech-debt-scan): per-fixture design and findings goldens, and the v2 end-to-end test
```

---

### Task 8: SKILL.md v2, the deletions, and the docs rewrite

**Files:**
- Rewrite: `skills/tech-debt-scan/SKILL.md`
- Delete: `skills/tech-debt-scan/scripts/build_synthesis_prompt.py`, `skills/tech-debt-scan/tests/test_build_synthesis_prompt.py`
- Modify: `skills/tech-debt-scan/tests/test_skill_check.py` (keep `test_real_skill_md_passes`; update any fixture that names a deleted script)
- Rewrite: `docs/architecture.md` (the workflow narrative and the categories table), `README.md` (quickstart, output formats, status)

**Interfaces:**
- Consumes: every v2 script's `--help` (the `skill_check.py` lint runs them).
- Produces: the fourteen-step scan list without steps 4 and 11, and the four-step promote list, exactly as spec 5 gives them.

**Confidence:** 93% (the step list is transcribed from spec 5 and machine-checked by `skill_check.py`; the risk is a flag that the lint's substring match accepts but the script does not, which Step 3 closes by running each command's `--help` by hand).

- [ ] **Step 1: Write the failing test**

In `tests/test_skill_check.py`, add:

```python
def test_real_skill_md_names_every_v2_script_and_no_deleted_one() -> None:
    """The cut-over guard: SKILL.md drives the v2 chain and nothing that no longer exists."""
    skill = (Path(__file__).parent.parent / "SKILL.md").read_text(encoding="utf-8")
    for name in ("inventory.py", "patterns.py", "rules.py", "plan_scan.py", "merge_findings.py",
                 "verify_prompts.py", "apply_verdicts.py", "rank.py", "design_writer.py",
                 "design_parser.py", "promote.py"):
        assert f"scripts/{name}" in skill, name
    for gone in ("build_synthesis_prompt.py", "tools_probe.py", "baseline.py"):
        assert gone not in skill, f"{gone} is not part of phase 3"
    assert "--top5" not in skill and "raw-findings.json" not in skill
    assert "top5.json" not in skill and "synthesis" not in skill.lower()
    steps = [line for line in skill.splitlines() if line.strip().startswith(("1. ", "2. ", "3. "))]
    assert steps, "the numbered step lists survive the rewrite"
```

- [ ] **Step 2: Run it to verify it fails**

```
python -m pytest skills/tech-debt-scan/tests/test_skill_check.py -k real_skill_md -q
```
Expected: `assert 'scripts/plan_scan.py' in skill` fails against the v1 document.

- [ ] **Step 3: Rewrite SKILL.md**

Sections, in order: frontmatter (unchanged name and description beyond the v2 wording, `triggers` unchanged); a one-paragraph overview naming detect, verify, rank; **Methodology** (hotspots, the taxonomy, the detect-verify-rank pipeline, and that no LLM picks the final list); **No improvisation** (unchanged); **When to use**; **Flags** exactly as spec 5 gives them, minus `--no-tools` (phase 4 adds it with step 4); **Conventions** (unchanged, plus `--workdir`); the **scan steps** as spec 5 lists them with steps 4 and 11 omitted and the rest keeping their numbers; the **promote steps** with `promote.py .tech-debt/design.md --out ./tech-debt-pbis` and no `--baseline`; **Token budget** from spec 7's table; **Caveats** (no live LLM in CI, best-effort churn, exit codes `inventory.py` 2 and `promote.py` 0/2/4/6, single-user promote, the spec 8 compatibility statement).

Every command line is a `python scripts/<name>.py` invocation so the lint reaches it. After writing, run each command's `--help` by hand and confirm the flag spellings, then run `python skills/tech-debt-scan/scripts/skill_check.py` and expect `ok`.

- [ ] **Step 4: Delete the v1 synthesis path**

```bash
git rm skills/tech-debt-scan/scripts/build_synthesis_prompt.py skills/tech-debt-scan/tests/test_build_synthesis_prompt.py
```
Then `grep -rn "build_synthesis_prompt\|top5\|raw-findings" skills/ docs/ README.md` and clear every live reference (plan and spec documents are historical records and stay). Remove the Task 3 skip markers from `test_e2e.py` if any survived.

- [ ] **Step 5: Rewrite the docs**

`docs/architecture.md`: replace the v1 workflow narrative with the v2 chain (the fourteen steps in prose, the family table pointer, the tier table, the ranking formula), keep the script table Tasks 1 to 6 have been updating, and fix the "Scout categories" count (`categories.py` has fourteen families, and the eight v1 categories are retired). `README.md`: the quickstart becomes the v2 two-command flow with the agent steps named, the output-formats table lists every v2 artefact in chain order, and the status paragraph says phase 3 is complete and phases 4 and 5 add tools and the baseline.

- [ ] **Step 6: Run everything, gate and commit**

```
python -m pytest -q
python skills/tech-debt-scan/scripts/skill_check.py
```
Run the gate. Commit:

```
feat(tech-debt-scan): SKILL.md v2 cut-over and the v1 synthesis deletion
```

---

### Task 9: final gate, docs sweep, PR preparation

**Files:** `docs/architecture.md`, `README.md` only if the sweep finds drift.

**Confidence:** 96%.

- [ ] **Step 1: Docs sweep**

Read `docs/architecture.md` and `README.md` top to bottom against the code. Every script row exists for the eleven v2 scripts plus `evaluate.py` and `live_run.py`; every output row exists for `inventory.json`, `coupling.json`, `patterns.json`, `rule-findings.json`, `scan-plan.json`, `candidates.json`, `verify-plan.json`, `verified.json`, `ranked.json`, `design.md`, `findings.json`, `prompts/notes.md`, `notes.json`, `evaluation.json` and the bundle. Every flag named in a doc line exists in that script's argparse (`python scripts/<name>.py --help`). No live reference to `build_synthesis_prompt.py`, `top5.json`, `raw-findings.json` or `synthesis-prompt.txt` survives outside the plan and spec documents.

- [ ] **Step 2: The full gate**

From the repository root: `python -m ruff check .`, `python -m mypy`, `python skills/tech-debt-scan/scripts/skill_check.py`, `python -m pytest -q`. All green. Report the test count against the phase 2 baseline (419 passed, 4 skipped) and account for the difference: the deleted synthesis tests, the rewritten e2e, and the new writer, slug, parser, bundle and golden tests.

- [ ] **Step 3: Commit**

```
docs(tech-debt-scan): phase 3 documentation sweep
```

- [ ] **Step 4: PR**

The PR opens after the final whole-branch review through `superpowers:finishing-a-development-branch`, against `main`, titled `feat(tech-debt-scan): v2 phase 3 report and cut-over (design_writer, promote, SKILL.md v2)`. The body lists the renderer, the parser boundary, the PBI changes, the cut-over, the deletions, the per-fixture goldens, and whatever the reviews parked.

---

## Self-review

**Spec coverage (phase 3 scope, section 11).** `design_writer.py` v2 `render` (Tasks 3, 4) and `notes-prompt` (Task 5); `design_parser.py` keys and the H1 boundary (Task 2); `bundle_writer.py` and `promote.py` with the new statuses, PBI fields and exit code 6 reserved (Task 6); SKILL.md v2 without steps 4 and 11 (Task 8); deletion of `build_synthesis_prompt.py`, its test and `validate_confidence` (Tasks 2, 8); `tests/golden/design-v1.md` (Task 2); the rewrite of `docs/architecture.md`, `README.md` and SKILL.md (Tasks 8, 9). Gate items: the design round trip including the H1 boundary (Task 2's parser test and Task 3's `write_design` self-check), e2e over the corpus from scouts to promote (Task 7), `test_real_skill_md_passes` (Task 8), a v1 design still promoting (Tasks 6 and 7). Spec 4.11's test list: golden `design.md` and `findings.json` per fixture (Task 7), round trip including the H1 boundary (Task 2), `category` equals `family` in every anchor (Tasks 3 and 7), `accepted` round-trips `reason` and `until` (Task 2), missing note renders the placeholder (Task 5), absent `diff.json` (Task 3), git-absent header (Task 3), the negative-space sections outside every finding body (Task 4), `notes-prompt` golden (Task 5). Spec 4.12's test list: bundle golden with the new fields, a v1 design promoting byte-identically, `accepted` counted, the six ralph keys, roll-forward exit 4 (Task 6, with the existing tests kept). Spec 4.13: the confidence validator deleted, every other case kept (Task 2). Two spec amendments are made explicitly (Task 3, Step 5). Phase 2's four carry-forwards land in Task 1. Not in scope and not planned: the baseline write-back and `--baseline` (phase 5), `tools_probe.py` and step 4 (phase 4), the note agent in `live_run.py` (phase 5), the web-ts d1 fixture and per-decoy `sources` (phase 5).

**Placeholder scan.** No "TBD", "TODO", "similar to Task N" or "add appropriate handling" in any step. Every code step carries its code or an exact, enumerated description of the lines to write. The two places an implementer supplies content are named and bounded: the hand-written per-fixture `notes.json` of Task 7 Step 1 (with the rule that a note must name the real file and change), and the SKILL.md prose of Task 8 Step 3 (transcribed from spec 5, machine-checked by `skill_check.py`).

**Type consistency.** `slugify(title: str) -> str` and `unique_slugs(titles: Sequence[str]) -> list[str]` are defined in Task 3 and used in Tasks 3, 4 and 7. `RenderInputs`, `load_inputs(workdir)`, `render_design(inputs, scan_date)` and `write_design(inputs, scan_date, out_path)` are defined in Task 3 and used unchanged in Tasks 4, 5 and 7; `render_findings_json(inputs)` is added in Task 4 and called from `write_design`; `render_notes_prompt(inputs)` and `notes_by_fingerprint(inputs)` are added in Task 5 and called from `_finding_section`. `acceptance_criteria(body_md: str) -> list[str]` is defined in Task 6 and used by `_render_plan` there. `EXIT_WRITE_BACK` is defined in Task 6 and asserted in its own test. `KIND_CAPS`, `GRAPH_FAILED` and the `read_failed` stat key are defined in Task 1 and used only there. `parse_design`'s finding dict gains the eleven optional keys in Task 2 and is read by Tasks 6 and 7 with those names. `design-v1.md` is the v1 golden from Task 2 onward, and every reference is updated in that task.
