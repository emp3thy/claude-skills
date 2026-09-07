# tech-debt-scan v2 phase 4b: the integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the probe's `tool-signals.json` change what the scan reports — leads, corroboration, candidates and tiers — and cut the probe into `/tech-debt-scan` as step 4.

**Architecture:** `plan_scan.py` turns inference-class signals into leads; `merge_findings.py` turns fact-class signals into candidates by three routings and adds the `tool:<name>` corroboration token that lifts the caps `apply_verdicts.family_cap` already codes; `apply_verdicts.py` records why a tier was assigned so the report can say it. No new bypass is built: `select_candidates` already pools only candidates whose `tier` is `None`, so a candidate arriving with `tier: "A"` skips verification today, and 4b adds osv facts as the second producer of that state.

**Tech Stack:** Python 3.11+, standard library plus `yaml`. `pytest` for tests. The external tools are subprocesses invoked by phase 4a's probe, never imported.

**Spec:** `docs/superpowers/specs/2026-09-04-tech-debt-scan-v2-design.md` — sections 4.5 (the probe's contract and the duplication decision), 4.6 (`plan_scan` and chunking), 4.7 (merge, the three routings, the producer invariant), 4.8 (the tier assignment and the budget rule), 5 and 6 (SKILL.md), 11 (phase 4b's scope and gate). Read 4.7 and 4.8 before Task 1.

## Global Constraints

- Python 3.11+; standard library only in the skill's scripts, plus `yaml`. No new dependencies.
- Flat sibling imports: `from config import load_config`, `from inventory import write_json`, `from redaction import redact`. Never package-relative.
- `python -m ruff check .`, `python -m mypy`, `python skills/tech-debt-scan/scripts/skill_check.py`, `python -m pytest -q` all green before every commit. The suite baseline entering this plan is 996 passed, 2 skipped, 7 deselected.
- Goldens are byte-compared, written LF-only through `inventory.write_json`, and regenerate byte-identically under `UPDATE_GOLDENS=1`.
- **The producer invariant:** `rules.py` and osv fact-class signals are the only producers of a non-`None` `tier` at merge time. Any other class acquiring one silently skips verification.
- Every quote, message and free-text field written to any document passes through `redact`, and redaction runs **before** any truncation. Both halves have been violated before, in `merge_findings` and again in `tools_probe`.
- No field that can carry source text or a credential reaches a document: gitleaks' `Secret` and `Match`, jscpd's `fragment`, actionlint's `snippet`.
- Never run an external tool against a corpus fixture in place. Copy to the scratch directory first; a stray `_jscpd_out/` and a `.ruff_cache/` have both had to be removed by hand.
- Commit subjects in conventional-commit form; every body ends with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Confidence floor 92%. Every task states its confidence and embeds its own mitigation.

---

## Guardrails from prior sessions

Retrieved reflections that bind this plan, with their confidence.

- **Read the argparse setup, never an existing example, when documenting a command** (0.95, evidence 7). Task 9 documents SKILL.md's step 4; its flags come from real `--help` output. A prior session shipped a README example whose flags argparse did not define.
- **Keep docs in sync in the same change** (0.95, evidence 7). A module docstring belongs to the task that changes the module, not to the docs task.
- **Verify a RED step is genuinely RED** (0.75, evidence 2). Several tasks here add behaviour behind an existing code path that already returns something plausible — a candidate without a tier already reaches the verifier, and a finding without a `tier_reason` already renders a tier C row. Every RED assertion in this plan asserts on a value, never merely that something raised or that a key is absent.
- Dismissed as not applicable: the TypeScript `Partial<T>` reflection (no TypeScript source in this plan — the fixture files in Task 5 are test data, not typechecked), the `tempfile.mkstemp` reflection (no temp files opened here), the ralph-queue reflection (no queue).

---

## Assumptions surfaced

### Real concerns

**1. The tier assignment has no guard today, and 4b doubles its producers.** `earned_tier` returns `"A"` for any candidate arriving with `tier == "A"`, and `select_candidates` excludes any candidate whose tier is not `None` from verification. Nothing asserts who is allowed to set it. Adding osv as a second producer doubles the surface without adding a guard, and a third producer introduced by accident later would skip verification with no test failing.

*Mitigation, embedded in Task 3:* the producer invariant becomes an executable assertion over the whole corpus and over a canned signals file — every candidate with a non-`None` tier has `source` in `{"rule", "tool"}`, and every `source: "tool"` candidate with a tier came from a fact-class osv signal. The test is written before the routings, so it fails first for the right reason.

**2. The fixture change moves numbers that a human has been reading as stable.** Adding two files to `web-ts` changes `inventory.json`'s totals, so hotspot scores shift, so `ranked.json` and every downstream golden move for all three fixtures. Phase 2's measured tier A precision stops being comparable against the same corpus.

*Mitigation, embedded in Tasks 5 and 10:* Task 5 regenerates the goldens in one commit that touches nothing else, so the diff is reviewable as "the fixture changed and here is exactly what moved". Task 10's live gate runs both arms rather than comparing against phase 2's numbers, and `docs/evaluation-log.md` gains a note that rows before this phase are against a different corpus.

**3. jscpd may not find the planted clone either.** The whole fixture change rests on jscpd detecting a pair we author. It found nothing on the existing files even at a 20-token threshold, and its tokenizer's behaviour on TypeScript is not something to assume.

*Mitigation, embedded in Task 5 Step 1:* the pair is verified against real jscpd at its **default** 50-token threshold before any golden is regenerated or any downstream work is done. If it does not fire, the task stops and reports rather than proceeding — the fallback is a larger duplicated run, not a lowered threshold.

### Verified safe

- `apply_verdicts.family_cap` already returns `None` — no cap — when `confirmed_by` carries a `tool:` token, for duplication, dead-code, architecture, test-quality, dependency-debt and security. Read at `apply_verdicts.py:58`. Task 2 only has to make the token appear.
- `verify_prompts.select_candidates` pools with `[c for c in candidates if c.get("tier") is None]`, read at `verify_prompts.py:141`, so a tiered candidate is excluded from verification without any change.
- `rules.py:670` builds its candidates with `"tier": "A"` and a `fingerprint` from `evidence.fingerprint`; Task 3's osv candidates follow that shape exactly rather than inventing one.
- `plan_scan.KIND_CAPS` is a plain dict of kind to cap, read at `plan_scan.py:49`; adding a `tool` kind is one entry plus a lead builder.
- `config.py:64` already carries `chunking: {max_files: 1500, max_loc: 200000}`. Task 8 reads it; no config schema change.
- The probe writes `tool-signals.json` with `schema_version: 2`, a `tools` map and a `signals` list, every signal carrying `tool`, `family`, `kind`, `file`, `line_start`, `line_end`, `message`, `fact`, `extra`. Phase 4a's goldens pin it.

