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
