# tech-debt-scan evaluation log

One row per live run of `scripts/live_run.py` over a corpus fixture (spec section 6). Tier A
precision is measured against the provisional 0.80 bar (reported at v2.0, hard at v2.1); zero
decoys at tier A or in the top N is hard from v2.0. Recall is reported without a bar.

`churn_months` is the git-history window the scan actually ran with: the fixture's
`planted.json` `churn_months` when present, else `--churn-months`, else the config
default; a `--churn-months` that disagrees with the fixture is ignored (with a
warning to stderr) so this column always matches the table the run was scored
against.

`tier_a_precision` counts tier A findings alone, which is the figure the bar names.
`reported_precision` is the same ratio over tiers A and B together (the per-family
`reported`/`precise` counts `evaluate.py` publishes); it is reported without a bar.

Rows are appended, never edited, so a fixture can appear more than once. **The
goldens under `skills/tech-debt-scan/tests/golden/` come from the four `2026-09-05`
rows** — for `web-ts`, the second of them (5 verifier batches, $2.47) supersedes the
first. Every row is the raw run, scored before the two hand edits the phase 2 plan
requires (an invented-quote pin and a trap `reject`), so a row can disagree with the
golden tree: the second `web-ts` run put decoy `d2` at tier A and in the top 5 on its
own, and the plan's trap reject — which lands on a decoy-path candidate when one
exists — is what returns the golden tree to zero. Golden regeneration is the
third reason a row can disagree with the tree: after a scoring or ranking change
the deterministic goldens are rebuilt with `UPDATE_GOLDENS=1` (candidates,
`verify-plan`, `verified` and `ranked`; the scouts and verdicts are never
regenerated), so the tree moves on while the rows that produced it do not.

**The three `2026-09-06` rows are the phase 2 gate**: one fresh run per fixture into
its own workdir, scored exactly as it came out. No hand edits, and nothing from these
runs was copied into the golden tree.

`decoys_top_n 1` on the `2026-09-06` `web-ts` row is decoy `d1`,
`.github/workflows/ci.yml`, planted to prove that no CI rule fires on a workflow
that already has pinned SHAs, a timeout, `permissions`, a cache and a retry
action. The hit is a confirmed tier-B scout finding that the workflow runs
`npm test` with no dependency install step, which is true of the fixture as
written — there is no `npm ci` in it — so the scan is right and the decoy is
mis-authored. `evaluate.hits` matches a finding to a decoy on family and path
alone when the decoy carries no `lines`, so any `pipeline-infra` finding on that
file counts as a decoy hit. Both ends are phase 5 work: an install step in the
fixture, and an explicit per-decoy `sources` list that `evaluate.hits` honours so
a decoy absorbs only the finding it was planted against.

`dead-code=0.00` on every row **through the `2026-09-06` gate** is structural
on this corpus, not a verifier failure. Spec 2.3 caps a dead-code finding at
tier C unless churn and fan-in are both zero on an ordinary source module;
every fixture file was committed inside the 240-month scoring window, so no
fixture file has churn 0, and recall counts the reported tiers A and B only.
No planted dead-code item can be recalled here until a fixture carries a
zero-churn file, **or** — from phase 4b — until a `tool:` corroboration lifts
the cap without one; `apply_verdicts._family_cap_and_lift` uncaps dead-code
whenever `confirmed_by` carries a `tool:` token, independent of churn or
fan-in. The `2026-09-07` service-py tools-arm row below is the first row in
this log where `dead-code` recall is not `0.00`.

**Rows recorded before phase 4b (`2026-09-05` and `2026-09-06`) are scored
against a different corpus than every row from `2026-09-07` on.** Task 5 of
phase 4b added a real clone pair to `web-ts` (`src/util/receipt.ts` and
`src/util/receipt-legacy.ts`, planted so `jscpd` finds it) and Task 8 added
per-module chunking; `web-ts` also gained the two tier-A ownership findings
Task 5's new files trip identically in both phase 4b arms. Comparing a
pre-phase-4b `web-ts` row's numbers directly against a `2026-09-07` row
conflates the corpus change with anything the probe did — the phase 4b gate
below compares its own two arms against each other for exactly this reason,
never against an earlier row.

