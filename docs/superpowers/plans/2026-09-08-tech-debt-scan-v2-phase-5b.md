# tech-debt-scan v2 phase 5b: the measurement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the corpus defects that contaminate every evaluation row, give the live harness the note agent, run the three repaired fixtures once, and replace the provisional 0.80 tier A bar with the minimum the run measures.

**Architecture:** Everything before the run is deterministic and pinned by a test: `evaluate.py` learns to read a decoy's `sources` list against a finding's producer tokens; the candidate and `findings.json` shapes gain the producer fields that makes possible; the three fixtures are repaired in `history.yaml`, `files/` and `planted.json`; two 4b carry-forwards change what the run measures; `live_run.py` gains the notes call, the render, a guard and a log column. The run is the last task and the bar is written from its rows.

**Tech Stack:** Python 3.11+, pytest, ruff, mypy; the corpus replays through `tests/helpers/make_history.py`; live calls go through `claude -p` in print mode.

**Spec:** `docs/superpowers/specs/2026-09-04-tech-debt-scan-v2-design.md` — sections 4.5, 4.7, 4.11, 6 (corpus, live policy) and 11 (phase 5b, setting the bar). The spec was amended for 5b in commits 2895745 and 51940cd on this branch.

## Global Constraints

- Redaction runs before any truncation at every capping site: `redact(text)[:n]`, never `[:n]` then `redact`.
- gitleaks' `Secret` and `Match`, jscpd's `fragment` and actionlint's `snippet` reach no document — not `tool-signals.json`, not a candidate, not a note.
- `rules.py` and osv fact-class signals are the ONLY producers of a non-`None` tier at merge time; nothing in this plan adds a producer, and a self-reported `tool:<name>` token never enters an untiered candidate's `confirmed_by`.
- Every date a test compares is a pinned literal that is not the wall-clock date.
- Goldens under `tests/golden/**` change only through `UPDATE_GOLDENS=1` after an intentional change, never by hand; the canned `scouts/`, `verdicts/` and `notes.json` are never regenerated.
- The corpus's replayed tree must equal its `files/` directory byte for byte (`test_replayed_tree_equals_files_dir`); every new fixture file lands in both `files/` and `history.yaml`.
- The live run is manual, never CI: `pytest -m live` and `live_run.py` are invoked by the controller only, and the whole suite runs with `-m "not live"` semantics through `python -m pytest -q` from the repository root (the seven live tests are deselected by configuration).
- Gate for every task, from the repository root: `python skills/tech-debt-scan/scripts/skill_check.py`, `python -m ruff check .`, `python -m mypy`, `python -m pytest -q`. Suite entering: 1230 passed / 1 skipped / 7 deselected.
- Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## Guardrails from memory

- **Keep documents in sync with every code change** (confidence 0.95, 7 evidence). Every task that changes a shape or a flag names the document line it updates in the same commit: `docs/architecture.md`'s script table rows, `README.md`, SKILL.md where a flag is documented. When a CLI flag is documented, read the argparse setup, never an existing example. [[keep-docs-in-sync]]
- **Verify the RED step is genuinely RED** (confidence 0.75). Where a new test would pass on the current code because a deeper layer already satisfies it, the task says so and calls the test a guard, not a red-to-green step. Tasks 1, 4, 6 and 7 mark each test accordingly. [[genuine-red]]
- **Path-resolving defaults need a CLI test from a foreign cwd** (5a whole-branch Critical). Task 7's `--keep` directory and the guard on the workdir are tested with `monkeypatch.chdir` away from the repository. [[foreign-cwd]]
- **Two call sites of one heuristic must see the same candidate set** (5a ruling 29). Task 1's `producers()` is the single place a finding's tokens are derived; `hits` and the decoy report both call it. [[one-derivation]]
- **A phase whose promise is a sequence needs one test that runs the sequence** (5a ruling 25). Task 7's harness test drives canned scout, verdict and notes replies through to `design.md` and asserts on the rendered document. [[sequence-test]]
- Dismissed: the ralph-queue reflection (no PBI is filed here); the Playwright and TypeScript reflections (no browser or TS code in this plan); the temp-file fd reflection (no `mkstemp` in this plan).

## Confidence

| Task | Confidence | Risk and mitigation inside the task |
|---|---|---|
| 1 evaluate producers and sources | 96% | pure function over dicts; the wildcard rule is stated exactly |
| 2 producer fields on candidates and findings.json | 94% | three dict literals plus one row; goldens regenerate; a key-order test may exist — Step 1 greps for it |
| 3 corpus: npm ci and decoy sources | 95% | data plus two corpus tests; the token vocabulary is closed and checked by the test |
| 4 zero-churn file | 93% | validated on 2026-09-08 by replaying the moved commit: churn 0, fan-in 0; goldens move deliberately |
| 5 mixed-decoys neutral files | 93% | validated 2026-09-08: neutral scores 0.3 and 1.7 against a planted mean of 2.78 |
| 6 4b carry-forwards | 92% | four small changes in three files; the gitleaks span change moves goldens where canned hits carry a column — Step 1 checks |
| 7 harness: notes, render, guard, column, keep | 92% | the largest task; the fake claude gains a third mode; every piece has a unit test and one sequence test |
| 8 the run | 92% | external: model variance and the decoy-at-tier-A outcome are both handled by the spec's two-outcome rule |
| 9 the bar | 95% | text edits from the rows; a grep pins every 0.80 mention |

---

### Task 1: `evaluate.py` reads a decoy's `sources` against a finding's producers

**Files:**
- Modify: `skills/tech-debt-scan/scripts/evaluate.py:73-93` (`hits`) and the module docstring
- Test: `skills/tech-debt-scan/tests/test_evaluate.py`

**Interfaces:**
- Consumes: finding dicts carrying `family`, `evidence`, and optionally `source`, `rule_id`, `tool`, `confirmed_by` (verified.json carries the first two today; Task 2 adds `tool` and copies all three into findings.json).
- Produces: `producers(finding: dict) -> frozenset[str]`; `source_matches(token: str, sources: list[str]) -> bool`; `hits(finding, item)` honouring `item["sources"]`.

The token vocabulary is closed: `scout:<family>`, `rule:<rule_id>`, `tool:<name>`. A `sources` entry is either an exact token or a prefix pattern ending in `*` (`rule:ci.*`, `rule:*`, `tool:*`), matched as a string prefix on everything before the `*`. A decoy with no `sources` key, or an empty list, matches any producer — the pre-5b behaviour — so the corpus test in Task 3 is what guarantees the fallback never runs on the corpus.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_evaluate.py`:

```python
from evaluate import producers, source_matches


def _producer_finding(family: str, file: str, **fields: Any) -> dict[str, Any]:
    finding = _finding(family, file, 1, 1, "A", "fp-" + family)
    finding.update(fields)
    return finding


def test_producers_names_the_findings_own_token_and_its_corroboration() -> None:
    scout = _producer_finding("dead-code", "a.py", source="scout",
                              confirmed_by=["scout:dead-code", "tool:vulture"])
    assert producers(scout) == frozenset({"scout:dead-code", "tool:vulture"})
    rule = _producer_finding("ownership", "a.py", source="rule", rule_id="ownership.island",
                             confirmed_by=["rule:ownership.island"])
    assert producers(rule) == frozenset({"rule:ownership.island"})
    tool = _producer_finding("security", "a.py", source="tool", tool="gitleaks",
                             confirmed_by=[])
    assert producers(tool) == frozenset({"tool:gitleaks"})
    # No source at all (a hand-written finding): only confirmed_by survives.
    bare = _producer_finding("security", "a.py", confirmed_by=["pattern:secret"])
    assert producers(bare) == frozenset({"pattern:secret"})