### Minor or accepted

- osv-scanner, gitleaks, hadolint and actionlint remain uninstallable here, so their routings are proven through canned signals only. `PROVENANCE.md` records it.
- `diff: NEW` on every finding until phase 5's baseline.
- Chunking cannot fire on any fixture; its tests lower the thresholds through config.
- The two-arm live run costs roughly $20–24 and is the phase's only token spend.
- A `tool` lead kind competes with pattern, SATD and inventory leads for prompt space; the cap is per kind, so prompts grow by up to 40 lines per family.

---

## File structure

| File | Responsibility |
|---|---|
| `skills/tech-debt-scan/scripts/plan_scan.py` | Modify. Read `tool-signals.json`, emit `tool` leads, and (Task 8) module chunking. |
| `skills/tech-debt-scan/scripts/merge_findings.py` | Modify. The corroboration token and the three fact-class routings. |
| `skills/tech-debt-scan/scripts/apply_verdicts.py` | Modify. Record `tier_reason`. |
| `skills/tech-debt-scan/scripts/design_writer.py` | Modify. Render `tier_reason` in the tier C table. |
| `skills/tech-debt-scan/scripts/tool_normalisers.py` | Modify. osv `source.path` colon handling. |
| `skills/tech-debt-scan/scripts/tools_probe.py` | Modify. `_redact_value` dict keys. |
| `skills/tech-debt-scan/SKILL.md`, `docs/architecture.md`, `README.md`, `docs/evaluation-log.md` | Modify in Tasks 9 and 10. |
| `skills/tech-debt-scan/tests/fixtures/corpus/web-ts/files/src/util/receipt.ts` and `receipt-legacy.ts` | Create in Task 5. The clone pair. |
| `skills/tech-debt-scan/tests/fixtures/tool-signals/` | Create in Task 6. Canned signals driving the chain golden. |

---

## Task 1: `plan_scan` reads `tool-signals.json`

**Confidence: 95%.** One reader, one lead builder, one cap entry, following the shape four other lead kinds already use.

**Files:**
- Modify: `skills/tech-debt-scan/scripts/plan_scan.py`
- Modify: `skills/tech-debt-scan/tests/test_plan_scan.py`

**Interfaces:**
- Consumes: `tool-signals.json` as phase 4a writes it; `Lead(kind, path, line, text, score=0.0)`; `KIND_CAPS`; `ScanDocs`.
- Produces: `ScanDocs.tool_signals: dict[str, Any]`, `_tool_leads(docs: ScanDocs, family: str) -> list[Lead]`, and `KIND_CAPS["tool"]`.

- [ ] **Step 1: Write the failing tests**

Add to `skills/tech-debt-scan/tests/test_plan_scan.py`:

```python
class TestToolLeads:
    def _docs(self, signals: list[dict]) -> object:
        from plan_scan import ScanDocs

        return ScanDocs(
            inventory={"files": [], "hotspots": []},
            tool_signals={"schema_version": 2, "tools": {}, "signals": signals},
        )

    def _signal(self, **over) -> dict:
        base = {
            "tool": "vulture", "family": "dead-code", "kind": "unused",
            "file": "src/pay/legacy.py", "line_start": 8, "line_end": 8,
            "message": "unused function 'export_v1'", "fact": False, "extra": {},
        }
        base.update(over)
        return base

    def test_an_inference_signal_for_the_family_becomes_a_lead(self) -> None:
        from plan_scan import _tool_leads

        leads = _tool_leads(self._docs([self._signal()]), "dead-code")
        assert [(lead.kind, lead.path, lead.line) for lead in leads] == [
            ("tool", "src/pay/legacy.py", 8)
        ]

    def test_the_lead_text_names_the_tool_and_its_message(self) -> None:
        from plan_scan import _tool_leads

        text = _tool_leads(self._docs([self._signal()]), "dead-code")[0].text
        assert "vulture" in text
        assert "unused function 'export_v1'" in text

    def test_a_signal_for_another_family_is_not_a_lead_here(self) -> None:
        from plan_scan import _tool_leads

        signals = [self._signal(family="duplication", tool="jscpd", kind="clone")]
        assert _tool_leads(self._docs(signals), "dead-code") == []

    def test_a_fact_class_signal_is_never_a_lead(self) -> None:
        """Fact-class signals become candidates in merge_findings; a lead as well
        would put the same fact in front of a scout and in the candidate list."""
        from plan_scan import _tool_leads

        signals = [self._signal(tool="gitleaks", family="security", kind="secret", fact=True)]
        assert _tool_leads(self._docs(signals), "security") == []

    def test_a_signal_with_no_file_is_dropped(self) -> None:
        from plan_scan import _tool_leads

        assert _tool_leads(self._docs([self._signal(file=None)]), "dead-code") == []

    def test_absent_tool_signals_yield_no_leads_and_do_not_raise(self) -> None:
        from plan_scan import ScanDocs, _tool_leads

        assert _tool_leads(ScanDocs(inventory={"files": []}), "dead-code") == []

    def test_the_tool_kind_is_capped_like_pattern_and_satd(self) -> None:
        from plan_scan import KIND_CAPS, LEAD_CAP

        assert KIND_CAPS["tool"] == LEAD_CAP
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_plan_scan.py -q -k ToolLeads`
Expected: FAIL — `TypeError: ScanDocs.__init__() got an unexpected keyword argument 'tool_signals'`, then `ImportError` for `_tool_leads`. Confirm the failure names the missing field, not something else.

- [ ] **Step 3: Add the field, the cap and the lead builder**

In `plan_scan.py`, add to `ScanDocs` beside the other document fields:

```python
    tool_signals: dict[str, Any] = field(default_factory=dict)
```

Extend the cap table:

```python
KIND_CAPS: Final[dict[str, int]] = {
    "pattern": LEAD_CAP, "satd": LEAD_CAP, "inventory": LEAD_CAP, "tool": LEAD_CAP,
}
```

Add the builder beside `_pattern_leads`:

```python
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
```

Register it in `_raw_leads` alongside the other kinds, and add `"tool": "Tool signals"` to the kind-label table beside `"inventory": "Inventory signals"`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest skills/tech-debt-scan/tests/test_plan_scan.py -q`
Expected: PASS.

- [ ] **Step 5: Load the document in `_main` and regenerate the plan goldens**

`_main` reads the other documents from the workdir; read `tool-signals.json` the same way, treating an absent file as `{}` — spec 4.6 says an absent file means every tool skipped, and an empty document yields no leads, which is the same outcome.

```bash
UPDATE_GOLDENS=1 python -m pytest skills/tech-debt-scan/tests/test_chain_goldens.py -q
python -m pytest skills/tech-debt-scan/tests/test_chain_goldens.py -q
```

The corpus fixtures have no `tool-signals.json` in their workdirs yet, so **no golden should move**. If one moves, stop and report — it means the reader changed behaviour where it should not have.

- [ ] **Step 6: Run the gate and commit**

```bash
python -m ruff check .
python -m mypy
python skills/tech-debt-scan/scripts/skill_check.py
python -m pytest -q
git add skills/tech-debt-scan/scripts/plan_scan.py skills/tech-debt-scan/tests/test_plan_scan.py
git commit -m "$(cat <<'EOF'
feat(tech-debt-scan): plan_scan reads tool signals as leads

