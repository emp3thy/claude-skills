# tech-debt-promote as a design entry point

Provenance: brainstormed 2026-09-10 after the first full v2 scan of `better-memory` (95 candidates, 19 tier A, 8 promoted). That run exposed the defect this design fixes: the bundles promote emits carry a rich `PBI.md` and a `PLAN.md` that is nothing but the finding's own acceptance criteria renumbered as steps. Acceptance criteria are assertions about a finished state; a plan is ordered work. No step in the pipeline ever authors one.

Fixed constraints, inherited from `2026-09-04-tech-debt-scan-v2-design.md`: Claude Code skill; SKILL.md orchestration with pinned commands, pinned output files and the exit-5 no-improvisation rule; pure Python 3.11+ with pyyaml as the only dependency, every script direct-path invocable as `python scripts/<name>.py`; read-only Agent subagents for LLM work; human review of `design.md` before promote; no live LLM in tests; Windows-safe argv; LF-only rendered output; ruff, mypy strict, pytest and `skill_check.py` in CI.

## 0. Guardrails for planning and implementation

- **(a) Handoffs are rendered and assumptions bucketed.** Every artefact handoff (this spec, the implementation plan) is rendered visually for review, with assumptions in three buckets: real concerns with decision and residual risk, verified safe with evidence, minor or accepted. Section 9 carries this spec's.
- **(b) Confidence per task.** Every plan task carries a confidence percentage; a task under 90 percent embeds its mitigation in the task text rather than deferring it.
- **(c) Documentation ships with code.** `docs/architecture.md`, the repository `README.md` and `skills/tech-debt-scan/SKILL.md` are updated in the same PR as the code they describe.
- **(d) Verify before commit.** Where a task says "follows existing pattern X", the implementer reads X's source before writing, at plan-write time rather than implementation time.
- **(e) No live LLM in tests.** Tests feed canned JSON to the scripts; the `live` pytest marker never runs in CI. The brainstorming handoff itself is therefore untested by construction — see section 9.
- **(f) One branch, one PR.** `feat/tech-debt-promote-brainstorm`, created before the first task.

## 1. Goal, non-goals, success criteria

**Goal.** Turn `/tech-debt-promote` from a packaging step into a design entry point. It selects one approved finding, materialises its evidence as a standalone document, and hands that to a brainstorming session that ends in a real implementation plan. Packaging work items for an autonomous executor is out of scope: ralph's own skills already do it, across repositories, and better.

**Success criteria.**

1. `/tech-debt-promote` with no approved findings stops and says so, changing nothing.
2. `promote.py --list-approved` emits a JSON array of the approved findings, most severe first, with no side effects.
3. `promote.py --select <slug>` writes `.tech-debt/evidence.md`, flips that finding to `promoted` in `design.md`, and records the decision in `baseline.json`, in that order. A failure at any step leaves the earlier steps' output in place and reports which step failed; the command is re-runnable, and a finding already `promoted` is selectable again so a failed baseline write can be retried.
4. `evidence.md` reproduces the finding's Proof, Evidence, Signals, Remediation and Acceptance criteria byte-for-byte as they appear in `design.md`.
5. A finding marked `promoted` still classifies `RESOLVED` on a later scan once its code is gone.
6. Nothing in the scan half of the pipeline changes: `/tech-debt-scan` produces a byte-identical `design.md` for the same inputs before and after this work.
7. `bundle_writer.py` and every reference to the PBI bundle format are gone from `skills/tech-debt-scan/`.

**Non-goals.** Emitting work items in any queue format. Filling `target_repo`. Executing the plan. Planning more than one finding per invocation. Fixing the ranking formula or the note agent's contract — the `### Remediation` prose stays as it is, and becomes an input to the brainstorm rather than a substitute for a plan. Any change to the scan.

## 2. Command contract

`/tech-debt-promote [design.md path]`, one finding per invocation.