def test_source_matches_exact_and_prefix_patterns() -> None:
    assert source_matches("rule:ci.no-timeout", ["rule:ci.*"])
    assert source_matches("rule:ci.no-timeout", ["rule:*"])
    assert source_matches("tool:jscpd", ["scout:duplication", "tool:jscpd"])
    assert not source_matches("tool:jscpd", ["scout:duplication"])
    assert not source_matches("rule:ci.no-timeout", ["rule:container.*"])
    assert not source_matches("scout:security", ["scout:securit"])  # exact, not prefix


def test_hits_honours_a_decoys_sources_list() -> None:
    decoy = {"id": "d1", "family": "pipeline-infra", "path": ".github/workflows/ci.yml",
             "why": "well configured", "sources": ["scout:pipeline-infra", "rule:ci.*"]}
    scout = _producer_finding("pipeline-infra", ".github/workflows/ci.yml", source="scout",
                              confirmed_by=["scout:pipeline-infra"])
    rule = _producer_finding("pipeline-infra", ".github/workflows/ci.yml", source="rule",
                             rule_id="ci.no-timeout", confirmed_by=["rule:ci.no-timeout"])
    tool = _producer_finding("pipeline-infra", ".github/workflows/ci.yml", source="tool",
                             tool="actionlint", confirmed_by=[])
    assert hits(scout, decoy) and hits(rule, decoy)
    assert not hits(tool, decoy), "actionlint is not in the decoy's sources"
    # A family mismatch is still decided first.
    other = _producer_finding("dead-code", ".github/workflows/ci.yml", source="scout",
                              confirmed_by=["scout:dead-code"])
    assert not hits(other, decoy)


def test_a_decoy_without_sources_matches_any_producer() -> None:
    decoy = {"id": "d9", "family": "security", "path": "a.py", "why": "old shape"}
    tool = _producer_finding("security", "a.py", source="tool", tool="gitleaks", confirmed_by=[])
    assert hits(tool, decoy)
    assert hits(tool, {**decoy, "sources": []})


def test_evaluate_scores_a_decoy_only_through_its_sources(planted: dict[str, Any]) -> None:
    planted = json.loads(json.dumps(planted))
    d1 = next(d for d in planted["decoys"] if d["id"] == "d1")  # duplication, seed.py
    d1["sources"] = ["scout:duplication"]
    by_scout = _producer_finding("duplication", "tests/fixtures/seed.py", source="scout",
                                 confirmed_by=["scout:duplication"])
    by_tool = _producer_finding("duplication", "tests/fixtures/seed.py", source="tool",
                                tool="jscpd", confirmed_by=[])
    by_tool["fingerprint"] = "fp-tool"
    report = evaluate([by_scout, by_tool], planted, set(), top=5)
    decoy = next(d for d in report["decoys"] if d["id"] == "d1")
    assert decoy["hit_tiers"] == ["A"], "only the scout finding counts against d1"
    assert report["families"]["duplication"]["decoy_hits"] == {"A": 1, "B": 0, "C": 0}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_evaluate.py -q -k "producers or source_matches or sources"`
Expected: `ImportError: cannot import name 'producers'` at collection.

- [ ] **Step 3: Implement**

In `scripts/evaluate.py`, after `_ranges_overlap`:

```python
def producers(finding: dict[str, Any]) -> frozenset[str]:
    """The producer tokens a finding carries: its own, then every ``confirmed_by`` token.

    The own token is read from the candidate's ``source`` (spec 4.7): ``scout:<family>``
    for a scout candidate, ``rule:<rule_id>`` for a rule finding, ``tool:<tool>`` for a
    tool candidate. ``findings.json`` copies those fields (spec 4.11) so this reads the
    same off either input. A finding with no ``source`` contributes only its
    ``confirmed_by`` tokens.
    """
    tokens: set[str] = set()
    source = finding.get("source")
    if source == "scout" and finding.get("family"):
        tokens.add(f"scout:{finding['family']}")
    elif source == "rule" and finding.get("rule_id"):
        tokens.add(f"rule:{finding['rule_id']}")
    elif source == "tool" and finding.get("tool"):
        tokens.add(f"tool:{finding['tool']}")
    for token in finding.get("confirmed_by") or []:
        if isinstance(token, str) and token:
            tokens.add(token)
    return frozenset(tokens)


def source_matches(token: str, sources: list[str]) -> bool:
    """True when ``token`` equals an entry, or matches an entry ending in ``*`` as a prefix."""
    for entry in sources:
        if not isinstance(entry, str):
            continue
        if entry.endswith("*"):
            if token.startswith(entry[:-1]):
                return True
        elif token == entry:
            return True
    return False


def _sources_allow(finding: dict[str, Any], item: dict[str, Any]) -> bool:
    """A decoy with a non-empty ``sources`` list admits only findings one of its producers made."""
    sources = item.get("sources")
    if not isinstance(sources, list) or not sources:
        return True
    return any(source_matches(token, sources) for token in producers(finding))
```

Then, in `hits`, after the family check and before the path loop:

```python
    if not _sources_allow(finding, item):
        return False
```

Extend the module docstring's "A finding hits a planted item or decoy when ..." paragraph with one sentence: "A decoy carrying a non-empty `sources` list (spec 6) is hit only by a finding whose producer tokens — its own `scout:`, `rule:` or `tool:` token plus its `confirmed_by` — match an entry, exactly or by a trailing-`*` prefix."

- [ ] **Step 4: Run the tests**

Run: `python -m pytest skills/tech-debt-scan/tests/test_evaluate.py -q`
Expected: all pass, including the pre-existing ones (a planted item has no `sources`, so nothing changes for it).

- [ ] **Step 5: Mutation check**

Temporarily make `_sources_allow` return `True` unconditionally: `test_hits_honours_a_decoys_sources_list` and `test_evaluate_scores_a_decoy_only_through_its_sources` must fail. Temporarily drop the prefix branch of `source_matches`: `test_source_matches_exact_and_prefix_patterns` must fail. Restore.

- [ ] **Step 6: Documents and commit**

`docs/architecture.md`'s `evaluate.py` row (grep `evaluate.py --planted`): add "a decoy's `sources` list (exact tokens or a trailing-`*` prefix) restricts which producers can hit it; a family mismatch is still decided first". `README.md`: grep `decoy` and add the same sentence where the evaluation is described.

```bash
git add skills/tech-debt-scan/scripts/evaluate.py skills/tech-debt-scan/tests/test_evaluate.py docs/architecture.md README.md
git commit -m "$(cat <<'EOF'
feat(tech-debt-scan): evaluate reads a decoy's sources against a finding's producers

A decoy carrying a sources list is hit only by a finding whose own
producer token or confirmed_by token matches an entry, exactly or by a
trailing-star prefix, so a true finding from another producer landing on a
decoy's path is no longer scored as a false positive. A decoy without the
list behaves as before; the corpus test that lands with the lists is what
keeps that fallback off the corpus.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: the producer fields travel — `tool` on every candidate, `source`/`rule_id`/`tool` in `findings.json`

**Files:**
- Modify: `skills/tech-debt-scan/scripts/merge_findings.py:556-580` (`_fact_candidate` dict) and `:750-770` (the scout candidate dict, `"rule_id": None` at ~757)
- Modify: `skills/tech-debt-scan/scripts/rules.py:655-672` (the rule finding dict, `"rule_id": primary.rule_id` at ~660)
- Modify: `skills/tech-debt-scan/scripts/design_writer.py:1036-1062` (the `findings.json` row)
- Test: `skills/tech-debt-scan/tests/test_merge_findings.py`, `tests/test_rules.py`, `tests/test_design_writer.py`, goldens via `UPDATE_GOLDENS=1`

**Interfaces:**
- Produces: every candidate dict carries `"tool": <str | None>` immediately after `"rule_id"`; `findings.json` rows carry `source`, `rule_id`, `tool` copied from the verified finding.