Inference-class signals become leads under a tool kind capped like
pattern and SATD. Fact-class signals are excluded on purpose: merge
turns those into candidates, and a lead as well would put the same fact
in front of a scout and in the candidate list.

An absent tool-signals.json is an empty document, which yields no leads
-- the same outcome spec 4.6 gives for every tool skipped.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: the corroboration token that lifts the caps

**Confidence: 94%.** The token is one addition to a `sources` set that already collects five other kinds. The subtlety is the matching rule — what counts as corroborating — and Step 1 pins it.

**Files:**
- Modify: `skills/tech-debt-scan/scripts/merge_findings.py`
- Modify: `skills/tech-debt-scan/tests/test_merge_findings.py`

**Interfaces:**
- Consumes: `tool-signals.json`; the `_corroborate(cand, patterns, rule_findings, inventory)` call site around `merge_findings.py:453`.
- Produces: `tool:<name>` entries in a candidate's `confirmed_by`.

- [ ] **Step 1: Write the failing tests**

Add to `skills/tech-debt-scan/tests/test_merge_findings.py`:

```python
class TestToolCorroboration:
    def _signal(self, **over) -> dict:
        base = {
            "tool": "jscpd", "family": "duplication", "kind": "clone",
            "file": "src/util/format.ts", "line_start": 1, "line_end": 8,
            "message": "8 duplicated lines", "fact": False, "extra": {},
        }
        base.update(over)
        return base

    def _candidate(self, **over) -> dict:
        base = {
            "fingerprint": "f" * 16, "family": "duplication",
            "evidence": [{"file": "src/util/format.ts", "line_start": 2, "line_end": 6,
                          "quote": "x", "quote_verified": True}],
            "confirmed_by": ["scout:duplication"],
            "signals": {}, "source": "scout",
        }
        base.update(over)
        return base

    def test_a_same_family_same_file_signal_adds_its_token(self) -> None:
        from merge_findings import corroborate_with_tools

        cand = self._candidate()
        corroborate_with_tools([cand], [self._signal()])
        assert "tool:jscpd" in cand["confirmed_by"]

    def test_a_different_family_does_not_corroborate(self) -> None:
        from merge_findings import corroborate_with_tools

        cand = self._candidate()
        corroborate_with_tools([cand], [self._signal(family="dead-code", tool="vulture")])
        assert cand["confirmed_by"] == ["scout:duplication"]

    def test_a_different_file_does_not_corroborate(self) -> None:
        from merge_findings import corroborate_with_tools

        cand = self._candidate()
        corroborate_with_tools([cand], [self._signal(file="src/other.ts")])
        assert cand["confirmed_by"] == ["scout:duplication"]

    def test_a_fact_class_signal_does_not_corroborate_here(self) -> None:
        """Fact-class signals become candidates; corroborating as well would let
        one signal both raise a finding and vouch for it."""
        from merge_findings import corroborate_with_tools

        cand = self._candidate()
        corroborate_with_tools([cand], [self._signal(fact=True)])
        assert cand["confirmed_by"] == ["scout:duplication"]

    def test_the_token_is_added_once_for_two_signals_from_one_tool(self) -> None:
        from merge_findings import corroborate_with_tools

        cand = self._candidate()
        corroborate_with_tools([cand], [self._signal(), self._signal(line_start=20)])
        assert cand["confirmed_by"].count("tool:jscpd") == 1

    def test_confirmed_by_stays_sorted(self) -> None:
        from merge_findings import corroborate_with_tools

        cand = self._candidate(confirmed_by=["scout:duplication", "rule:ci.pinning"])
        corroborate_with_tools([cand], [self._signal()])
        assert cand["confirmed_by"] == sorted(cand["confirmed_by"])

    def test_a_signal_with_no_file_corroborates_nothing(self) -> None:
        from merge_findings import corroborate_with_tools

        cand = self._candidate()
        corroborate_with_tools([cand], [self._signal(file=None)])
        assert cand["confirmed_by"] == ["scout:duplication"]


class TestToolTokenLiftsTheCap:
    def test_a_duplication_finding_reaches_A_only_with_a_tool_token(self) -> None:
        """family_cap already returns None for duplication when a tool: token is
        present; this pins that the token merge adds is the one it reads."""
        from apply_verdicts import family_cap

        without = {"family": "duplication", "confirmed_by": ["scout:duplication"], "signals": {}}
        with_tool = {"family": "duplication",
                     "confirmed_by": ["scout:duplication", "tool:jscpd"], "signals": {}}
        assert family_cap(without) == "B"
        assert family_cap(with_tool) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_merge_findings.py -q -k ToolCorroboration`
Expected: FAIL — `ImportError: cannot import name 'corroborate_with_tools'`. `TestToolTokenLiftsTheCap` should PASS already; that is the point, and it documents the existing behaviour the token feeds.

- [ ] **Step 3: Write the corroborator**

In `merge_findings.py`:

```python
def corroborate_with_tools(
    candidates: list[dict[str, Any]], signals: list[dict[str, Any]]
) -> None:
    """Add a ``tool:<name>`` token where an inference signal backs a candidate.

    This token is the whole mechanism by which the 2.3 caps lift:
    ``apply_verdicts.family_cap`` returns no cap for duplication, dead-code,
    architecture, test-quality, dependency-debt and security once it is
    present. Matching is same family, same file — a tool that flags the same
    file for the same reason is a second opinion, and line proximity is not
    required because a tool's range and a scout's rarely coincide.

    Fact-class signals are excluded: those become candidates in their own
    right, and letting one both raise a finding and vouch for it would make a
    single source look like two.
    """
    by_family: dict[tuple[str, str], set[str]] = {}
    for item in signals:
        if not isinstance(item, dict) or item.get("fact"):
            continue
        path, family, tool = item.get("file"), item.get("family"), item.get("tool")
        if not isinstance(path, str) or not path or not family or not tool:
            continue
        by_family.setdefault((str(family), path), set()).add(str(tool))
    if not by_family:
        return
    for cand in candidates:
        evidence = cand.get("evidence") or []
        if not evidence:
            continue
        key = (str(cand.get("family")), str(evidence[0].get("file")))
        tools = by_family.get(key)
        if not tools:
            continue
        cand["confirmed_by"] = sorted(set(cand["confirmed_by"]) | {f"tool:{t}" for t in tools})
```

