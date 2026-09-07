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
diff against the five candidates predicted to move, and the one prediction
that did not hold as cleanly as expected (web-ts's clone-pair duplication
finding: found by the scout, corroborated by `tool:jscpd`, and still
downgraded to C by the verifier's own judgement that de-duplicating dead code
is moot) are in
`.superpowers/sdd/2026-09-07-tech-debt-scan-v2-phase-4b/task-10-report.md`.
Summary: three of the five predicted dead-code fingerprints reached tier A in
the tools arm and two of those three reappeared at tier C, capped, in the
no-tools arm with the identical fingerprint (the third was not raised by the
no-tools arm's scout at all — LLM run-to-run variability, not a tools
effect); two further dead-code candidates (not among the five, one on
`web-ts`'s `stock.ts`, matched by identical fingerprint across both arms)
showed the same clean C-to-A movement; `mixed-decoys` showed no dead-code or
duplication tool corroboration in either arm, exactly as predicted, because
no tool in the ten-tool registry produces a Go dead-code or duplication
signal. `web-ts` family-level `dead-code` **recall** stayed `0.00` in both
arms regardless — the officially planted dead-code items are not the files
any candidate above moved on — recorded as a claim that did not hold when
read that way, alongside the candidate-level claim that did.

| date | fixture | model | churn_months | tier_a_precision | reported_precision | decoys_tier_a | decoys_top_n | recall | scouts | verifiers | cost_usd |
|---|---|---|---|---|---|---|---|---|---|---|---|
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