- [ ] **Step 1: Find every place the candidate key set is pinned**

Run: `grep -rn '"rule_id"' skills/tech-debt-scan/scripts skills/tech-debt-scan/tests | grep -v golden`
Expected: the three dict literals above plus any test that asserts the exact key list or order (a `CANDIDATE_KEYS`-style constant or a `list(cand) ==` assertion). Every such site gains `tool` after `rule_id`. Record the list in the report.

- [ ] **Step 2: Write the failing tests**

`tests/test_merge_findings.py`, inside the tool-candidates test class (the one holding `test_a_gitleaks_fact_becomes_a_candidate_with_no_tier` at ~918), copying that test's setup:

```python
    def test_a_tool_candidate_names_the_tool_that_raised_it(self) -> None:
        signals, inventory = self._gitleaks_signals()  # reuse the class's existing helper name
        new, _ = tool_candidates(signals, inventory, [])
        assert new and all(c["tool"] == "gitleaks" for c in new)
        assert list(new[0]).index("tool") == list(new[0]).index("rule_id") + 1
```

(If the class has no such helper, build the signal exactly as `test_a_gitleaks_fact_becomes_a_candidate_with_no_tier` does.) A scout candidate: in the test that builds candidates from a scout reply (grep `"source": "scout"` in the test file), assert `cand["tool"] is None`. `tests/test_rules.py`: in any test that inspects a rule finding dict, assert `finding["tool"] is None` and `finding["source"] == "rule"`.

`tests/test_design_writer.py`, beside the existing `findings.json` test (grep `findings.json` there):

```python
def test_findings_json_carries_the_producer_fields(tmp_path: Path) -> None:
    inputs = _render_inputs(tmp_path)  # the file's existing helper; read it first
    write_design(inputs, "2026-04-15", tmp_path / "design.md")
    rows = json.loads((inputs.workdir / "findings.json").read_bytes())["findings"]
    verified = {f["fingerprint"]: f for f in inputs.verified["findings"]}
    for row in rows:
        source = verified[row["fingerprint"]]
        assert row["source"] == source.get("source")
        assert row["rule_id"] == source.get("rule_id")
        assert row["tool"] == source.get("tool")
```

- [ ] **Step 3: Run them to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_merge_findings.py skills/tech-debt-scan/tests/test_design_writer.py -q -k "tool_that_raised or producer_fields"`
Expected: `KeyError: 'tool'`.

- [ ] **Step 4: Implement**

`merge_findings._fact_candidate`: after `"rule_id": None,` add `"tool": tool,` (the local `tool = str(sig.get("tool"))` already exists). Scout candidate dict (~757): after `"rule_id": None,` add `"tool": None,`. `rules.py` (~660): after `"rule_id": primary.rule_id,` add `"tool": None,`. `design_writer` findings row: after `"confirmed_by": ...,` add

```python
                "source": finding.get("source"),
                "rule_id": finding.get("rule_id"),
                "tool": finding.get("tool"),
```

Update `_fact_candidate`'s docstring ("same keys, same order" as `rules.py`) to mention `tool`.

- [ ] **Step 5: Regenerate goldens and run the gate**

Run: `UPDATE_GOLDENS=1 python -m pytest skills/tech-debt-scan/tests/test_chain_goldens.py -q` (PowerShell: `$env:UPDATE_GOLDENS='1'; python -m pytest ...; Remove-Item Env:UPDATE_GOLDENS`), then `git diff --stat skills/tech-debt-scan/tests/golden` — expect `candidates.json`, `verified.json`, `findings.json` (and `design.md` only if a rendered value changed, which it should not) for every fixture. Then the full gate.

- [ ] **Step 6: Documents and commit**

`docs/architecture.md`: the `merge_findings.py` row's candidate shape and the `design_writer.py render` row's `findings.json` field list gain `tool` / `source`, `rule_id`, `tool`. `README.md`: grep `findings.json` and extend the field list if one is printed.

```bash
git add -A skills/tech-debt-scan docs/architecture.md README.md
git commit -m "$(cat <<'EOF'
feat(tech-debt-scan): candidates name their tool; findings.json carries the producer fields

A tool candidate records the tool that raised it in a tool field, since
its confirmed_by is empty by design and nothing else named the producer;
rule and scout candidates carry tool: null. findings.json copies source,
rule_id and tool from the verified finding so evaluate.py reads the same
producer off either input. Goldens regenerated for the new keys.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: corpus repairs — `npm ci` in web-ts, a `sources` list on all 27 decoys

**Files:**
- Modify: `skills/tech-debt-scan/tests/fixtures/corpus/web-ts/files/.github/workflows/ci.yml`
- Modify: the three `planted.json` files under `skills/tech-debt-scan/tests/fixtures/corpus/<fixture>/`
- Test: `skills/tech-debt-scan/tests/test_corpus.py`

**Interfaces:**
- Consumes: Task 1's token vocabulary and wildcard rule.
- Produces: every decoy carries `sources`; `web-ts`'s workflow installs before it tests.

- [ ] **Step 1: Write the failing corpus tests**

Append to `tests/test_corpus.py`:

```python
import re

SOURCE_TOKEN = re.compile(r"^(scout:[a-z-]+|rule:([a-z]+\.[a-z0-9-]+|[a-z]+\.\*|\*)|tool:([a-z-]+|\*))$")


def test_every_decoy_names_its_sources(corpus: tuple[str, Path]) -> None:
    """Spec 6: a decoy without a sources list would match any producer, which the corpus never allows."""
    name, _ = corpus
    planted = json.loads((CORPUS_ROOT / name / "planted.json").read_text(encoding="utf-8"))
    for decoy in planted["decoys"]:
        sources = decoy.get("sources")
        assert isinstance(sources, list) and sources, f"{name} {decoy['id']} has no sources"
        for token in sources:
            assert SOURCE_TOKEN.match(token), f"{name} {decoy['id']}: {token!r}"


def test_web_ts_workflow_installs_before_it_tests(web_ts_repo: Path) -> None:
    """Spec 6: decoy d1 is a decoy only once the workflow really is well configured."""
    text = (web_ts_repo / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "run: npm ci" in text
    assert text.index("run: npm ci") < text.index("nick-fields/retry@")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_corpus.py -q -k "sources or installs"`
Expected: three `has no sources` failures and one `'run: npm ci' in text` failure.

- [ ] **Step 3: Repair the workflow**

In `web-ts/files/.github/workflows/ci.yml`, between the `setup-node` step and the retry step, insert:

```yaml
      - run: npm ci
```

(`history.yaml` lists the file as `"@final"`, so the replayed tree picks the change up; no history edit.)

- [ ] **Step 4: Add the sources lists**

`service-py/planted.json` decoys:

| id | sources |
|---|---|
| d1 | `["scout:duplication", "tool:jscpd"]` |
| d2 | `["scout:security", "tool:gitleaks", "rule:*"]` |
| d3 | `["scout:dependency-debt", "rule:manifest.*", "tool:osv-scanner"]` |
| d4 | `["scout:dead-code", "tool:vulture"]` |
| d5 | `["scout:dead-code", "tool:vulture"]` |
| d6 | `["scout:test-gaps"]` |
| d7 | `["rule:ownership.*"]` |
| d8 | `["scout:half-finished"]` |

`web-ts/planted.json` decoys:

| id | sources |
|---|---|
| d1 | `["scout:pipeline-infra", "rule:ci.*", "tool:actionlint"]` |
| d2 | `["scout:error-masking"]` |
| d3 | `["scout:half-finished"]` |
| d4 | `["scout:dead-code", "tool:knip"]` |
| d5 | `["scout:duplication", "tool:jscpd"]` |
| d6 | `["scout:dead-code", "tool:knip"]` |
| d7 | `["scout:security", "tool:gitleaks", "rule:*"]` |
| d8 | `["scout:pipeline-infra"]` |