**The six `2026-09-07` rows are the phase 4b two-arm live gate**: each of the
three fixtures run twice, once with `tools_probe.py` producing a real
`tool-signals.json` ("tools" arm) and once with `tools_probe.py --skip-all`
producing an all-`skipped` one ("no-tools" arm, the exact command
`--no-tools` runs) — the same replayed repository copy for both arms of a
fixture, so the two rows differ only in the probe. Total cost across all six
runs: $20.27. Full per-fixture, per-family tier tables, the fingerprint-level
diff against the five candidates predicted to move, and the two predictions
that did not hold as cleanly as expected — web-ts's clone-pair duplication
finding (found by the scout, corroborated by `tool:jscpd`, and still
downgraded to C by the verifier's own judgement that de-duplicating dead code
is moot) and web-ts's cart/pricing/stock import cycle (found by `madge`,
raised by the scout as an `architecture` candidate, corroborated via
`tool:madge`, and rejected outright by the verifier as an intra-package
design smell matching the family's own trap list) — are in
`.superpowers/sdd/2026-09-07-tech-debt-scan-v2-phase-4b/task-10-report.md`.
In both cases the tool corroborated the candidate before the verifier ever
ruled on it — a verifier decline, not a failure of tool corroboration to
occur. Summary: three of the five predicted dead-code fingerprints reached
tier A in the tools arm and two of those three reappeared at tier C, capped,
in the no-tools arm with the identical fingerprint (the third was not raised
by the no-tools arm's scout at all — LLM run-to-run variability, not a tools
effect); two further dead-code candidates (not among the five, one on
`web-ts`'s `stock.ts`, matched by identical fingerprint across both arms)
showed the same clean C-to-A movement; `mixed-decoys` showed no dead-code or
duplication tool corroboration in either arm, exactly as predicted, because
no tool in the ten-tool registry produces a Go dead-code or duplication
signal. `web-ts` family-level `dead-code` **recall** stayed `0.00` in both
arms regardless — the officially planted dead-code items are not the files
any candidate above moved on — recorded as a claim that did not hold when
read that way, alongside the candidate-level claim that did. Cycles
(`architecture`) never reached tier A in either arm: the tools arm's only
cycle candidate was the madge-corroborated one the verifier rejected above,
and the no-tools arm's scout did not raise the cycle as a candidate at all
this run, leaving nothing to compare a tier against there.

**Rows recorded before 2026-09-08 were scored without `sources` on the decoys
and without the `npm ci` step in web-ts's workflow.** From 2026-09-08 onward
every decoy carries a `sources` list that restricts which producers can hit it,
and the web-ts fixture installs dependencies before running tests, so the decoy
columns are not directly comparable with earlier rows on web-ts.

**From 2026-09-09 the harness renders the design document with the note agent's
notes and scores `findings.json`.** After ranking, `live_run.py` dispatches the
single remediation-note agent over the top N, renders `design.md` and
`findings.json` with `design_writer.write_design`, and scores `findings.json`
rather than `verified.json`. The trailing `notes` column is the count of top-N
findings the note agent actually filled in over the top-N size, e.g. `3/5`;
rows recorded before this date carry no `notes` column at all.

**The three `2026-09-09` rows are the phase 5b run over the repaired corpus**:
`sonnet`, `--churn-months 240`, the deep family set, top 5, tools present
(`live_run.py --tools`); the note agent rendered a real remediation note for
`5/5` top-N findings on every fixture; total cost $10.61. Tier A precision:
service-py 0.57 (12/21), web-ts 0.28 (5/18), mixed-decoys 0.50 (8/16). Decoys
at tier A: 0, 1, 0; in the top 5: 0, 0, 0. The tier-A decoy is web-ts's `d2`
(`error-masking`, `src/api/client-admin.ts` lines 8-17), hit by the producer
its `sources` names (`scout:error-masking`) and confirmed by the verifier on
the reading that a catch which logs the cause and returns `null` still leaves
callers unable to tell a failure from an empty body. `categories.py:171-176`
names four shapes under "failures caught and hidden, so nobody learns of
them" — empty catch blocks, catch-everything variants, log-only catches that
drop the cause, and disabled assertions. The decoy's `why` reads the site as
the third shape (this catch logs the cause,
`console.error("admin request failed", e)`); the verifier read the same site
as the second, a catch-everything variant that hides every failure behind a
`null` the caller cannot tell from an empty response. The rubric admits both
readings, and which one the corpus adopts is the first decision of the next
run. Per spec section 11's second outcome, no bar is set from this run: the
minimum the three rows would have given, 0.25 after rounding down, is recorded
as measured but not adopted, and the provisional 0.80 stays; whether `d2` stays
a decoy or becomes planted debt is the first decision of the next run, and
raising or setting the bar still requires a run that clears the hard gate. Two
more results worth noting: `dead-code` recall on service-py reached 1.00 for
the first time, the zero-churn repair (task 4) finally making the family
measurable; and web-ts's other decoy, `d1`, was hit at tier B by a
release-process finding (manual version bumps with no CI release job) that
cites the workflow as evidence — below the hard gate, so it is recorded as a
hit, not ruled on. The run's `evaluation.json`, `design.md`, `notes.json` and
`findings.json` for all three fixtures are kept under
`docs/research/tech-debt-scan-v2/runs/2026-09-09-5b/`.

**The 2026-09-12 goldens add the `performance` and `concerns` families to the
chain harness.** From this date `tests/test_chain_goldens._chain` and
`tests/test_e2e._scan` build `concern-index.json` (`concern_index.py`) and
copy each fixture's canned `tool-signals.json` into the workdir before
planning, neither of which the harness did before; several pre-existing
candidates gained `tool:` corroboration they had never exercised under test
and rose from tier B or C to tier A on `service-py` and `web-ts` as a result
— checked against source rather than taken on faith: `refund.issue_partial`
(TD-09, service-py) is flagged by vulture as an unused function at
`src/pay/refund.py:45`, the exact `def issue_partial` line already inside the
candidate's own evidence span, and `export_v1` (TD-30, service-py) is flagged
by vulture at `src/pay/legacy_export.py:8`, the exact `def export_v1` line
inside its evidence span. Both lifts are genuine same-symbol corroboration,
not same-file coincidence. Two
planted items land in the regenerated goldens per fixture: `service-py`'s
`p21` (`performance`, TD-36, a local loop smell) reaches tier A on a hotspot
lead, a `pattern:io-in-loop` corroboration, the scout, and `tool:ruff`;
`service-py`'s `p22` (`concerns`, TD-10) reaches tier B. `web-ts`'s `p11`
(`performance`) reaches only tier B — no TypeScript performance tool exists
in the ten-tool probe registry, so the B cap is structural rather than a
verifier decision — and `web-ts`'s `p12` (`concerns`) also reaches tier B.
Per-family precision for both new families is 1.00 with 1/1 recall on
`service-py` and `web-ts`; `mixed-decoys` carries no planted item for either
family. `decoys_in_tier_a` and `decoys_in_top_n` are both 0 on all three
fixtures. Overall tier A precision from the regenerated goldens: `service-py`
0.60 (12/20), `web-ts` 0.25 (3/12), `mixed-decoys` 0.70 (7/10) — these are
deterministic-golden figures from the replayed fixtures, not a `live_run.py`
row, so they are recorded here as prose rather than as a row in the table
below. A decoy sharing a file and family with a planted item now carries a
non-overlapping `lines` range in `planted.json`, because `evaluate.hits()`
otherwise matches an unranged decoy to any finding reported on that file,
including one that is really the planted hit. These deterministic-golden
figures satisfy spec success criterion 7's corpus half; the live tier-A
evaluation of `performance` and `concerns` the criterion also asks for is
deferred to the project's pending bar-setting live run, the same run the
tier-A bar (provisional at 0.80 since phase 5b) is still waiting on.

| date | fixture | model | churn_months | tier_a_precision | reported_precision | decoys_tier_a | decoys_top_n | recall | scouts | verifiers | cost_usd | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-09-05 | service-py | sonnet | 240 | 0.59 | 0.48 | 0 | 0 | dead-code=0.00 dependency-debt=1.00 doc-drift=1.00 error-masking=1.00 half-finished=1.00 ownership=1.00 pipeline-infra=1.00 security=0.80 test-gaps=1.00 test-quality=1.00 | 14 | 5 | 3.11 |
| 2026-09-05 | web-ts | sonnet | 240 | 0.31 | 0.27 | 0 | 0 | architecture=0.00 dead-code=0.00 dependency-debt=1.00 duplication=0.00 error-masking=1.00 half-finished=0.50 migration=1.00 pipeline-infra=1.00 | 13 | 4 | 2.49 |
| 2026-09-05 | mixed-decoys | sonnet | 240 | 0.50 | 0.41 | 0 | 0 | dead-code=0.00 error-masking=0.00 half-finished=0.50 pipeline-infra=1.00 security=0.40 test-quality=1.00 | 14 | 5 | 3.17 |
| 2026-09-05 | web-ts | sonnet | 240 | 0.25 | 0.19 | 1 | 1 | architecture=0.00 dead-code=0.00 dependency-debt=1.00 duplication=0.00 error-masking=0.00 half-finished=0.50 migration=1.00 pipeline-infra=1.00 | 13 | 5 | 2.47 |
| 2026-09-06 | service-py | sonnet | 240 | 0.62 | 0.52 | 0 | 0 | dead-code=0.00 dependency-debt=1.00 doc-drift=1.00 error-masking=1.00 half-finished=1.00 ownership=1.00 pipeline-infra=1.00 security=0.40 test-gaps=1.00 test-quality=1.00 | 14 | 5 | 3.60 |
| 2026-09-06 | web-ts | sonnet | 240 | 0.30 | 0.28 | 0 | 1 | architecture=0.00 dead-code=0.00 dependency-debt=1.00 duplication=0.00 error-masking=0.00 half-finished=0.50 migration=1.00 pipeline-infra=1.00 | 13 | 5 | 2.88 |
| 2026-09-06 | mixed-decoys | sonnet | 240 | 0.73 | 0.46 | 0 | 0 | dead-code=0.00 error-masking=1.00 half-finished=1.00 pipeline-infra=1.00 security=0.40 test-quality=1.00 | 14 | 5 | 3.37 |
| 2026-09-07 | service-py | sonnet | 240 | 0.61 | 0.48 | 0 | 0 | dead-code=1.00 dependency-debt=1.00 doc-drift=1.00 error-masking=1.00 half-finished=1.00 ownership=1.00 pipeline-infra=1.00 security=0.80 test-gaps=1.00 test-quality=1.00 | 14 | 5 | 3.54 |
| 2026-09-07 | service-py | sonnet | 240 | 0.67 | 0.57 | 0 | 0 | dead-code=0.00 dependency-debt=1.00 doc-drift=1.00 error-masking=1.00 half-finished=1.00 ownership=1.00 pipeline-infra=1.00 security=0.80 test-gaps=1.00 test-quality=1.00 | 14 | 5 | 3.31 |
| 2026-09-07 | web-ts | sonnet | 240 | 0.35 | 0.30 | 1 | 1 | architecture=0.00 dead-code=0.00 dependency-debt=1.00 duplication=1.00 error-masking=1.00 half-finished=1.00 migration=1.00 pipeline-infra=1.00 | 13 | 5 | 3.26 |
| 2026-09-07 | web-ts | sonnet | 240 | 0.43 | 0.30 | 0 | 0 | architecture=0.00 dead-code=0.00 dependency-debt=1.00 duplication=1.00 error-masking=1.00 half-finished=1.00 migration=1.00 pipeline-infra=1.00 | 13 | 5 | 3.46 |
| 2026-09-07 | mixed-decoys | sonnet | 240 | 0.53 | 0.43 | 1 | 0 | dead-code=0.00 error-masking=1.00 half-finished=1.00 pipeline-infra=1.00 security=0.40 test-quality=1.00 | 14 | 5 | 3.39 |
| 2026-09-07 | mixed-decoys | sonnet | 240 | 0.64 | 0.52 | 1 | 1 | dead-code=0.00 error-masking=0.00 half-finished=1.00 pipeline-infra=1.00 security=0.80 test-quality=1.00 | 14 | 5 | 3.31 |
| 2026-09-09 | service-py | sonnet | 240 | 0.57 | 0.50 | 0 | 0 | dead-code=1.00 dependency-debt=1.00 doc-drift=1.00 error-masking=1.00 half-finished=1.00 ownership=1.00 pipeline-infra=1.00 security=0.40 test-gaps=1.00 test-quality=1.00 | 14 | 5 | 3.43 | 5/5 |
| 2026-09-09 | web-ts | sonnet | 240 | 0.28 | 0.19 | 1 | 0 | architecture=0.00 dead-code=0.00 dependency-debt=1.00 duplication=0.00 error-masking=1.00 half-finished=0.50 migration=0.00 pipeline-infra=1.00 | 13 | 5 | 3.36 | 5/5 |
| 2026-09-09 | mixed-decoys | sonnet | 240 | 0.50 | 0.52 | 0 | 0 | dead-code=0.00 error-masking=1.00 half-finished=1.00 pipeline-infra=1.00 security=0.40 test-quality=1.00 | 14 | 5 | 3.82 | 5/5 |

## document-drift

One row per live run of `skills/document-drift/tests/dd_live_run.py` (spec 11.3), which runs the
skill's three stages with real `claude -p` agents on a corpus fixture (replayed into a temporary
directory) or on a repository (a throwaway clone: a run without `--check` commits there). The
harness appends the row below the header's table; it never edits this text or the header. A
row is never edited, with one exception: the owner fills in its `judged acceptable` cell.