Call it in `merge` immediately after the existing `_corroborate` loop, passing the signals read from `tool-signals.json` (absent file means an empty list).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest skills/tech-debt-scan/tests/test_merge_findings.py -q`
Expected: PASS.

- [ ] **Step 5: Run the gate and commit**

```bash
python -m ruff check .
python -m mypy
python -m pytest -q
git add skills/tech-debt-scan/scripts/merge_findings.py skills/tech-debt-scan/tests/test_merge_findings.py
git commit -m "$(cat <<'EOF'
feat(tech-debt-scan): tool signals corroborate candidates

An inference-class signal on the same file and family adds a tool:<name>
token to confirmed_by, which is the whole mechanism by which the 2.3 caps
lift -- family_cap already returns no cap once it is present, so nothing
in apply_verdicts changes.

Matching is family and file, not line proximity: a tool's range and a
scout's rarely coincide. Fact-class signals are excluded because they
become candidates themselves, and one source vouching for its own
finding would look like two.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: the three fact-class routings, and the producer invariant

**Confidence: 92%.** The riskiest task in the plan: it adds the second producer of a tier that skips verification. The invariant test is written first, deliberately, so the guard exists before the thing it guards.

**Files:**
- Modify: `skills/tech-debt-scan/scripts/merge_findings.py`
- Modify: `skills/tech-debt-scan/tests/test_merge_findings.py`

**Interfaces:**
- Consumes: `evidence.fingerprint(family, path, quote)`; `evidence.signals_for(inventory, path)`; the rule candidate shape at `rules.py:645-671`.
- Produces: `tool_candidates(signals, inventory, rule_findings) -> tuple[list[dict], list[dict]]` returning `(new_candidates, merged_rule_findings)`.

- [ ] **Step 1: Write the invariant test first, and watch it pass**

```python
class TestTierProducerInvariant:
    """Spec 4.7: rules.py and osv fact-class signals are the only producers of a
    non-None tier at merge time. select_candidates pools only candidates whose
    tier is None, so any other class acquiring one skips verification silently."""

    def test_only_rule_and_tool_sources_ever_carry_a_tier(self, tmp_path) -> None:
        from merge_findings import merge

        document = merge_over_corpus_fixture(tmp_path, "service-py")
        tiered = [c for c in document["candidates"] if c.get("tier") is not None]
        assert tiered, "the fixture must produce at least one tiered candidate"
        assert {c["source"] for c in tiered} <= {"rule", "tool"}

    def test_every_tiered_tool_candidate_came_from_an_osv_fact(self, tmp_path) -> None:
        from merge_findings import merge

        document = merge_over_corpus_fixture(tmp_path, "service-py")
        for cand in document["candidates"]:
            if cand.get("tier") is not None and cand["source"] == "tool":
                assert any(t == "tool:osv-scanner" for t in cand["confirmed_by"])
```

`merge_over_corpus_fixture` is a helper this test file already needs; if one does not exist, write it beside these tests as a thin wrapper that copies the named corpus fixture into `tmp_path`, runs the chain's earlier steps, and returns `merge`'s document. Do not inline the chain into each test.

Run it now, before implementing anything: `python -m pytest skills/tech-debt-scan/tests/test_merge_findings.py -q -k TierProducer`
Expected: PASS — today only `rules.py` sets a tier, so the invariant already holds. It must keep holding after Step 3, which is the point of writing it first.

- [ ] **Step 2: Write the failing routing tests**

```python
class TestFactClassRoutings:
    def _osv(self) -> dict:
        return {
            "tool": "osv-scanner", "family": "dependency-debt", "kind": "vuln",
            "file": "package-lock.json", "line_start": None, "line_end": None,
            "message": "left-pad 1.1.3 (npm) is affected by GHSA-xxxx-yyyy-zzzz",
            "fact": True,
            "extra": {"package": "left-pad", "version": "1.1.3",
                      "ecosystem": "npm", "id": "GHSA-xxxx-yyyy-zzzz", "aliases": []},
        }

    def _gitleaks(self) -> dict:
        return {
            "tool": "gitleaks", "family": "security", "kind": "secret",
            "file": "src/config/settings.py", "line_start": 12, "line_end": 12,
            "message": "generic-api-key: Detected a Generic API Key",
            "fact": True, "extra": {"rule": "generic-api-key", "entropy": 4.31},
        }

    def _hadolint(self) -> dict:
        return {
            "tool": "hadolint", "family": "pipeline-infra", "kind": "dockerfile",
            "file": "Dockerfile", "line_start": 1, "line_end": 1,
            "message": "DL3006: Always tag the version of an image explicitly",
            "fact": True, "extra": {"code": "DL3006", "level": "warning", "severity": 3},
        }

    def test_an_osv_fact_becomes_a_tier_A_candidate_with_no_line_range(self) -> None:
        from merge_findings import tool_candidates

        new, _ = tool_candidates([self._osv()], {"files": []}, [])
        assert len(new) == 1
        cand = new[0]
        assert cand["tier"] == "A"
        assert cand["source"] == "tool"
        assert cand["evidence"][0]["file"] == "package-lock.json"
        assert cand["evidence"][0]["line_start"] is None
        assert cand["evidence"][0]["quote_verified"] is True
        assert "tool:osv-scanner" in cand["confirmed_by"]

    def test_an_osv_candidate_has_a_fingerprint_like_any_other(self) -> None:
        from merge_findings import tool_candidates

        new, _ = tool_candidates([self._osv()], {"files": []}, [])
        assert len(new[0]["fingerprint"]) == 16

    def test_two_advisories_on_one_package_are_two_candidates(self) -> None:
        from merge_findings import tool_candidates

        second = self._osv()
        second["extra"] = dict(second["extra"], id="GHSA-aaaa-bbbb-cccc")
        second["message"] = "left-pad 1.1.3 (npm) is affected by GHSA-aaaa-bbbb-cccc"
        new, _ = tool_candidates([self._osv(), second], {"files": []}, [])
        assert len({c["fingerprint"] for c in new}) == 2

    def test_a_gitleaks_fact_becomes_a_candidate_with_no_tier(self) -> None:
        """Placeholders and test fixtures produce false positives, so gitleaks
        goes to the verifier (spec 4.5)."""
        from merge_findings import tool_candidates

        new, _ = tool_candidates([self._gitleaks()], {"files": []}, [])
        assert new[0]["tier"] is None
        assert new[0]["source"] == "tool"

    def test_hadolint_merges_into_a_same_file_rule_finding(self) -> None:
        from merge_findings import tool_candidates

        rule = {"fingerprint": "a" * 16, "family": "pipeline-infra", "source": "rule",
                "evidence": [{"file": "Dockerfile", "line_start": 3, "line_end": 3,
                              "quote": "FROM python", "quote_verified": True}],
                "confirmed_by": ["rule:container.image"], "tier": "A", "signals": {}}
        new, merged = tool_candidates([self._hadolint()], {"files": []}, [rule])
        assert new == []
        assert "tool:hadolint" in merged[0]["confirmed_by"]

    def test_hadolint_becomes_its_own_candidate_when_no_rule_covers_the_file(self) -> None:
        from merge_findings import tool_candidates

        new, merged = tool_candidates([self._hadolint()], {"files": []}, [])
        assert len(new) == 1
        assert new[0]["evidence"][0]["file"] == "Dockerfile"
        assert new[0]["tier"] is None

    def test_an_inference_signal_never_becomes_a_candidate(self) -> None:
        from merge_findings import tool_candidates

        inference = dict(self._osv(), fact=False, tool="vulture", family="dead-code")
        new, _ = tool_candidates([inference], {"files": []}, [])
        assert new == []

    def test_every_message_is_redacted(self) -> None:
        from merge_findings import tool_candidates

        leaky = dict(self._gitleaks(),
                     message='found token = "sk_live_51H8f2kL9mN3pQ7rS4tU6vW" in settings')
        new, _ = tool_candidates([leaky], {"files": []}, [])
        blob = json.dumps(new)
        assert "sk_live_51H8f2kL9mN3pQ7rS4tU6vW" not in blob
        assert "sk_l***" in blob
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_merge_findings.py -q -k FactClass`
Expected: FAIL — `ImportError: cannot import name 'tool_candidates'`.