| # | Step | Who |
|---|---|---|
| 1 | Parse `design.md` | `design_parser.parse_design`, unchanged |
| 2 | Record every finding's status into `baseline.json` | `baseline.record`, amended per section 4 |
| 3 | List the `status: approved` findings, most severe first | `promote.py --list-approved` |
| 4 | User chooses one | SKILL.md |
| 5 | Write `.tech-debt/evidence.md` | `promote.py --select <slug>` via `evidence_doc.py` |
| 6 | Flip that finding to `promoted` in `design.md` and in `baseline.json` | `promote.py --select <slug>` |
| 7 | Hand off to `superpowers:brainstorming`, seeded with `evidence.md` | SKILL.md |
| 8 | Brainstorm ends by invoking `superpowers:writing-plans` | SKILL.md |

Steps 1, 2, 3, 5 and 6 are deterministic Python with pinned outputs. Steps 4, 7 and 8 are conversational and live in SKILL.md, matching how every other LLM step in this skill is already structured: a script renders a file, an agent consumes it.

**Step 8 is unconditional.** Brainstorming classifies each request itself, and its *bounded* path deliberately ends at an in-chat design with no plan file. A tech-debt finding must yield a plan, so the classification informs the depth of the conversation but never whether `writing-plans` runs. The plan lands wherever `writing-plans` puts it in the scanned repository; that file is the deliverable, fed to ralph or worked manually.

**Status vocabulary.** `promoted` is redefined from "a bundle was emitted" to "selected for a design session". `STATUSES` stays at five values, so `design_parser`, the `design.md` vocabulary and the status tests do not churn. The redefinition is safe because `SUPPRESSING` is `frozenset({"rejected", "accepted"})` — `promoted` has never suppressed anything — and `RESOLVED` is computed structurally in `baseline.diff` as a baseline entry no current finding matched, independent of status. A promoted finding therefore still resolves when its code goes.

**Exit codes.** 0 success; 2 a parse or mark error; 6 the baseline write-back failed after `design.md` was already marked. Exit 4 (a bundle-write failure after at least one bundle was written) disappears with the roll-forward logic that produced it.

## 3. `evidence.md`

**Path** `.tech-debt/evidence.md` — one file, regenerated on each `--select`, inside the gitignored workdir. It is a generated seed for one brainstorm, never hand-edited; `design.md` remains the durable record.

**Renderer** a new `scripts/evidence_doc.py`, a pure function from (finding, matched open questions, matched looks-bad-but-fine entries) to a markdown string, with no filesystem access — the same shape `bundle_writer.py` had, and testable the same way.

**Structure**

```
# <title>

Repository: <inventory root>
Scan: <scan_date> (preset <preset>)
Finding: <fingerprint> | <family> | <type_id> | <debt_type>
Tier <tier> | severity <n> | effort <S|M|L> | <diff>

### Proof
### Evidence
### Signals
### Remediation
### Acceptance criteria
### Open questions from the scan      (omitted when none match)
### Already ruled out                 (omitted when none match)
```

Everything from `### Proof` through `### Acceptance criteria` is copied verbatim out of the finding's `body_md`. No re-summarising: what the verifier confirmed is what the brainstorm reads.

The `Repository:` line comes from `inventory.json`'s `root`. It is carried explicitly because the session running promote need not be inside the scanned repository — the 2026-09-09 run invoked every command from `C:\Users\gethi\source` and from the skill directory, never from `better-memory`.

**The two matched sections.** `open_questions` and `looks_bad_but_fine` are anchored to `file` and `line_start`, not to a fingerprint: scouts emit them under that schema (`prompts/scout-*.md`), `merge_findings.py:866` collects them, `design_writer.py:953` renders them. Matching them to a finding is therefore a heuristic, and is specified as such:

- an entry matches when its `file` equals any file in the finding's evidence list
- matched entries are ordered by absolute distance from the finding's first evidence `line_start`
- neither section is capped; a file with many entries yields many
- when nothing matches, the heading is omitted entirely rather than rendered empty