`mixed-decoys/planted.json` decoys:

| id | sources |
|---|---|
| d1 | `["scout:complex-units", "tool:lizard"]` |
| d2 | `["scout:dead-code"]` |
| d3 | `["scout:dead-code"]` |
| d4 | `["scout:god-classes"]` |
| d5 | `["scout:error-masking"]` |
| d6 | `["scout:dead-code"]` |
| d7 | `["scout:pipeline-infra", "rule:container.*"]` |
| d8 | `["scout:pipeline-infra", "rule:iac.*"]` |
| d9 | `["scout:half-finished"]` |
| d10 | `["scout:error-masking"]` |
| d11 | `["rule:ownership.*"]` |

Add the key after `"why"` in each decoy object, keeping the file's existing indentation (two spaces, one decoy per object block as it is now).

- [ ] **Step 5: Run the corpus tests, the chain goldens and the gate**

Run: `python -m pytest skills/tech-debt-scan/tests/test_corpus.py skills/tech-debt-scan/tests/test_chain_goldens.py skills/tech-debt-scan/tests/test_evaluate.py -q`
Expected: pass. The workflow edit changes no golden (no rule fires on it before or after, and the canned scout replies are inputs); if `test_chain_goldens` reports a diff, stop and record which file moved before regenerating anything.

- [ ] **Step 6: Documents and commit**

`docs/architecture.md`: in the corpus paragraph (grep `planted.json`), one sentence: every decoy carries a `sources` list and `test_every_decoy_names_its_sources` pins it. `docs/evaluation-log.md`: no row changes; add one dated paragraph above the table's introduction saying rows before 2026-09-xx were scored without `sources` and without the `npm ci` step, so their decoy columns are not comparable with later rows.

```bash
git add skills/tech-debt-scan/tests/fixtures/corpus skills/tech-debt-scan/tests/test_corpus.py docs/architecture.md docs/evaluation-log.md
git commit -m "$(cat <<'EOF'
test(tech-debt-scan): every decoy names its sources; web-ts installs before it tests

All 27 planted decoys carry the producer tokens they were planted to trap,
pinned by a corpus test that also checks the token vocabulary. The web-ts
workflow gains the run: npm ci step it always meant to have, so its d1
decoy no longer draws a true pipeline-infra finding.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: the zero-churn file — `legacy_export.py` in its own 2004 commit

**Files:**
- Modify: `skills/tech-debt-scan/tests/fixtures/corpus/service-py/history.yaml` (the first commit's `files` map, and a new commit before it)
- Modify: `skills/tech-debt-scan/tests/test_corpus.py:13` (`EXPECTED_COMMITS["service-py"]` 16 → 17)
- Test: `skills/tech-debt-scan/tests/test_inventory_v2.py` (it already takes `service_py_repo`, e.g. `test_service_py_path_classes` at line 74), `tests/test_apply_verdicts.py`, goldens via `UPDATE_GOLDENS=1`

**Interfaces:**
- Produces: `src/pay/legacy_export.py` has churn 0, fan-in 0 and path class `source` in the replayed fixture; the 2.3 dead-code cap can return B for it.

Validated 2026-09-08 by replaying the edited history: before churn 1 / fan-in 0 / hotspot 2.5; after churn 0 / fan-in 0 / hotspot 0.0; no other commit touches the file and nothing imports it.

- [ ] **Step 1: Write the failing tests**

In the inventory test file that already uses `service_py_repo`:

```python
def test_legacy_export_has_zero_churn_and_zero_fan_in(service_py_repo: Path) -> None:
    """Spec 6: the one genuinely zero-churn file, so the 2.3 dead-code cap can award B."""
    from config import DEFAULTS
    from inventory import build_all

    inventory, _ = build_all(service_py_repo, churn_months=240, config=DEFAULTS)
    entry = next(e for e in inventory["files"] if e["path"] == "src/pay/legacy_export.py")
    assert entry["churn"] == 0 and entry["fan_in_approx"] == 0
    assert entry["path_class"] == "source"
```

In `tests/test_apply_verdicts.py`, beside the test at ~216 that pins "dead-code is capped at C without tool corroboration" (copy its candidate builder):

```python
    def test_dead_code_with_zero_churn_and_fan_in_is_capped_at_B_not_C(self) -> None:
        cand = _candidate(family="dead-code", signals={"churn": 0, "fan_in_approx": 0,
                                                       "path_class": "source"})
        cap, reason = family_cap(cand)
        assert cap == "B" and reason == "tool corroboration"
```

(Use the file's real builder name; if the B case is already covered, cite the existing test in the report and add nothing.)

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests -q -k "zero_churn"`
Expected: the inventory test fails with `assert 1 == 0` (churn 1). The cap test is a guard: `family_cap` already returns B for those signals, so it passes today — say so in the report ([[genuine-red]]).

- [ ] **Step 3: Move the file into a 2004 commit**

In `service-py/history.yaml`: remove the `src/pay/legacy_export.py: "@final"` line from the first commit's `files` map, and insert as the new first element of `commits`:

```yaml
  - author: "Ada Lovelace <ada@example.com>"
    date: "2004-01-01T10:00:00+00:00"
    subject: "chore: legacy export kept for the audit archive"
    files:
      src/pay/legacy_export.py: "@final"
```

Set `EXPECTED_COMMITS["service-py"] = 17` in `tests/test_corpus.py`.

- [ ] **Step 4: Regenerate goldens and run the gate**

Run: `UPDATE_GOLDENS=1 python -m pytest skills/tech-debt-scan/tests/test_chain_goldens.py -q`, then `git diff --stat skills/tech-debt-scan/tests/golden/service-py` — expect the inventory-derived goldens to move (`candidates.json` signals, `verified.json`, `ranked.json` priorities, `design.md`, `findings.json`, `diff.json` only if counts moved). The `scouts/`, `verdicts/` and `notes.json` must be untouched — `git diff --stat -- '*scouts*' '*verdicts*' '*notes.json'` empty. Then the full gate; `test_corpus` passes with 17 commits and the replayed tree unchanged.

- [ ] **Step 5: Commit**

```bash
git add -A skills/tech-debt-scan/tests
git commit -m "$(cat <<'EOF'
test(tech-debt-scan): service-py's legacy export is the corpus's zero-churn file

legacy_export.py moves out of the fixture's first commit into its own
commit dated 2004-01-01, outside the 240-month window and never touched
again, so its churn is 0 and its fan-in 0 and the 2.3 dead-code cap can
award tier B without a tool for the first time. Goldens carrying churn
and hotspot figures move with it; the canned replies still cite the file.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: mixed-decoys gains two neutral files so the correlation test runs on all three fixtures

**Files:**
- Create: `skills/tech-debt-scan/tests/fixtures/corpus/mixed-decoys/files/internal/units/units.go`, `.../internal/units/labels.go`
- Modify: `skills/tech-debt-scan/tests/fixtures/corpus/mixed-decoys/history.yaml` (first commit and the 2026-04-20 "feat: builder TLS option" commit)
- Test: `skills/tech-debt-scan/tests/test_corpus.py`, `tests/test_rank.py` (the parametrised correlation test), goldens via `UPDATE_GOLDENS=1`

Validated 2026-09-08: with these two files the neutral set scores 0.3 and 1.7 against a planted mean of 2.78.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_corpus.py`:

```python
def test_every_fixture_has_neutral_source_files(corpus: tuple[str, Path]) -> None:
    """Spec 6: the hotspot-correlation test needs source files that are neither planted nor decoys."""
    from config import DEFAULTS
    from inventory import build_all

    name, repo = corpus
    planted = json.loads((CORPUS_ROOT / name / "planted.json").read_text(encoding="utf-8"))
    taken = {p["path"] for p in planted["planted"]} | {d["path"] for d in planted["decoys"]}
    inventory, _ = build_all(repo, churn_months=240, config=DEFAULTS)
    neutral = [e["path"] for e in inventory["files"]
               if e["path_class"] == "source" and e["path"] not in taken]
    assert len(neutral) >= 2, f"{name}: {neutral}"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest skills/tech-debt-scan/tests/test_corpus.py -q -k neutral`
Expected: `mixed-decoys: []` fails; the other two pass.

- [ ] **Step 3: Add the files and their history**

`files/internal/units/units.go` (final content):

```go
package units

// Kilobytes converts a byte count to whole kilobytes, rounding down.
func Kilobytes(n int64) int64 {
	return n / 1024
}
```

`files/internal/units/labels.go` (final content):

```go
package units

// Label returns a short unit label for display.
func Label(plural bool) string {
	if plural {
		return "KBs"
	}
	return "KB"
}
```

`history.yaml`: in the first commit's `files` map add, with the pre-edit wording so the later commit is a real change:

```yaml
      internal/units/units.go: |
        package units

        // Kilobytes converts a byte count to whole kilobytes.
        func Kilobytes(n int64) int64 {
        	return n / 1024
        }
      internal/units/labels.go: |
        package units

        // Label returns a short unit label.
        func Label(plural bool) string {
        	if plural {
        		return "KBs"
        	}
        	return "KB"
        }
```

(Tabs inside Go bodies must stay tabs; the YAML block scalar preserves them.) In the 2026-04-20 commit ("feat: builder TLS option") add to its `files` map:

```yaml
      internal/units/units.go: "@final"
      internal/units/labels.go: "@final"
```

- [ ] **Step 4: Run the corpus, correlation and golden tests**

Run: `python -m pytest skills/tech-debt-scan/tests/test_corpus.py skills/tech-debt-scan/tests/test_rank.py -q -k "neutral or correlat or replayed_tree"` — the correlation test now reports `passed` for all three parametrisations (check with `-rs` that no skip remains for mixed-decoys). Then `UPDATE_GOLDENS=1 python -m pytest skills/tech-debt-scan/tests/test_chain_goldens.py -q` and inspect `git diff --stat skills/tech-debt-scan/tests/golden/mixed-decoys` (inventory totals move); canned replies untouched. Full gate.

- [ ] **Step 5: Commit**

```bash
git add -A skills/tech-debt-scan/tests
git commit -m "$(cat <<'EOF'
test(tech-debt-scan): mixed-decoys gains two neutral files so the correlation test runs

Every source file in the fixture was planted or a decoy, so the
hotspot-correlation test had no comparison set and skipped. Two small Go
files with two commits each give it one; the test now runs on all three
fixtures and a corpus test keeps at least two neutral source files in each.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: the 4b carry-forwards — range guard order, gitleaks `StartColumn`, two one-liners

**Files:**
- Modify: `skills/tech-debt-scan/scripts/merge_findings.py:479-498` (`_fingerprint_span`), `:556-580` (`_fact_candidate`), `:696-713` (the untiered route in `tool_candidates`), and the docstring paragraph at `:659-664` that records the `StartColumn` collapse
- Modify: `skills/tech-debt-scan/scripts/tool_normalisers.py:627-660` (`normalise_gitleaks`)
- Modify: `skills/tech-debt-scan/scripts/plan_scan.py:646` (`_module_display`)
- Modify: `skills/tech-debt-scan/scripts/apply_verdicts.py:104-105` (the test-quality reason)
- Test: `tests/test_merge_findings.py`, `tests/test_tool_normalisers.py`, `tests/test_plan_scan.py`, `tests/test_apply_verdicts.py`

- [ ] **Step 1: Check what the canned gitleaks payload carries**

Run: `python -c "import json;p=json.load(open('skills/tech-debt-scan/tests/fixtures/tool-output/gitleaks.json'));print([(r.get('StartLine'),r.get('StartColumn')) for r in p])"`
Expected: real gitleaks records carry `StartColumn`. If they do, the span change moves fingerprints in every golden that includes a gitleaks candidate (`candidates.json`, `verified.json`, `verify-plan.json`, `ranked.json`, `design.md`, `findings.json`, `diff.json`, and the canned `verdicts/` that name those fingerprints). **The canned verdicts must not be regenerated**, so decide by evidence: if any canned verdict names a gitleaks fingerprint, keep the column OUT of the fingerprint span and record it only in `extra` plus a `column` key on the evidence item — two same-line secrets then still collapse, and the report says so with the reason. If no canned verdict names one, fold the column into the span as below. Record the decision and its evidence in the report.

- [ ] **Step 2: Write the failing tests**

`tests/test_tool_normalisers.py`, beside `test_gitleaks_signals_are_fact_class`:

```python
    def test_gitleaks_keeps_the_start_column_in_extra(self) -> None:
        payload = [{"File": "a.py", "StartLine": 3, "EndLine": 3, "StartColumn": 17,
                    "RuleID": "generic-api-key", "Description": "d", "Secret": "S", "Match": "M"}]
        [sig] = normalise_gitleaks(payload, Path("."))
        assert sig["extra"]["column"] == 17
        assert "Secret" not in json.dumps(sig) and "M" != sig.get("message")

    def test_gitleaks_without_a_column_records_none(self) -> None:
        payload = [{"File": "a.py", "StartLine": 3, "RuleID": "r", "Description": "d"}]
        [sig] = normalise_gitleaks(payload, Path("."))
        assert sig["extra"]["column"] is None
```

`tests/test_merge_findings.py`, in the tool-candidates class:

```python
    def test_two_secrets_on_one_line_stay_two_candidates(self) -> None:
        base = {"tool": "gitleaks", "family": "security", "kind": "secret", "file": "a.py",
                "line_start": 3, "line_end": 3, "message": "generic-api-key: d", "fact": True}
        signals = [{**base, "extra": {"rule": "generic-api-key", "entropy": 4.0, "column": 5}},
                   {**base, "extra": {"rule": "generic-api-key", "entropy": 4.1, "column": 40}}]
        new, _ = tool_candidates(signals, self._inventory(), [])
        assert len(new) == 2 and new[0]["fingerprint"] != new[1]["fingerprint"]

    def test_a_hadolint_fact_with_no_range_still_merges_into_a_same_file_rule_finding(self) -> None:
        rule = self._rule_finding(family="pipeline-infra", file="Dockerfile")  # the class's builder
        sig = {"tool": "hadolint", "family": "pipeline-infra", "kind": "container",
               "file": "Dockerfile", "line_start": None, "line_end": None,
               "message": "DL3007: latest", "fact": True, "extra": {"level": "warning"}}
        counts: list = []
        new, rules = tool_candidates([sig], self._inventory(), [rule], counts=counts)
        assert new == [] and "tool:hadolint" in rules[0]["confirmed_by"]
        assert not any("no usable line range" in (c[2] or "") for c in counts)

    def test_a_hadolint_fact_with_no_range_and_no_rule_finding_is_still_dropped(self) -> None:
        sig = {"tool": "hadolint", "family": "pipeline-infra", "kind": "container",
               "file": "Dockerfile", "line_start": None, "line_end": None,
               "message": "DL3007: latest", "fact": True, "extra": {"level": "warning"}}
        counts: list = []
        new, _ = tool_candidates([sig], self._inventory(), [], counts=counts)
        assert new == [] and any("no usable line range" in (c[2] or "") for c in counts)