- [ ] **Step 4: Write the routings**

In `merge_findings.py`, following the rule candidate shape at `rules.py:645-671` exactly rather than inventing one. The osv branch sets `tier: "A"`; gitleaks and an uncovered hadolint or actionlint set no tier; a covered hadolint or actionlint mutates the rule finding's `confirmed_by` and produces no candidate. Every text field goes through `redact`. The quote for a null-line-range candidate states the fact, as spec 4.5 gives repository-level rule facts.

Fingerprint each candidate with `evidence.fingerprint(family, path, quote)` so two advisories on one package differ by their quote.

Call `tool_candidates` in `merge` after the rule findings are read and before suppressions are applied, so a tool candidate can be suppressed like any other.

- [ ] **Step 5: Run the tests, including the invariant, to verify all pass**

Run: `python -m pytest skills/tech-debt-scan/tests/test_merge_findings.py -q`
Expected: PASS. The invariant test from Step 1 must still pass — if it now fails, a routing gave a tier to something that is not an osv fact, which is the defect this task exists to avoid.

- [ ] **Step 6: Run the gate and commit**

```bash
python -m ruff check .
python -m mypy
python -m pytest -q
git add skills/tech-debt-scan/scripts/merge_findings.py skills/tech-debt-scan/tests/test_merge_findings.py
git commit -m "$(cat <<'EOF'
feat(tech-debt-scan): fact-class tool signals become candidates

Three routings from spec 4.5. osv findings enter with tier A already set,
a null line range and the manifest path as evidence, so they skip
verification through the path rule findings already use. gitleaks enters
untiered and reaches the verifier, because placeholders and fixtures are
what a verifier is for. hadolint and actionlint merge into a same-file
rule finding rather than raising a second candidate for the same fact.

The producer invariant is asserted first and kept: rules.py and osv facts
are the only producers of a non-null tier. select_candidates pools only
untiered candidates, so anything else acquiring one would skip
verification with nothing to notice.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: record why a tier was assigned

**Confidence: 94%.** One field set in one function, and one column rendered from it. Absorbs a finding parked since phase 3.

**Files:**
- Modify: `skills/tech-debt-scan/scripts/apply_verdicts.py`
- Modify: `skills/tech-debt-scan/scripts/design_writer.py`
- Modify: `skills/tech-debt-scan/tests/test_apply_verdicts.py`, `test_design_writer.py`

**Interfaces:**
- Consumes: `earned_tier(cand, verdict)` at `apply_verdicts.py:92`; `family_cap(cand)`; the tier C table renderer in `design_writer.py`.
- Produces: `tier_reason: str` on every finding in `verified.json`, and its use as the tier C table's reason column.

- [ ] **Step 1: Write the failing tests**

```python
class TestTierReason:
    def _cand(self, **over) -> dict:
        base = {"fingerprint": "f" * 16, "family": "duplication", "source": "scout",
                "confirmed_by": ["scout:duplication"], "signals": {},
                "evidence": [{"file": "a.ts", "line_start": 1, "line_end": 2,
                              "quote": "x", "quote_verified": True}]}
        base.update(over)
        return base

    def _confirm(self) -> dict:
        return {"verdict": "confirm", "proof": "p", "severity": 3, "effort": "M",
                "trap_matched": None, "checked": [], "opened": []}

    def test_a_family_cap_says_so(self) -> None:
        from apply_verdicts import _finding

        out = _finding(self._cand(), self._confirm(), selected=True)
        assert out["tier"] == "B"
        assert out["tier_reason"] == "duplication is capped at B without tool corroboration"

    def test_a_lifted_cap_says_which_tool(self) -> None:
        from apply_verdicts import _finding

        cand = self._cand(confirmed_by=["scout:duplication", "tool:jscpd"])
        out = _finding(cand, self._confirm(), selected=True)
        assert out["tier"] == "A"
        assert "tool:jscpd" in out["tier_reason"]

    def test_an_unverified_candidate_says_so(self) -> None:
        from apply_verdicts import _finding

        out = _finding(self._cand(), None, selected=False)
        assert out["tier"] == "C"
        assert out["tier_reason"] == "not selected for verification"

    def test_a_downgrade_says_so(self) -> None:
        from apply_verdicts import _finding

        out = _finding(self._cand(), dict(self._confirm(), verdict="downgrade"), selected=True)
        assert out["tier_reason"] == "the verifier downgraded it"

    def test_a_rule_fact_says_so(self) -> None:
        from apply_verdicts import _finding

        out = _finding(self._cand(tier="A", source="rule"), None, selected=False)
        assert out["tier_reason"] == "a deterministic rule finding, true by construction"

    def test_every_finding_has_a_reason(self) -> None:
        """A blank reason renders a blank column, which is what this replaces."""
        from apply_verdicts import _finding

        for verdict in (None, self._confirm(), dict(self._confirm(), verdict="reject")):
            out = _finding(self._cand(), verdict, selected=True)
            assert out["tier_reason"].strip()