- `mode`: `first`, `later` (since the last drift run), `base` (`--base`, or `--from`, which is
  passed as `--base`) or `full`, from `changes.json` `scope`. `docs` counts the docs in scope;
  `affected` the docs reviewed (every doc on a first or full run, the affected docs on a later
  one); `units` the review units.
- `edits proposed` is the total, then review / gap / notice; from phase C the total also counts
  the script edits (`cite`, `fact`), which have no figure of their own in the brackets (so
  `97 (83/4/5)` is 83 review, 4 gap, 5 notice and 5 script edits); `kept` the edits that passed the
  script checks; `verdicts` accept / reject / unsure / unverified; `applied` the edits applied
  (`0` under `--check`); `judged acceptable` the applied edits the repository's owner judged
  acceptable after reading the drift commits, as `n/m` of `applied` (spec 11.3): the harness
  writes `-`, and the owner replaces it after judging, the one permitted edit to a row; `human`
  the "Needs a human decision" entries; `notices placed` the applied 1st and 2nd notices; `gaps`
  undocumented / missing-from-list.
- `planted caught` and `decoys touched` (fixtures only): an item of the state's `planted.json`
  is caught when every expectation holds (`dd_corpus.evaluate`); a decoy (`kind` `decoy` or
  `excluded`) is touched when one does not. An item marked `canned_only` (it encodes a
  deliberate mistake of the canned agents, which a correct live agent never makes) is not
  scored and is named in `notes` as `canned-only: ...`. `notes` names each miss and touch; the
  run's task report explains them from the agents' outputs.
