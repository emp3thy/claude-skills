# tech-debt-scan evaluation log

One row per live run of `scripts/live_run.py` over a corpus fixture (spec section 6). Tier A
precision is measured against the provisional 0.80 bar (reported at v2.0, hard at v2.1); zero
decoys at tier A or in the top N is hard from v2.0. Recall is reported without a bar.

| date | fixture | model | tier_a_precision | decoys_tier_a | decoys_top_n | recall | scouts | verifiers | cost_usd |
|---|---|---|---|---|---|---|---|---|---|