```

And in `test_design_writer.py`:

```python
    def test_the_tier_c_table_prints_the_tier_reason_not_the_verdict(self) -> None:
        """Four rows reading `confirm` told a maintainer nothing about why a
        finding is below the cut."""
        # Build inputs with one tier C finding whose tier_reason is distinctive,
        # render, and assert the reason appears in the tier C table row while the
        # bare verdict word does not stand alone in that column.
```

Write that last test out fully against the fixtures the file already uses; do not leave it as a comment.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_apply_verdicts.py -q -k TierReason`
Expected: FAIL with `KeyError: 'tier_reason'`. This is a genuine RED: the key does not exist, rather than existing and holding something else.

- [ ] **Step 3: Record the reason**

Refactor `earned_tier` to return the tier and its reason together, or add a sibling that computes the reason from the same inputs — either is acceptable, but the two must not be able to disagree, so do not duplicate the branch logic. State which you chose and why in the report.

The reasons, exactly:

- `"a deterministic rule finding, true by construction"` — arrived with `tier: "A"` and `source: "rule"`.
- `"a published advisory, true by construction"` — arrived with `tier: "A"` and `source: "tool"`.
- `"not selected for verification"` — no verdict.
- `"the verifier rejected it"`, `"the verifier downgraded it"`, `"the verifier referred it"` — by verdict kind.
- `"a quote could not be verified"` — confirmed but evidence unverified.
- `"<family> is capped at <tier> without tool corroboration"` — `family_cap` lowered it.
- `"confirmed and corroborated by <tokens>"` — reached A.
- `"confirmed, with no independent corroboration"` — reached B uncapped.

- [ ] **Step 4: Render it**

In `design_writer.py`, the tier C table's reason column takes `tier_reason` instead of the verdict. Where a finding predates this field — a v1 document, or a `verified.json` from an earlier run — fall back to the existing behaviour rather than raising.

- [ ] **Step 5: Run the tests and regenerate the goldens**

```bash
python -m pytest skills/tech-debt-scan/tests/test_apply_verdicts.py skills/tech-debt-scan/tests/test_design_writer.py -q
UPDATE_GOLDENS=1 python -m pytest skills/tech-debt-scan/tests/test_chain_goldens.py -q
python -m pytest skills/tech-debt-scan/tests/test_chain_goldens.py -q
```

Every `verified.json`, `ranked.json` and `design.md` golden will move — `verified.json` gains a field and the tier C tables gain real reasons. Read one `design.md` tier C table and confirm the reasons now say something a maintainer can act on. Report what the four `service-py` rows say before and after.

- [ ] **Step 6: Run the gate and commit**

```bash
python -m ruff check .
python -m mypy
python skills/tech-debt-scan/scripts/skill_check.py
python -m pytest -q
git add -A skills/tech-debt-scan
git commit -m "$(cat <<'EOF'
docs(tech-debt-scan): say why a finding got the tier it got

The tier C table printed the verdict, so four service-py rows read
"confirm" and told a maintainer nothing about why those findings are
below the cut -- a family cap in particular has a real reason that was
never shown.

apply_verdicts now records tier_reason beside the tier, computed from the
same branch rather than a parallel one so the two cannot disagree, and
the table renders it. A finding from an earlier run without the field
falls back to the old column.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: a clone pair jscpd actually finds

**Confidence: 92%.** Everything downstream rests on real jscpd detecting the pair, so Step 1 verifies that before anything else happens, and the task stops if it does not.

**Files:**
- Create: `skills/tech-debt-scan/tests/fixtures/corpus/web-ts/files/src/util/receipt.ts`
- Create: `skills/tech-debt-scan/tests/fixtures/corpus/web-ts/files/src/util/receipt-legacy.ts`
- Modify: every golden the fixture change moves

**Interfaces:**
- Consumes: nothing. Produces: a `web-ts` fixture whose duplication is tool-detectable.

- [ ] **Step 1: Verify real jscpd finds the pair, before touching the repository**

Copy `web-ts/files` to the scratch directory. Write the two files there. Run real jscpd at its **default** threshold:

```bash
jscpd --reporters json --output <scratch>/out <scratch>/web-ts/src
```

Read `<scratch>/out/jscpd-report.json` and confirm `duplicates` is non-empty and names both files. Paste the duplicate record into your report.

**If it is empty, stop.** Do not lower `--min-tokens`, and do not proceed to Step 2. Enlarge the shared run — more statements, not more comments, since jscpd tokenises — and try again. Report how many attempts it took and what finally worked; that is information the next person needs.

The pair should be plausible application code, not filler: a receipt-formatting function duplicated between a current and a legacy module is the shape the fixture already suggests elsewhere.

- [ ] **Step 2: Add the files to the fixture and confirm the probe sees it**

Copy the two verified files into the real fixture. Then run the probe against a **copy** of the fixture and confirm a jscpd signal for the pair appears in `tool-signals.json`.

- [ ] **Step 3: Regenerate every golden the change moves**

```bash
UPDATE_GOLDENS=1 python -m pytest skills/tech-debt-scan/tests -q
python -m pytest skills/tech-debt-scan/tests -q
```

Then answer these, in your report, before accepting anything:

1. Which goldens moved, and is each move explained by two new files — file counts, LOC, hotspot scores, ranking, the probe's signals?
2. Did any golden move that has nothing to do with `web-ts`? If so, stop and report; the fixture change should not reach the other two fixtures except through shared code paths.
3. Do the captured scout responses still verify their quotes? They cite files that still exist, so they should — confirm rather than assume.
4. Is the second run byte-identical to the first?

- [ ] **Step 4: Run the gate and commit, touching nothing else**

This commit changes the fixture and the goldens it moves, and nothing else, so the diff reads as exactly that.

```bash
python -m ruff check .
python -m mypy
python -m pytest -q
git add skills/tech-debt-scan/tests
git commit -m "$(cat <<'EOF'
test(tech-debt-scan): give web-ts a duplication real jscpd finds

jscpd reported no clones on either fixture even at a 20-token threshold:
the planted p2 pair is structurally similar but genuinely divergent, 16
lines against 22, so phase 4's headline claim could not be measured at
all. web-ts gains a real clone pair detected at jscpd's default 50-token
threshold, with the planted decoys untouched.

The threshold is not lowered, because one tuned to pass a fixture would
flood real repositories. Adding files moves inventory totals and
therefore hotspot scores and ranking, so the goldens move with them; the
captured scout responses stay valid because they cite files that still
exist.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: the chain golden that proves the bypass

**Confidence: 93%.** Deterministic, no live agent, no installed tool. It proves the wiring and the negative half of the gate.

**Files:**
- Create: `skills/tech-debt-scan/tests/fixtures/tool-signals/osv-and-friends.json`
- Modify: `skills/tech-debt-scan/tests/test_chain_goldens.py`
- Create: `skills/tech-debt-scan/tests/golden/tool-chain/` — `candidates.json`, `verified.json`, `ranked.json`