- `agents` counts the plan entries dispatched per role, review / gap / verify, and on a
  README-mode run (phase B) five figures, review / gap / verify / sheet / writer (a
  `retry.json` re-dispatch is in `notes`, not counted twice); `tokens` sums every call's input (cache reads
  and writes included) and output tokens as the reply envelope reports them; `cost usd` sums
  the envelopes' `total_cost_usd`. `wall time` covers the stages and agent waves, not the
  fixture replay.
- Phase B (a run on a repository with no root README) adds README figures, which the
  harness appends to the `notes` cell of a README-mode row as `areas <n>; sheets
  <valid>/<unchecked>; statements <proposed>/<accepted>/<rejected>/<unsure>/<unverified>;
  readme <n> lines` (rejected counts the statements the citation check pre-rejected; `readme`
  is the length of the README written, 0 when none was). The table header is unchanged.
- Phase C adds `cite <moved>/<checked>; facts <corrected>/<checked>; opened <n>` to the `notes`
  cell of every row the harness writes: citations rewritten of citations checked, fact rows
  corrected of rows checked (both from `script-edits.json`), and `n`, the `opened` entries
  summed over the review outputs, so the reading rule is measurable.

The phase 1 rows (`2026-10-09`, ralph and better-memory, from phase 1's deterministic
`dd_run.py`) were removed with that section's columns: phase A replaced the pipeline they
measured. They are in git history.