```

(Use the class's real builder names for the inventory and a rule finding; read `test_hadolint_merges_into_a_same_file_rule_finding` at ~927 first and copy its setup.) The existing `test_a_hadolint_signal_with_a_null_line_range_is_dropped` (~1318) asserts the pre-fix order — update it to the "no rule finding" case above or delete it in favour of the two new ones, and say which in the report.

`tests/test_plan_scan.py`: extend the existing `(repository root)` test (grep it) to assert the new label and that it cannot equal a directory name:

```python
    assert _module_display(None, {"root"}) == "/"
    assert "/" not in {"root", "src"}
```

`tests/test_apply_verdicts.py`: a test-quality candidate without `tool:` gets `tier_reason` mentioning "CI data" — copy the wording test at ~216 and assert `"CI data" in out["tier_reason"]`.

- [ ] **Step 3: Run them to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_tool_normalisers.py skills/tech-debt-scan/tests/test_merge_findings.py skills/tech-debt-scan/tests/test_plan_scan.py skills/tech-debt-scan/tests/test_apply_verdicts.py -q -k "column or two_secrets or no_range or module_display or CI_data or ci_data"`
Expected: the column tests fail with `KeyError: 'column'`; the two-secrets test fails with `assert 1 == 2`; the no-range merge test fails on `new == []` being true but `confirmed_by` lacking the token (or on the counts assertion); the label and wording tests fail on the string.

- [ ] **Step 4: Implement**

`normalise_gitleaks`: `extra={"rule": rule, "entropy": record.get("Entropy"), "column": column}` where `column = record.get("StartColumn") if isinstance(record.get("StartColumn"), int) and not isinstance(record.get("StartColumn"), bool) else None`. Update its docstring: the column is kept because two secrets on one line under one rule share every other field.

`tool_candidates`, untiered route: move the `_MERGE_INTO_RULE_TOOLS` / `_merge_into_rule` block ABOVE the range guard, directly after the `path is None` check, so a covered hadolint or actionlint fact merges regardless of its range; the range guard then applies only to the candidate that would be raised. Rewrite the docstring bullet that describes the range guard to say the merge is tried first because it reads no range.

`_fingerprint_span` (only if Step 1 decided to fold the column in): add a keyword `column: int | None = None` and return `f"{path or ''}:{line_start}-{line_end}@{column}"` when `column is not None`; `_fact_candidate` passes `column=_usable_line((extra or {}).get("column")) if isinstance(extra, dict) else None`. Either way, `_fact_candidate` copies the column onto the evidence item as `"column": <int | None>` after `line_end` so a reader can tell the two hits apart, and the docstring paragraph at ~659-664 recording the collapse is rewritten to state what now happens.

`_module_display`: `return "root" if "root" not in real_modules else "/"` and update its docstring ("a label no directory can equal: a path segment cannot be `/`").

`family_cap`: split the three-family line so `test-quality` returns `(None if tool else "B"), "CI data, which this scan never reads"` while `dependency-debt` and `security` keep `"tool corroboration"`; check spec 2.3's wording for test-quality and quote its phrase.

- [ ] **Step 5: Regenerate goldens if fingerprints moved, run the gate**

If Step 1 folded the column in: `UPDATE_GOLDENS=1 python -m pytest skills/tech-debt-scan/tests/test_chain_goldens.py -q` and confirm `git diff --stat -- '*verdicts*'` is empty. Full gate.

- [ ] **Step 6: Documents and commit**

`docs/architecture.md`: the `tools_probe.py`/`tool_normalisers.py` row (gitleaks keeps `StartColumn` as `column`), the `merge_findings.py` row (merge before the range guard; the span), the `plan_scan.py` row (the root label), and the `apply_verdicts.py` row's test-quality reason. `skills/tech-debt-scan/tests/fixtures/tool-output/PROVENANCE.md` if it describes the gitleaks fields.

```bash
git add -A skills/tech-debt-scan docs/architecture.md
git commit -m "$(cat <<'EOF'
fix(tech-debt-scan): facts merge before the range guard; gitleaks keeps its column

A hadolint or actionlint fact with no usable range can still corroborate
a same-file rule finding, since that merge reads no range; the guard now
protects only the candidate route that builds evidence spans. gitleaks'
StartColumn survives normalisation so two secrets on one line under one
rule stay two candidates. The repo-root chunk label is one no directory
can equal, and the test-quality cap's reason names CI data as spec 2.3 does.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: the note agent joins the harness — notes call, render, guard, `notes` column, `--keep`

**Files:**
- Modify: `skills/tech-debt-scan/scripts/live_run.py` (imports, `LOG_HEADER`, a `NOTES_SCHEMA`, `_valid`, `run_chain`, `log_row`, `_main`)
- Modify: `docs/evaluation-log.md:105-106` (the header and separator gain the trailing `notes` column) and its prose
- Test: `skills/tech-debt-scan/tests/test_live_run.py` (the `FAKE` script, `LOG_HEADER_TEXT`, new tests)

**Interfaces:**
- Consumes: `design_writer.load_inputs(workdir)`, `render_notes_prompt(inputs) -> str`, `write_design(inputs, scan_date, out_path)`, `NOTE_PLACEHOLDER`; `evaluate.load_findings(workdir)`.
- Produces: `NOTES_SCHEMA: dict`; `run_chain(..., keep: Path | None = None)` writing `prompts/notes.md`, `notes.json`, `design.md`, `findings.json`; `log_row(..., notes: str)`; CLI `--keep <dir>`.

- [ ] **Step 1: Extend the fake claude with a notes mode and write the failing tests**

In `tests/test_live_run.py`'s `FAKE`, replace the `mode = ...` line with:

```python
if "remediation notes" in prompt:
    mode = "notes"
elif "read-only scout" in prompt:
    mode = "scout"
else:
    mode = "verifier"
```

and before the `else:` (verifier) branch add:

```python
elif mode == "notes":
    fps = [line.split("fingerprint: ")[1].strip()
           for line in prompt.splitlines() if line.startswith("fingerprint: ")]
    payload = [{"fingerprint": fp, "remediation": "Extract the helper, then delete the copy.",
                "acceptance_criteria": ["the copy is gone", "tests pass"]} for fp in fps]
```

Update `LOG_HEADER_TEXT` to the new header (below). Add tests:

```python
from live_run import NOTES_SCHEMA


def test_notes_schema_is_an_array_of_bounded_notes() -> None:
    assert NOTES_SCHEMA["type"] == "array"
    item = NOTES_SCHEMA["items"]
    assert item["required"] == ["fingerprint", "remediation", "acceptance_criteria"]
    assert item["properties"]["acceptance_criteria"]["minItems"] == 2
    assert item["properties"]["acceptance_criteria"]["maxItems"] == 5
    assert item["additionalProperties"] is False


def test_run_chain_renders_the_design_with_notes_from_the_agent(
    tmp_path: Path, fake_claude: str, service_py_repo: Path
) -> None:
    workdir = tmp_path / "wd"
    log = tmp_path / "log.md"
    log.write_text(LOG_HEADER_TEXT, encoding="utf-8")
    planted = Path(__file__).parent / "fixtures" / "corpus" / "service-py" / "planted.json"
    summary = run_chain(service_py_repo, workdir, families="quick", top=3, preset="balanced",
                        churn_months=240, model="haiku", budget=0.1, claude=fake_claude,
                        timeout=60, skip_agents=False, planted=planted, log_path=log,
                        fixture_name="service-py")
    for name in ("prompts/notes.md", "notes.json", "design.md", "findings.json"):
        assert (workdir / name).is_file(), name
    assert summary["notes_calls"] == 1
    design = (workdir / "design.md").read_text(encoding="utf-8")
    top = design.split("# Top ")[1].split("\n# Below the cut")[0]
    assert "remediation note not available" not in top
    assert "Extract the helper" in top
    row = log.read_text(encoding="utf-8").splitlines()[-1]
    top_n = json.loads((workdir / "ranked.json").read_bytes())["top_n"]
    assert row.endswith(f"| {len(top_n)}/{len(top_n)} |")
    report = json.loads((workdir / "evaluation.json").read_bytes())
    assert report["source"] == "findings.json"