`### Open questions from the scan` carries a fixed lead line — "Ask these before proposing approaches" — because these are the questions the code could not settle, and they are frequently the exact decision the brainstorm needs. `### Already ruled out` exists so the brainstorm does not propose something a scout examined and dismissed with a stated reason.

**Excluded:** `Not assessed`, `Considered and rejected`, the hotspot and coupling preamble, and every other finding. Repository-wide context the brainstorm reads for itself.

## 4. Baseline changes

`baseline.record` today refuses to record a `promoted` decision unless a bundle directory is supplied or was previously recorded — "only `promote` can vouch for a bundle". With bundles gone, that guard raises on the first selection. Three changes:

1. `record()` loses its `bundles` parameter and the vouching guard.
2. The entry schema loses its `bundle` field.
3. The reader ignores a `bundle` field on entries written by the current version rather than rejecting them, so a baseline already committed — `better-memory`'s carries eight — keeps working. No migration script.

Everything else in `baseline.py` is unchanged, and the semantics that make repeat invocations safe are already correct: `record` is a full re-sync keyed by fingerprint, not an append. Each run rewrites every entry from the parsed `design.md` plus `verified.json`; findings with no decision are written `pending` dated today so they read `UNCHANGED` next scan; entries from earlier scans that this scan did not find are kept, which is how a `rejected` decision survives; an entry whose code was edited migrates to the finding's new fingerprint; the write is atomic. Eight successive invocations therefore produce the same 95 entries with one more `promoted` each time, and any status edited by hand in `design.md` between runs is picked up without special handling.

The `.gitignore` triple stays: `baseline.json` must remain tracked while the rest of `.tech-debt/` is not.

## 5. Code inventory

**Deleted**

| Path | Size | Why |
|---|---|---|
| `scripts/bundle_writer.py` | 271 lines | the only PBI/PLAN/HISTORY author |
| `tests/test_bundle_writer.py` | 226 lines | its tests |
| `tests/golden/bundle/`, `tests/golden/bundle-v2/` | golden trees | golden bundle output |

**Rewritten — `scripts/promote.py`** (362 lines, the majority bundle orchestration: `_existing_bundle_dir`, the roll-forward path, the emitted and already-promoted counters). New CLI surface:

- `--list-approved` — JSON array on stdout: `slug`, `title`, `family`, `severity`, `effort`, `primary_file`, `fingerprint`; sorted by severity descending then priority descending; no side effects
- `--select <slug>` — writes `evidence.md`, marks `design.md`, records the baseline. Accepts a slug whose status is `approved` or already `promoted` (the latter so a failed baseline write, or a second design session on the same finding, can be re-run); any other status, or an unknown slug, is exit 2. `--list-approved` still lists only `approved` findings, so a re-run is deliberate rather than offered.
- `--baseline <path>` retained; `--out` and `--force` removed

**New — `scripts/evidence_doc.py`** per section 3.

**Amended — `scripts/baseline.py`** per section 4 (12 bundle references today).

**Amended — docstrings and prose only:** `scripts/design_writer.py` (4 references), `scripts/slugs.py` (1 reference), `skills/tech-debt-scan/SKILL.md` (the whole "Promote steps" section plus the bundle sentences in Conventions and Caveats), `docs/architecture.md`.

**Untouched:** the entire scan half — `inventory`, `patterns`, `rules`, `tools_probe`, `plan_scan`, `merge_findings`, `verify_prompts`, `apply_verdicts`, `rank`, `baseline diff`, `design_writer`'s rendering. Success criterion 6 asserts this.

## 6. Tests

**New — `tests/test_evidence_doc.py`**: every header field present and correct; body sections copied byte-for-byte from a fixture finding; open questions matched by file and ordered by line proximity; looks-bad-but-fine matched the same way; both sections omitted when nothing matches; a finding whose evidence carries several files matches against all of them.