**The `2026-10-13` `py-service (state 1)` row is the first live run** (sonnet review and gap
agents, opus verifiers, $0.71). It was first logged as `6/11` and `1/8`, then re-scored from
the run's kept workdir (same files, no new agent call) once `canned_only` was added:
`p14` expects the verifier to reject the canned review's wrong `--workers` default
correction, and decoy `d7` expects the check to drop the canned review's bad `connect`
anchor; the live review made neither edit, so neither can be met by a correct agent. The
four misses are agent judgement: `p2`, the right `--worker` to
`--workers` fix, was proposed and the verifier answered `unsure` because `serve` never reads
`args.workers`; `p4`, the stale `store.delete` item, was rewritten to `store.list` (a
`correct`, not a `remove`) and the verifier rejected it because `store.list` is in
`undocumented_ok`; `p8a` and `p10`, the two `docs/design.md` lines that name nothing, came back
as an `unsure` question (nothing schedules `Store.purge`) and as no nomination at all. Both
rejected edits reached the human-decision list, so neither doc line was changed wrongly.

| date | repository | head | mode | docs | affected | units | edits proposed | kept | verdicts | applied | judged acceptable | human | notices placed | gaps | planted caught | decoys touched | agents | wall time | tokens | cost usd | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-13 | py-service (state 1) | 09c42c0 | first | 8 | 8 | 1 | 7 (4/3/0) | 7 | 5/1/1/0 | 5 | - | 9 | 0 | 2/1 | 6/10 | 0/7 | 1/2/4 | 1m08s | 422201 | 0.71 | missed p2, p4, p8a, p10; canned-only: p14, d7 |
| 2026-10-13 | better-memory | 9d5be26 | full | 38 | 38 | 2 | 29 (19/3/7) | 20 | 17/0/0/0 | 20 | - | 21 | 3 | 13/13 | - | - | 2/5/8 | 4m15s | 3597675 | 3.27 | run completed (2 commits on docs/drift-2026-10-13); the harness echo crashed afterwards on cp1252 stdout (fixed). u001 packed 27 linked docs at 10,757 lines against a 6,000 budget: the agent left 7 docs unreviewed and nominated them whole as unverified blocks; 3 whole-doc notices applied (read-spec, write-spec, synthesize-freeze), 4 refused by the never-edit heading check. 0 anchor edits proposed (A12) |
| 2026-10-13 | better-memory | 9d5be26 | full | 38 | 38 | 4 | 91 (87/3/1) | 64 | 53/10/0/0 | 54 | - | 45 | 1 | 13/13 | - | - | 4/5/18 | 4m58s | 11420625 | 8.96 | second run, same head, with the fixed unit packer (3 units within budget); the first pass crashed in retry_units (fixed) and was resumed at verify with 8 earlier calls; wall time from the resume; 1 retried |
| 2026-10-14 | py-cli-nodocs (state 1) | bdaa430 | first | 0 | 0 | 0 | 1 (0/0/0) | 1 | 0/0/0/0 | 1 | - | 3 | 0 | 8/0 | 9/9 | 0/3 | 0/0/8/4/1 | 2m33s | 734840 | 1.59 | 1 retried; canned-only: p9; areas 4; sheets 4/0; statements 41/38/3/0/0; readme 93 lines |
| 2026-10-14 | claude-skills | 8b4decb | first | 26 | 26 | 16 | 23 (18/3/2) | 18 | 13/3/0/0 | 14 | - | 15 | 2 | 18/0 | - | - | 16/2/9 | 8m42s | 13077972 | 7.72 | 2 retried |
| 2026-10-14 | py-cli-nodocs (state 1) | bdaa430 | first | 0 | 0 | 0 | 1 (0/0/0) | 1 | 0/0/0/0 | 1 | - | 5 | 0 | 8/0 | 9/9 | 0/3 | 0/0/7/4/1 | 2m05s | 645298 | 0.83 | models overridden: sonnet; 1 retried; canned-only: p9; areas 4; sheets 4/0; statements 43/38/5/0/0; readme 74 lines |
| 2026-10-14 | better-memory | 9d5be26 | full | 38 | 38 | 5 | 94 (92/2/0) | 58 | 51/7/0/0 | 51 | - | 51 | 0 | 13/13 | - | - | 5/5/15 | 11m44s | 9720085 | 8.89 | 2 retried |
| 2026-10-14 | better-memory | 9d5be26 | full | 38 | 38 | 5 | 97 (83/4/5) | 65 | 53/4/0/0 | 61 | - | 54 | 3 | 13/13 | - | - | 5/5/15 | 10m02s | 7999117 | 8.06 | 2 retried; cite 4/78; facts 1/73; opened 8 |
| 2026-10-14 | better-memory | 9d5be26 | full | 38 | 38 | 4 | 93 (81/3/4) | 69 | 50/11/0/0 | 58 | - | 52 | 3 | 13/13 | - | - | 4/5/15 | 8m24s | 8805028 | 7.37 | 1 retried; cite 4/78; facts 1/73; opened 29; final phase C code (inline blocks removed, hints split) |
| 2026-10-14 | claude-skills | 6600ae5 | full | 26 | 26 | 18 | 9 (5/4/0) | 5 | 4/1/0/0 | 4 | - | 14 | 0 | 18/0 | - | - | 18/2/5 | 6m43s | 10515272 | 6.85 | stopped: finish exited 5 (an add edit naming three flags matched no gap; fixed in fd3e69e); 4 retried; cite 0/26; facts 0/0; opened 64 |
| 2026-10-14 | claude-skills | fd3e69e | full | 26 | 26 | 17 | 9 (6/3/0) | 7 | 6/1/0/0 | 6 | - | 10 | 0 | 18/0 | - | - | 17/2/6 | 6m31s | 9059930 | 6.48 | 3 retried; cite 0/26; facts 0/0 (23 rows not in scan); opened 52; 2 commits on docs/drift-2026-10-14 |