def test_run_chain_refuses_to_score_when_a_baseline_or_diff_is_in_the_workdir(
    tmp_path: Path, fake_claude: str, service_py_repo: Path
) -> None:
    workdir = tmp_path / "wd"
    workdir.mkdir()
    (workdir / "diff.json").write_text("{}", encoding="utf-8")
    planted = Path(__file__).parent / "fixtures" / "corpus" / "service-py" / "planted.json"
    with pytest.raises(RuntimeError, match="baseline"):
        run_chain(service_py_repo, workdir, families="quick", top=3, preset="balanced",
                  churn_months=240, model="haiku", budget=0.1, claude=fake_claude,
                  timeout=60, skip_agents=False, planted=planted, log_path=None,
                  fixture_name="service-py")


def test_run_chain_keeps_the_run_documents_under_keep(
    tmp_path: Path, fake_claude: str, service_py_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)  # a foreign cwd: keep must not resolve against it
    workdir = tmp_path / "wd"
    keep = tmp_path / "runs" / "2026-04-15-test"
    planted = Path(__file__).parent / "fixtures" / "corpus" / "service-py" / "planted.json"
    run_chain(service_py_repo, workdir, families="quick", top=3, preset="balanced",
              churn_months=240, model="haiku", budget=0.1, claude=fake_claude, timeout=60,
              skip_agents=False, planted=planted, log_path=None, fixture_name="service-py",
              keep=keep)
    for name in ("evaluation.json", "design.md", "notes.json"):
        assert (keep / "service-py" / name).is_file(), name


def test_log_row_appends_the_notes_column_last(tmp_path: Path) -> None:
    log = tmp_path / "log.md"
    report = {"families": {}, "decoys_in_tier_a": 0, "decoys_in_top_n": 0,
              "tier_a": {"reported": 0, "precise": 0, "precision": None}}
    log_row(log, "service-py", "haiku", report, churn_months=None,
            scouts=0, verifiers=0, cost=0.0, notes="3/5")
    text = log.read_text(encoding="utf-8")
    assert text.splitlines()[0].endswith("| cost_usd | notes |")
    assert text.splitlines()[-1].endswith("| 0.00 | 3/5 |")
```

Also extend `test_run_chain_over_a_corpus_fixture_with_the_fake`'s file list with `"design.md"` and `"findings.json"`, and `test_cli_exit_codes` stays.

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_live_run.py -q`
Expected: `ImportError: cannot import name 'NOTES_SCHEMA'`; after adding the constant alone, the chain tests fail on `prompts/notes.md` missing, the guard test on no `RuntimeError`, the keep test on the missing directory, the log test on the header.

- [ ] **Step 3: Implement**

In `live_run.py`:

```python
from design_writer import NOTE_PLACEHOLDER, load_inputs, render_notes_prompt, write_design
from evaluate import evaluate, load_findings, render_table
```

```python
NOTES_SCHEMA: Final[dict[str, Any]] = {
    "type": "array",
    "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["fingerprint", "remediation", "acceptance_criteria"],
        "properties": {
            "fingerprint": {"type": "string"},
            "remediation": {"type": "string", "minLength": 1, "maxLength": 1200},
            "acceptance_criteria": {
                "type": "array", "minItems": 2, "maxItems": 5,
                "items": {"type": "string", "minLength": 1},
            },
        },
    },
}
LOG_HEADER: Final[str] = (
    "| date | fixture | model | churn_months | tier_a_precision | reported_precision "
    "| decoys_tier_a | decoys_top_n | recall | scouts | verifiers | cost_usd | notes |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
)
```

`_valid`, array branch: keep `isinstance(payload, list)` and add, when `schema is NOTES_SCHEMA`, that every item is a dict with the three required keys, a non-empty string `remediation` and a list of 2 to 5 non-empty strings — the CLI enforces the JSON schema, this is the structural twin `dispatch` already relies on for the other two contracts.

`run_chain`: add the parameter `keep: Path | None = None`. At the top, after `workdir.mkdir(...)`:

```python
    for stale in ("diff.json", "baseline.json"):
        if (workdir / stale).is_file():
            raise RuntimeError(
                f"{workdir / stale} exists: the harness never diffs against a baseline, and "
                "design_writer drops baseline-suppressed findings from findings.json, so a "
                "run scored here would set a bar from a filtered population"
            )
```

After `write_json(workdir / "ranked.json", ranked)`:

```python
    scan_date = datetime.now(UTC).date().isoformat()
    inputs = load_inputs(workdir)
    notes_prompt = workdir / "prompts" / "notes.md"
    notes_prompt.parent.mkdir(parents=True, exist_ok=True)
    notes_prompt.write_bytes(render_notes_prompt(inputs).encode("utf-8"))
    notes_calls = 0
    notes_output = workdir / "notes.json"
    if ranked["top_n"] and _needs_call(notes_output, skip_agents=skip_agents, label="notes"):
        res = dispatch(notes_prompt, notes_output, cwd=repo, model=model, budget=budget,
                       schema=NOTES_SCHEMA, claude=claude, timeout=timeout)
        cost += res.cost_usd
        notes_calls += 1
        if res.status != "ok":
            raise RuntimeError(f"notes agent failed: {res.error}")
    inputs = load_inputs(workdir)
    write_design(inputs, scan_date, workdir / "design.md")
    design_text = (workdir / "design.md").read_text(encoding="utf-8")
    top_section = design_text.split("# Top ", 1)[1].split("\n# Below the cut", 1)[0] \
        if "# Top " in design_text else ""
    filled = len(ranked["top_n"]) - top_section.count(NOTE_PLACEHOLDER) // 2
    notes_cell = f"{max(filled, 0)}/{len(ranked['top_n'])}"
```