**Rewritten — `tests/test_promote.py`** (438 lines, all bundle-shaped): `--list-approved` JSON shape, ordering and empty case; `--select` writes all three effects; unknown slug and non-approved slug both exit 2; baseline write-back failure is exit 6 with `design.md` already marked.

**Amended — `tests/test_baseline.py`** (1352 lines). The largest risk in this change: bundle vouching runs through much of it. Every test asserting the vouching guard, the `bundles` parameter or the `bundle` field is either deleted or restated, and one new test asserts a legacy entry carrying `bundle` still reads.

**Amended — `tests/test_e2e.py`, `tests/test_chain_goldens.py`**: the chain currently terminates in bundle output; it terminates at `evidence.md` instead.

**Amended — `tests/test_skill_check.py`** if `skill_check.py` asserts on the promote section's structure; verify before writing the task.

## 7. Build order

1. `evidence_doc.py` and its tests — pure, no dependencies on the rest of the change.
2. `baseline.record` amendment and its test surgery — independent of promote.
3. `promote.py` rewrite and its tests — depends on 1 and 2.
4. Chain and e2e test updates — depends on 3.
5. `SKILL.md`, `docs/architecture.md`, `README.md` — depends on 3, and per guardrail (c) ships in the same PR.

## 8. Migration and compatibility

A `design.md` from any earlier scan still parses: the change touches no anchor key. A `baseline.json` from an earlier promote still reads, its `bundle` fields ignored. The 13 bundle directories under `better-memory/tech-debt-pbis/` become orphans of a format nothing generates; deleting them is the user's call and needs no code.

There is no compatibility shim for the bundle format itself. Nothing outside this repository reads it, and ralph's own skills own that responsibility now.

## 9. Assumptions

**Real concerns**

1. **The brainstorming handoff cannot be tested.** Guardrail (e) forbids a live LLM in tests, so steps 4, 7 and 8 have no automated coverage — only `evidence.md`'s content is testable. *Decision:* accept, and keep the untested surface as thin as possible by putting every decision that can be deterministic into Python. *Residual risk:* a SKILL.md instruction can rot without CI noticing, exactly as the scan's step numbering could.
2. **Question matching is a heuristic and will sometimes mislead.** Open questions carry `file` and `line_start` only, so a busy file yields questions belonging to other findings. *Decision:* match by file, order by line proximity, and label the section as coming from the scan rather than as belonging to this finding. *Residual risk:* a brainstorm opens by asking something adjacent. Cheap to skip, and the alternative — dropping the section — loses questions that are frequently the decisive ones.
3. **`test_baseline.py` is 1352 lines and bundle vouching is woven through it.** *Decision:* task 2 in the build order does that surgery alone, before promote is touched, so a regression there is isolated from the rewrite. *Residual risk:* the amendment is larger than the feature.

**Verified safe**

- `promoted` never suppressed: `SUPPRESSING = frozenset({"rejected", "accepted"})`, `baseline.py:44`.
- `RESOLVED` is status-independent: computed in `diff` as a baseline entry no current finding matched, per the module docstring.
- `record` is a full re-sync, not an append: its docstring states entries absent from this scan are kept and every finding with no decision is written `pending`.
- Open questions are genuine scan output, not promote-time invention: emitted under `"open_questions": [{"file": "", "line_start": 0, "question": ""}]` in every scout prompt, collected at `merge_findings.py:866`, rendered at `design_writer.py:953`.
- Reusing `promoted` avoids touching `STATUSES`, the parser's validation and the status tests.

**Minor or accepted**

- `evidence.md` is overwritten each run; the content is always re-derivable from `design.md`.
- One finding per invocation is deliberate, for fresh context per design session.
- Orphan bundle directories are left in place.
- `target_repo` is not filled, because bundles no longer exist to carry it.