**Interfaces:**
- Consumes: `merge`, `apply`, `rank` as the chain test already drives them.
- Produces: a golden proving an osv fact reaches tier A with no verdict, and that nothing else does.

- [ ] **Step 1: Write the canned signals file**

A `tool-signals.json` in the phase 4a shape carrying, at minimum: one osv fact against a lockfile that exists in the `service-py` fixture; one gitleaks fact; one hadolint fact for a file with no rule finding; one jscpd inference signal on a file a scout finding already cites, so the corroboration path is exercised; and one inference signal for a family with no candidate, so the no-match path is exercised.

- [ ] **Step 2: Write the failing chain test**

Extend the chain test to run the fixture with this signals file in the workdir, driving `merge`, `apply` and `rank`, and byte-compare all three outputs against goldens under `tests/golden/tool-chain/`. Assert, beyond the byte comparison:

```python
    def test_the_osv_fact_is_tier_A_with_no_verdict(self) -> None:
        verified = self._chain_with_tool_signals()
        osv = next(f for f in verified["findings"] if f["source"] == "tool"
                   and "tool:osv-scanner" in f["confirmed_by"])
        assert osv["tier"] == "A"
        assert osv["verdict"] == "rule"
        assert osv["fingerprint"] not in self._verified_fingerprints()

    def test_no_other_candidate_class_skips_verification(self) -> None:
        candidates = self._candidates_with_tool_signals()
        for cand in candidates:
            if cand.get("tier") is not None:
                assert cand["source"] in {"rule", "tool"}
                if cand["source"] == "tool":
                    assert "tool:osv-scanner" in cand["confirmed_by"]

    def test_the_gitleaks_fact_is_sent_to_the_verifier(self) -> None:
        candidates = self._candidates_with_tool_signals()
        leak = next(c for c in candidates if "tool:gitleaks" in c["confirmed_by"])
        assert leak["tier"] is None
```

- [ ] **Step 3: Run to verify it fails, then generate and read the goldens**

Expected first failure: the golden files do not exist. Generate with `UPDATE_GOLDENS=1`, then **read all three** and answer in your report: does the osv candidate carry a null line range and a fact-stating quote? Does the gitleaks candidate appear in `verify-plan.json`'s selection rather than skipping it? Does the jscpd signal's token appear on the candidate it corroborates, and did that candidate's tier change as a result?

- [ ] **Step 4: Run the gate and commit**

```bash
python -m ruff check .
python -m mypy
python -m pytest -q
git add skills/tech-debt-scan/tests
git commit -m "$(cat <<'EOF'
test(tech-debt-scan): pin the fact-class chain end to end

osv-scanner cannot be installed here, so a canned tool-signals.json
drives merge, apply and rank exactly as a real run would. The golden
proves an osv fact reaches tier A with no verifier reading it, that a
gitleaks fact does reach the verifier, and -- the half that matters --
that no other candidate class arrives with a tier and skips verification.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: two parked fixes, in files this phase already touches

**Confidence: 95%.** Two small guarded changes with named tests.

**Files:**
- Modify: `skills/tech-debt-scan/scripts/tool_normalisers.py`, `tools_probe.py`
- Modify: their tests

- [ ] **Step 1: osv's `source.path` for docker and git sources**

`rel_path` rejects a colon in any segment, so an osv source path such as `alpine:3.18` or a git URL is dropped silently and the advisory is lost. 4b is the first phase to consume those paths.

Write the failing test first: an osv payload whose `source.type` is `docker` with `path: "alpine:3.18"`, asserting a candidate is produced whose evidence names the image rather than being dropped. Then handle it: a non-lockfile source is not a repository path, so it is carried as a fact about the image or repository rather than forced through `rel_path`. Say in your report how you represented it and why.

- [ ] **Step 2: `_redact_value` and dict keys**

`_redact_value` in `tools_probe.py` redacts every string value but never a dict key. Write the failing test — a signal whose `extra` has a secret-shaped token as a key — then fix, then confirm the test fails against the pre-fix code.

- [ ] **Step 3: Run the gate and commit**

```bash
python -m ruff check .
python -m mypy
python -m pytest -q
git add skills/tech-debt-scan
git commit -m "$(cat <<'EOF'
fix(tech-debt-scan): carry non-lockfile osv sources, redact dict keys

An osv source path for a docker image or a git URL carries a colon, which
rel_path rejects, so the advisory was dropped silently -- and 4b is the
first phase to consume those paths. _redact_value redacted every string
value but never a key, the same gap one level down from the one already
closed for values.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: module chunking and the halved deep thresholds

**Confidence: 92%.** No fixture can trigger chunking, so every test drives it through lowered config thresholds — which is also the only evidence the halving takes effect. Ordered last of the code tasks because it touches only `plan_scan.py` and is the piece that can be cut if the branch runs long.

**Files:**
- Modify: `skills/tech-debt-scan/scripts/plan_scan.py`
- Modify: `skills/tech-debt-scan/tests/test_plan_scan.py`
- Create: `skills/tech-debt-scan/tests/golden/chunked-plan-full.json`, `chunked-plan-halved.json`

**Interfaces:**
- Consumes: `config["chunking"]["max_files"]` and `["max_loc"]`; the selected set.
- Produces: `scan-plan.json` with `chunked: true` and entries named `scout-<family>-<module>` writing to `prompts/scout-<family>-<module>.md`.

- [ ] **Step 1: Write the failing tests**

Cover: below both thresholds gives `chunked: false` and today's entries unchanged; above `max_files` splits by top-level directory; above `max_loc` splits likewise; a module with no leads and no hotspot-band files for a family gets no entry for that family; the deep set halves both thresholds so a repository between the halved and full values chunks under `deep` and not under `default`; and every prompt path in the plan is unique.

That last one matters: two modules whose names collide after slugging would overwrite each other's prompt, and the plan would dispatch one agent twice.

- [ ] **Step 2: Run to verify they fail**

Expected: the chunked assertions fail because `chunked` is hard-coded `False` today.

- [ ] **Step 3: Implement chunking**

Split by top-level directory when either threshold is exceeded, halving both when the selected set is `deep` — the halving follows from the set, per spec 4.6, so `--deep` and `--families deep` cannot diverge. A family runs in a module only when it has leads or hotspot-band files there.

- [ ] **Step 4: Generate the two goldens and read them**

Generate a chunked plan at the full thresholds and at the halved ones, from a synthetic tree large enough to trigger each. Read both and confirm the module split is by top-level directory, that no family appears in a module it has nothing to do in, and that every prompt path is distinct.

- [ ] **Step 5: Run the gate and commit**