**The `2026-10-14` `py-cli-nodocs (state 1)` row was re-scored** from the run's kept workdir
(same files, no new agent call): first logged as `1/3` decoys touched (`touched d2`), it is
`0/3`, since the `readme:absent` judge matched the decoy `migrate` in the span `Store.migrate`,
a false positive fixed in 88f12b1, and its README figures in `notes` were filled in from the
same workdir.

Anchor check (2026-10-13, not a full run): one review agent re-run on the second run's unit
u003, the unit holding better-memory's 11 docs with no anchor in their reviewed lines, with
the prompt that marks such docs (`no anchors in these lines`) and asks for an `anchor` edit or
an unverified block per code block there. 270 claims checked, 2 `correct` edits, 1 `unsure`,
0 anchor edits, 0 unverified blocks: the agent counted those docs (tech-debt PBIs and plans,
`CLAUDE.md`) as 0 code claims. A12 stays unvalidated (one Sonnet call, 1,442,094 tokens,
$0.76; a first attempt with the workdir under `~/.claude` cost $1.10 and wrote nothing, since
the agent refuses to write there).

**Phase C measurement (2026-10-14, better-memory `9d5be26`, `--full`, same `.document-drift.yaml`):** the three
better-memory rows above are the before run (the `main` code, phases A and B), the first after run
(the phase C branch with the reading ranges inlined in the review prompt) and the final after run
(the branch as merged: inline blocks removed under section 10's rule, the hints split into their own
prompt section). The columns below follow that order.