(`NOTE_PLACEHOLDER` appears twice per unfilled top-N finding — `_finding_section` writes it under Remediation and again under Acceptance criteria, `design_writer.py:767-768` — hence the halving; assert that in the sequence test by checking the cell.) Then the evaluation block reads `findings, source_name = load_findings(workdir)` instead of `verified["findings"]`, sets `report["source"] = source_name` before `write_json(workdir / "evaluation.json", report)` (the CLI's `_main` does the same; `evaluate()` itself does not), passes `notes=notes_cell` to `log_row`, and adds `"notes_calls": notes_calls` to `summary`. After scoring, if `keep` is not None:

```python
        dest = keep / (fixture_name or repo.name)
        dest.mkdir(parents=True, exist_ok=True)
        for name in ("evaluation.json", "design.md", "notes.json", "findings.json"):
            src = workdir / name
            if src.is_file():
                shutil.copyfile(src, dest / name)
```

`log_row`: new keyword `notes: str = "-"`, appended as `f"| {notes} |\n"` in place of the current terminal `|\n`. `_main`: `parser.add_argument("--keep", default=None, help="directory to copy evaluation.json, design.md, notes.json and findings.json into, under <fixture>/")`, passed as `keep=Path(args.keep).resolve() if args.keep else None` (resolved before any chdir can matter — [[foreign-cwd]]). The `print` line at the end of `run_chain` gains the notes call count.

`docs/evaluation-log.md`: change lines 105-106 to the new header and separator (older rows stay one cell shorter), and add one paragraph above the table: from 2026-09-xx the harness renders the design document with the note agent's notes and scores `findings.json`; the trailing `notes` column is the top-N findings with a real note over N.

- [ ] **Step 4: Run the tests and the gate**

Run: `python -m pytest skills/tech-debt-scan/tests/test_live_run.py -q`, then the full gate. The seven `live`-marked tests stay deselected.

- [ ] **Step 5: Mutation check**

Temporarily skip the notes dispatch: the sequence test fails on `notes_calls` and on the placeholder assertion. Temporarily score `verified["findings"]` again: the `report["source"]` assertion fails. Temporarily remove the guard: the refusal test fails. Restore.

- [ ] **Step 6: Documents and commit**

`docs/architecture.md`'s live-harness paragraph and `README.md`'s live-run section: the notes call, the render, the guard, `--keep`, the `notes` column; read `python skills/tech-debt-scan/scripts/live_run.py --help` before writing any flag ([[keep-docs-in-sync]]).

```bash
git add -A skills/tech-debt-scan docs/architecture.md docs/evaluation-log.md README.md
git commit -m "$(cat <<'EOF'
feat(tech-debt-scan): the note agent joins the live harness

After ranking, live_run renders the notes prompt, dispatches the single
note agent under the same isolation and budget as the scouts, validates
its reply against NOTES_SCHEMA, renders design.md and findings.json, and
scores findings.json. It refuses to score a workdir holding a diff.json or
a baseline, appends a trailing notes column to the log, and copies the
run's documents under --keep so a bar can be audited against them.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: the run — executed by the controller, not a subagent

**Files:**
- Create: `docs/research/tech-debt-scan-v2/runs/<date>-5b/<fixture>/{evaluation.json,design.md,notes.json,findings.json}`
- Modify: `docs/evaluation-log.md` (three rows, appended by the harness)

This task spends about $11 through the `claude` CLI and needs the maintainer's authenticated CLI, so the controller runs it in this session rather than dispatching it. Same model and settings as every prior row: `sonnet`, the fixture's own `churn_months` (240), the deep family set and top 5 (every prior row shows 14 scouts and 5 verifier batches), per-call budget at the harness default.

- [ ] **Step 1: Confirm the settings of the previous rows**

Run: `sed -n '1,104p' docs/evaluation-log.md | grep -n -i -E "families|--top|deep|budget|command"` and read the prose above the table; the command below must match what it records. If the prose names different flags, use those and note it in the ledger.

- [ ] **Step 2: Run the three fixtures**

From the repository root, one after another (each 5 to 15 minutes):

```bash
python skills/tech-debt-scan/scripts/live_run.py service-py --families deep --top 5 --model sonnet --keep docs/research/tech-debt-scan-v2/runs/<date>-5b
python skills/tech-debt-scan/scripts/live_run.py web-ts --families deep --top 5 --model sonnet --keep docs/research/tech-debt-scan-v2/runs/<date>-5b
python skills/tech-debt-scan/scripts/live_run.py mixed-decoys --families deep --top 5 --model sonnet --keep docs/research/tech-debt-scan-v2/runs/<date>-5b
```

Expected: exit 0 each, a table per fixture on stdout, three rows appended to `docs/evaluation-log.md` with a `notes` cell, and the four documents per fixture under the keep directory. A non-zero exit stops the task: the error line is recorded in the ledger and the failed fixture is re-run once only if the cause is a transport error (timeout, CLI refusal), never for a bad number.

- [ ] **Step 3: Read the rows**

Record in the ledger, per fixture: `tier_a_precision`, `decoys_tier_a`, `decoys_top_n`, `notes`, `cost_usd`. Compute the minimum tier A precision across the three and round it DOWN to the nearest 0.05 (`math.floor(x * 20) / 20`).

- [ ] **Step 4: Commit the run**

```bash
git add docs/evaluation-log.md docs/research/tech-debt-scan-v2/runs
git commit -m "$(cat <<'EOF'
docs(tech-debt-scan): phase 5b live run over the repaired corpus

Three rows, sonnet, churn 240, deep set, top 5, with the note agent's
remediation notes rendered for the first time. The run's evaluation,
design, notes and findings documents are kept under docs/research so the
bar can be audited against them.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: the bar

**Files:**
- Modify: `docs/superpowers/specs/2026-09-04-tech-debt-scan-v2-design.md` — section 1 success criterion 2 (line ~24), section 6 live policy (line ~680 "Release bars"), section 9 assumption 1 (line ~712), and the section 10 confidence row that mentions 0.80 (line ~749)
- Modify: `docs/evaluation-log.md` (one paragraph naming the bar), `README.md` and `docs/architecture.md` wherever `0.80` or "provisional" appears

Two outcomes (spec section 11):

- **No decoy at tier A or in the top N in any of the three rows.** The bar is the rounded-down minimum. Write it as "**<value>**, measured on <date> (phase 5b, three fixtures, the minimum across them rounded down to 0.05)". Every "provisional 0.80" sentence becomes that; the `grep -rn "0\.80\|provisional" docs README.md skills/tech-debt-scan/SKILL.md` list must come back empty of bar references (the research documents under `docs/research/` are history and stay).
- **A decoy at tier A or in the top N.** No bar is written. The decoy's `sources` list and the finding's producers (read `evaluation.json`'s `decoys` entry and `findings.json`) say whether the hit is a real false positive or a fixture defect; the ruling goes into the ledger, and a paragraph in `docs/evaluation-log.md` records it. The spec's provisional language stays, with one sentence added to section 11: "5b's run of <date> put a decoy at tier A on <fixture> (<id>, <producer>); no bar was set; see the log." A second run is a separate decision for the user.

- [ ] **Step 1: Write the edits with a script that asserts each target sentence exists once** (the pattern `scratchpad/amend_spec_5b.py` on this branch used), run it, read the diff.

- [ ] **Step 2: Gate and commit**

`python -m pytest -q skills/tech-debt-scan/tests/test_skill_check.py` (SKILL.md may mention the bar) and the full gate.

```bash
git add docs README.md skills/tech-debt-scan/SKILL.md
git commit -m "$(cat <<'EOF'
docs(tech-debt-scan): the tier A bar is measured, not provisional

The minimum tier A precision across the three repaired fixtures in the
phase 5b run, rounded down to 0.05, replaces the provisional 0.80 in the
spec's success criteria and live policy; the assumption and confidence
rows that argued from the provisional figure now argue from the measured one.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

## Self-review

**Spec coverage.** Section 6 corpus: `npm ci` (Task 3), `sources` and the token semantics (Tasks 1, 3), the corpus test that every decoy carries a list (Task 3), the zero-churn file (Task 4), the neutral files and the correlation test (Task 5). Section 4.7 `tool` and 4.11 producer fields (Task 2). Section 11's two 4b carry-forwards and two one-liners (Task 6). Section 6 live policy: the notes call, the render, the guard, `findings.json` scoring, the `notes` column, the kept documents (Task 7). The run and both outcomes of setting the bar (Tasks 8, 9). What 5b does not do is not planned. Nothing in the amended spec is unassigned.

**Placeholder scan.** Task 2 Step 1 and Task 6 Step 1 are evidence-gathering steps with a stated decision rule, not deferred work. Task 6's test code names class helpers the implementer must read first; the plan says which existing test to copy. Task 8 names the three commands and the stop rule. No "TBD", no "handle edge cases".

**Type consistency.** `producers(finding) -> frozenset[str]` and `source_matches(token, sources) -> bool` are defined in Task 1 and used only there. `run_chain(..., keep: Path | None = None)` and `log_row(..., notes: str = "-")` are defined in Task 7 and called by Task 7's tests and Task 8's CLI (`--keep`). `NOTES_SCHEMA` is an array schema, which `wire_schema` wraps and `unwrap_payload` unwraps, as `VERDICT_SCHEMA` is. `tool` is a key on every candidate after Task 2 and is read by Task 1's `producers` through `finding.get("tool")`, so a finding predating Task 2 still works.

**Order.** Tasks 1 and 2 before 3 so the corpus test's tokens have a consumer; 4 and 5 move goldens once each; 6 may move fingerprints and lands before 7 so the harness test runs on the final chain; 7 before 8; 9 last.
