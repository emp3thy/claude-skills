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
exists — is what returns the golden tree to zero.

**The three `2026-09-06` rows are the phase 2 gate**: one fresh run per fixture into
its own workdir, scored exactly as it came out. No hand edits, and nothing from these
runs was copied into the golden tree.

| date | fixture | model | churn_months | tier_a_precision | reported_precision | decoys_tier_a | decoys_top_n | recall | scouts | verifiers | cost_usd |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-09-05 | service-py | sonnet | 240 | 0.59 | 0.48 | 0 | 0 | dead-code=0.00 dependency-debt=1.00 doc-drift=1.00 error-masking=1.00 half-finished=1.00 ownership=1.00 pipeline-infra=1.00 security=0.80 test-gaps=1.00 test-quality=1.00 | 14 | 5 | 3.11 |
| 2026-09-05 | web-ts | sonnet | 240 | 0.31 | 0.27 | 0 | 0 | architecture=0.00 dead-code=0.00 dependency-debt=1.00 duplication=0.00 error-masking=1.00 half-finished=0.50 migration=1.00 pipeline-infra=1.00 | 13 | 4 | 2.49 |
| 2026-09-05 | mixed-decoys | sonnet | 240 | 0.50 | 0.41 | 0 | 0 | dead-code=0.00 error-masking=0.00 half-finished=0.50 pipeline-infra=1.00 security=0.40 test-quality=1.00 | 14 | 5 | 3.17 |
| 2026-09-05 | web-ts | sonnet | 240 | 0.25 | 0.19 | 1 | 1 | architecture=0.00 dead-code=0.00 dependency-debt=1.00 duplication=0.00 error-masking=0.00 half-finished=0.50 migration=1.00 pipeline-infra=1.00 | 13 | 5 | 2.47 |
| 2026-09-06 | service-py | sonnet | 240 | 0.62 | 0.52 | 0 | 0 | dead-code=0.00 dependency-debt=1.00 doc-drift=1.00 error-masking=1.00 half-finished=1.00 ownership=1.00 pipeline-infra=1.00 security=0.40 test-gaps=1.00 test-quality=1.00 | 14 | 5 | 3.60 |
| 2026-09-06 | web-ts | sonnet | 240 | 0.30 | 0.28 | 0 | 1 | architecture=0.00 dead-code=0.00 dependency-debt=1.00 duplication=0.00 error-masking=0.00 half-finished=0.50 migration=1.00 pipeline-infra=1.00 | 13 | 5 | 2.88 |
| 2026-09-06 | mixed-decoys | sonnet | 240 | 0.73 | 0.46 | 0 | 0 | dead-code=0.00 error-masking=1.00 half-finished=1.00 pipeline-infra=1.00 security=0.40 test-quality=1.00 | 14 | 5 | 3.37 |