| | before | after (inline blocks) | after (final) |
|---|---|---|---|
| total | $8.89, 9.72M tokens, 11m44s | $8.06, 8.00M tokens, 10m02s | $7.37, 8.81M tokens, 8m24s |
| review | 5 calls (2 retries), $4.64, 7.31M tokens, 1.46M per call, 191 s per call | 5 calls (2 retries), $4.69, 5.84M tokens, 1.17M per call, 184 s per call | 4 calls (1 retry), $3.93, 6.56M tokens, 1.64M per call (2.15M per full call), 206 s per call |
| gap | 5 calls, $0.60, 0.49M | 5 calls, $0.50, 0.42M | 5 calls, $0.48, 0.44M |
| verify | 15 calls, $3.65, 1.92M | 15 calls, $2.86, 1.74M | 15 calls, $2.96, 1.81M |
| edits proposed | 94: 92 review, 2 gap, 0 notice | 97: 83 review, 4 gap, 5 notice, 5 script (4 cite, 1 fact) | 93: 81 review, 3 gap, 4 notice, 5 script (4 cite, 1 fact) |
| verdicts | 51 accept, 7 reject | 53 accept, 4 reject | 50 accept, 11 reject |
| notices placed | 0 | 3 (5 notice edits: 3 kept, 2 dropped as `overlap-script`) | 3 (4 notice edits: 3 kept, 1 dropped as `overlap-script`) |
| applied | 51 | 61, including the 5 script edits and the 3 notice edits | 58, including the 5 script edits and the 3 notice edits |

Review tokens per call fell 20% (1,462,013 to 1,167,157), against the acceptance target of a
halving: **the target was not met.** Cost per review call did not move ($4.64 to $4.69 over five
calls), the total fell 9% mostly in verify (15 calls, $3.65 to $2.86), and wall time per review call
fell 4%. Per spec section 10 the figure is recorded here and the decision (keep the inline blocks
for a 20% cut, or remove them and fall back to the prompt rule alone) is the owner's. The 20% is
confounded: the after run's review agents proposed 9 fewer edits (83 against 92) and left the 20
citation lines below untouched, both of which cut tokens on their own. Each figure is one run per
side with no repeat, so run-to-run variance of the agents is not separated from the change;
read the comparison as indicative.
**Ruling (2026-10-14):** the halving target was not met, so under section 10's rule the inline
code blocks were removed from the review prompts; the reading rule and `opened` stay.

**The final after run** (inline blocks removed, hints under their own heading) had the same three
large review units as the other two runs (5,836, 5,793 and 4,877 lines) and one small one (598
lines) where they had two. Per large unit the review tokens were 2.02M before, 1.69M with the inline
blocks and 2.15M in the final run: removing the blocks gave the 16% back and the wider reading
added 7% on top. Total review tokens were 6.56M against 7.31M before and 5.84M with the blocks,
the difference being the small units; the total cost fell 17% against the before run ($8.89 to
$7.37), mostly in the verify and small-unit calls, and the verifier rejected 11 of 61 (the before
run 7 of 58). Of the 20 citation lines
the inline-block run left untouched, **16 got a review agent's `correct` edit again** (13 applied,
3 rejected by the verifier: `agentcore-mapping.md` lines 39, 40 and 42) and 4 did not:
`agentcore-mapping.md:53` (a subject-less table cell, listed as `cite-unresolved`), lines 69 and 73
(protected lines the before run had sent to a human too) and `data-sources.md:167` (a guarantee,
also a human item before). So the split of the hints recovered the regression except for one line,
and the script's own 5 edits (4 `cite`, 1 `fact`) were the same five. The agents opened 29 files
(22 distinct) over 3 full calls, against 8 in the inline-block run: `ui/app.py` and
`setup/manifest.py` three times each, `mcp/tools.py`, `config.py` and
`mcp/handlers/reflections.py` twice, the rest once, every entry with a one-line `why`; with no
inlined ranges the reading rule is what limits the reading, and the agents read more files than
the inlined ranges had covered at a 7% token cost per large unit over the before run.