```bash
python -m ruff check .
python -m mypy
python -m pytest -q
git add skills/tech-debt-scan
git commit -m "$(cat <<'EOF'
feat(tech-debt-scan): module chunking and the halved deep thresholds

A repository over chunking.max_files or max_loc splits by top-level
directory, and a family runs in a module only where it has leads or
hotspot-band files. The halving follows from the selected set being deep
rather than from the flag, so --deep and --families deep cannot diverge.

No fixture is large enough to trigger chunking, so the tests lower the
thresholds through config and pin a plan at both the full and halved
values -- the only evidence the halving takes effect.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: SKILL.md step 4 and the network notice

**Confidence: 94%.** The step list is machine-checked by `skill_check.py`, but the network notice's wording is not, and it is the part a user actually reads before data leaves their machine.

**Files:**
- Modify: `skills/tech-debt-scan/SKILL.md`, `docs/architecture.md`, `README.md`

- [ ] **Step 1: Read the real `--help` before writing anything**

```bash
python skills/tech-debt-scan/scripts/tools_probe.py --help
```

Every flag you document must appear there.

- [ ] **Step 2: Write step 4 exactly as spec section 5 gives it**

The network notice must state what osv-scanner sends — package names, versions, ecosystems and file hashes to OSV.dev — that the other first-cut tools are local-only, and how to stay offline via `tools.network: false`. Then the probe command, with `--no-tools` mapping to `--skip-all` and the file still written with every tool skipped.

Do not renumber the steps after 4; spec section 5 fixes the numbering across phases and phase 5 inserts step 11 into the same list.

- [ ] **Step 3: Update the two documents**

`docs/architecture.md` and `README.md` now describe a probe that is wired in. Remove any statement that `tool-signals.json` is read by nothing. State what the tier assignment means for a reader: an osv advisory can reach the top of a report without a verifier having read it, and which two producers are allowed to do that.

- [ ] **Step 4: Run the gate and commit**

```bash
python skills/tech-debt-scan/scripts/skill_check.py
python -m ruff check .
python -m mypy
python -m pytest -q
git add skills/tech-debt-scan/SKILL.md docs/architecture.md README.md
git commit -m "$(cat <<'EOF'
feat(tech-debt-scan): SKILL.md step 4 runs the probe

The network notice states what osv-scanner sends before anything leaves
the machine, that every other first-cut tool is local-only, and how
tools.network false stays offline. --no-tools maps to --skip-all, which
still writes the file with every tool skipped.

The documents no longer say tool-signals.json is read by nothing, and
they now state that an osv advisory can reach the top of a report with no
verifier having read it -- and which two producers may do that.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: the two-arm live run, the evaluation log, and the gate

**Confidence: 92%.** The only task that spends tokens, and the only one whose result cannot be predicted. Its risk is the temptation to explain away a tier that does not move; the steps make the raw numbers the deliverable.

**Files:**
- Modify: `docs/evaluation-log.md`
- Modify: any document the sweep finds stale

- [ ] **Step 1: Run both arms over all three fixtures**

With tools present, and again with `--no-tools`. Same model and settings as phase 2's runs, so the arms differ only in the probe. Record cost.

- [ ] **Step 2: Tabulate tier assignment between the arms**

Per fixture and per family: how many findings reached tier A, B and C in each arm, and which specific findings changed tier. The claim under test is that duplication, dead code and cycles reach A with tools and are capped without.

- [ ] **Step 3: Write the rows**

One row per arm in `docs/evaluation-log.md`, with a note that rows recorded before this phase are against a different corpus, since `web-ts` gained files.

**If a tier did not move, record that.** Phase 2's gate failed honestly and the log carries it; a claim that did not hold is a result, not a problem to be argued away. Say which claim failed and what the numbers were.

- [ ] **Step 4: Sweep the documentation**

Every command, flag, path, exit code and step count in `SKILL.md`, `README.md` and `docs/architecture.md` checked against the code at HEAD. `skill_check.py` covers only `python scripts/*.py` lines in SKILL.md; everything else is checked by hand.

- [ ] **Step 5: The full gate**

```bash
python -m ruff check .
python -m mypy
python skills/tech-debt-scan/scripts/skill_check.py
python -m pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add docs
git commit -m "$(cat <<'EOF'
docs(tech-debt-scan): the phase 4b live gate, both arms

Three fixtures run with tools present and with --no-tools, so the arms
differ only in the probe. The claim under test was that duplication, dead
code and cycles reach tier A with tool corroboration and are capped
without it; the rows record what actually happened.

Rows before this phase are against a different corpus, since web-ts
gained a clone pair.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Self-review

**Spec coverage.** Section 4.6's tool-signal reading and chunking: Tasks 1 and 8. Section 4.7's three routings, the corroboration token and the producer invariant: Tasks 2 and 3. Section 4.8's tier assignment and its negative half: Tasks 3 and 6. Section 4.5's duplication decision: Task 5. Section 5's step 4 and the network notice: Task 9. Section 11's gate: Tasks 6, 8, 9 and 10. The three parked items 4b absorbs: Task 4 (tier C reason) and Task 7 (osv source paths, dict keys). No 4b requirement is unassigned.

**Deliberately out of scope**, as phase 5: `baseline.py`, the `diff` anchor key, promote write-back, `accepted` expiry, step 11, the note agent joining the live harness, the duplicated fence rule, `heading_text`'s ordering, vulture's `--sort-by-size`, the deny-all golden edge.

**Placeholder scan.** One test in Task 4 Step 1 is given as a described shape rather than a body — the tier C rendering test — and the step says explicitly to write it out fully against the fixtures that file already uses. Every other step carries its code. Tasks 5, 6, 8 and 10 have steps whose output cannot be written in advance because it depends on real tool behaviour, a generated golden or a live run; each of those steps names exactly what to record instead.

**Type consistency.** `_tool_leads(docs, family) -> list[Lead]` and `Lead(kind, path, line, text, score=0.0)` match `plan_scan`'s existing dataclass. `corroborate_with_tools(candidates, signals) -> None` mutates in place, matching `_corroborate`'s existing style. `tool_candidates(signals, inventory, rule_findings) -> tuple[list[dict], list[dict]]` returns new candidates and the rule findings it mutated, so the caller can keep them distinct. `tier_reason` is a plain `str` on every finding, set in `apply_verdicts` and read in `design_writer` with a fallback. `KIND_CAPS["tool"]` uses the same `LEAD_CAP` constant as its three siblings.

**One thing the plan cannot settle in advance.** Task 5 depends on real jscpd detecting a pair we author. If it will not, at any run length, the fixture approach fails and the phase falls back to recording duplication as unmeasured — Task 5 Step 1 stops rather than lowering the threshold, and that decision comes back to the human.