**The run on this repository** (phase C code at `fd3e69e`, `--full`, the two `claude-skills` rows
above): the first attempt stopped in the commit step after the corrections commit, because the gap
agent had put three flags that belong together in one `add` edit, as its prompt asks, and the
commit step matched the whole subject (`--tested, --passing, --failing`) against one gap name;
`gap_kind` now takes the first listed name that is a gap. The repeated run made two commits on
`docs/drift-2026-10-14`: 6 corrections in `docs/architecture.md` (tech-debt-scan tiers, caps, the
category and debt-type lists, where `findings.json` is written) and the three-flag addition in
`skills/karate-bootstrap/SKILL.md`, with 10 human items (5 `no-home` names in test fixtures and
scripts, 3 `unsure`, 1 `verify-rejected`, 1 `target-refused`). The script found nothing to rewrite:
all 26 citations are unresolved (23 of them in this log, citing better-memory files that are not
in this repository; the other 3 in the agent prompts, illustrative), and the 23 table rows the
fact checker read are a YAML-key table in `skills/document-drift/SKILL.md` and an agent-count table
in `skills/tech-debt-scan/SKILL.md`, neither of which the scan knows: 23 `not in scan` hints, no
edit, as designed. Against the phase A run of the same docs ($7.72, 23 edits proposed, 14 applied,
8m42s), this run cost $6.48 for 9 proposed and 6 applied in 6m31s; the docs had been corrected
by that run already, so the two are not a like-for-like measure.

The after run's agents opened 8 files over the 5 review calls (`opened` in `review/u00N.json`),
all by the `opened` rule and none refused: `ui/app.py` three times (u001, u002, u004: route and
`create_app` bodies the inline ranges did not cover, for claims that the UI never builds a backend
and which routes use it), `mcp/tools.py` once (u003: the `required` list of the `memory.retrieve`
schema, to settle a scan row against a doc that marks `query` optional), `storage/agentcore.py`
once (u005: which backend methods exist, for new-method names in a spec), `storage/session.py`,
`ui/queries.py` and `setup/manifest.py` once each (u001, u002: a function the claim names but the
changed ranges did not include). So three classes: a body outside the inlined ranges (6), a
schema the scan row contradicted (1), existence of a named method (1).

The script made 5 edits, committed as `docs(drift): correct citations and facts` on
`docs/drift-2026-10-14` (citations 78 checked, 6 current, 4 moved, 7 ambiguous, 16 use sites, 45
unresolved; fact rows 73 checked, 1 corrected, 4 not in scan; 2 agent edits dropped as
`overlap-script`):
`docs/agentcore-ui/data-sources.md:139` `SemanticMemoryService.list_for_project`
`services/semantic.py:220` to `:239`; `docs/agentcore-ui/write-spec.md:63` `list_session_exposures`
`protocol.py:262` to `:380`; `chore-agentcore-backend-error-path-tests` `PBI.md:23` `observe`
`agentcore.py:89` to `:238`; `chore-ui-app-factory-god-module` `PBI.md:23` `create_app`
`app.py:22` to `:45`; `website/mcp-tools.md:60` fact `outcome` Required `yes` to `no`
(`mcp/tools.py:257`). Each of the four rewrites targets the first line of the subject's current
span in `defindex.json` (`semantic.py:239-358`, `protocol.py:380-397`, `agentcore.py:238-301`,
`app.py:45-817`): 4 rewrites, 0 wrong.

Against the before run: its agents proposed 50 edits whose `old` held a `path:line` citation
(`edits.json`, source review or gap); 28 of them were kept by the checks and 25 were accepted
and applied (3 rejected; of the other 22, 16 went to a human, 14 of them as `protected`, and 6
were dropped as `new-reference`). Compared by document and line in the after run, 2 became script
edits (`write-spec.md:63`, which the before agent also moved `262` to `380`, and
`data-sources.md:139`, which the before checks had dropped as `new-reference`), 23 were again
made by a review agent (11 kept and applied, 12 left to a human as in the before run), 5 were
again dropped by the checks, and **20 got no edit at all**: `agentcore-mapping.md` lines 33,
35-37, 39-44 and 53 (11 lines), 69 and 73, and `data-sources.md` lines 127-132 and 167
(recounted from `live-bm-before/edits.json` against `live-bm-after/`). 14 of the 20 had been
applied in the before run. Of the 20, the script listed 12 as `cite-unresolved` (subject-less
table cells and a bare `agentcore.py:N` the nearest-name rule cannot place) and 5 as
`cite-use-site`; 3 carry no hint (`agentcore-mapping.md:69` and `:73` sit in protected lines,
which the before run had sent to a human, and `data-sources.md:167` was a guarantee the before
run had sent to a human too). The agents saw the 17 hints under "Already settled by script" and
treated those lines as off limits. So the spec's expectation that every citation the agent fixed
before is a `cite` edit after, or a listed hint, holds only for the hint half: 17 of 50 were hints
and unfixed. Fixed after the measurement: the review prompt now lists the hints under their own
heading, `## Not settled by script: these need you`, as the agent's work, and only the `cite` and
`fact` edits as settled. The 2 `overlap-script` drops were two whole-line `notice` placements
(`notices.json`, for blocks an agent nominated as unverified), not agent corrections, on the two
PBI.md lines the script rewrote (`agentcore.py:89` and `app.py:22`): the script edit won, which
is the net C5 relies on.
