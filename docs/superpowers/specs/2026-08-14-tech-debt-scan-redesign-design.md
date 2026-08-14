# tech-debt-scan Redesign — Waves 1-5 Design

**Date:** 2026-08-14
**Skill:** `claude-skills/skills/tech-debt-scan`
**Scope:** Waves 1-5. Waves 6-7 (persistent register, dedup, trend) are a separate later spec.
**Source:** Three research reports (`C:\dev\.tech-debt-research\01-measuring.md`, `02-detecting.md`, `03-managing.md`) plus two eval agents (consensus + fit-to-scanner). Design approved by user 2026-08-14.

## Problem

The current scanner detects debt via 6 LLM scouts and ranks the top-5 by bare scout severity (`impact × tractability` gut-feel). Research and eval surfaced concrete gaps:

- **Ranking is gameable and non-reproducible.** Bare severity 1-5 varies run-to-run and has no objective anchor. Best-practice frameworks (RICE/WSJF, hotspot) weight by confidence, change-size, and change-frequency.
- **The single strongest missing signal is the git hotspot** (complexity × change-frequency). Language-agnostic, cheap, absent today. `mtime` is captured but unused.
- **No cheap deterministic pre-passes** (SATD regex, import-count) route scout attention or add reproducibility.
- **The 8-category debt taxonomy has an infrastructure gap** — no scout reads dependency manifests for ancient/EOL versions.
- **Findings carry no size/risk profile.** Bare severity 1-5 tells neither the human dispatcher nor the autonomous coder how big or how dangerous the remediation is. (Time/dollar quantification — hours, TDR — is deliberately excluded: the consumer is ralph via a human's dispatch decision, not a capacity planner.)
- **Promoted PBI bundles lack the fields an autonomous ralph agent needs** — why-now, scope-boundary, acceptance-criteria, change-size, change-risk.

## Invariants (hard constraints, unchanged)

1. **Language-agnostic** — no per-language AST parser. LLM structural reading plus git/text pre-passes only.
2. **Git-optional** — hotspot/churn degrade gracefully when `.git` is absent (skip the signal, never abort).
3. **Bounded tokens** — ~60-80k per scan. Pre-passes route attention; they must not inflate the token budget.
4. **No-improvisation abort** — the SKILL.md exit-5 contract is preserved.
5. **Top-5 cap + bounded PBIs** — anti-noise and anti-rewrite. Both retained.

## Design — Five Dependency-Ordered Waves

### Wave 1 — Prompt calibration + three new real schema fields

Files: `categories.py`, `build_synthesis_prompt.py`, `validation.py`.

**Prompt-only calibration (no schema change):**
- **Duplication scout** — Rule of Three: 2 copies ⇒ severity ≤ 2; 3+ occurrences ⇒ actionable. Calibrates the most gameable scout.
- **God-modules scout** — name the underlying metric intent (WMC / CBO / LCOM — size, coupling, cohesion) so severity tiers are calibrated, not gut-feel.
- **Synthesis prompt** — RICE/WSJF framing: rank by Impact (severity) × Confidence / change_size rather than bare severity.
- **ISO 25010 tag + Fowler quadrant** — fold as label hints into the existing `reasoning` prose. NOT new fields (avoids cascade bloat).

**Four new REAL schema fields** on each top5 item (per locked decision "real schema fields"):
- `confidence` — integer 1-5, evidence strength. Penalizes speculation; counters gameable severity.
- `change_size` — enum `S | M | L | XL`. Scope/complexity of the remediation diff (files touched, conceptual difficulty). Explicitly **not** a time estimate — the scanner proposes findings for a human to hand to an autonomous coder (ralph), so wall-clock hours are meaningless. Still serves as the RICE/WSJF denominator (oversized ⇒ split).
- `change_risk` — enum `low | med | high`. Likelihood the remediation itself breaks behavior (blast radius of the fix). **Informational only** — the scanner proposes; a human decides whether/how to act on each finding. It does NOT gate the pipeline or couple to disposition. Note: risk-of-*not*-fixing (the debt's interest) is already carried by `severity` + the why-now/hotspot signal, so this field is fix-risk only, no double-count.
- `disposition` — enum `full-repayment | debt-conversion | interest-only`. Not everything is a rewrite. Set by scout judgment, independent of `change_risk`.

`validation.py` gains `validate_change_size`, `validate_change_risk`, and `validate_disposition` (frozenset enums, same shape as `validate_status`).

### Wave 2 — Inventory pre-passes

File: `inventory.py`.

`FileEntry` gains two deterministic, language-agnostic fields:
- **`satd_count`** — count of `TODO | FIXME | HACK | XXX | WORKAROUND | KLUDGE` matches per file (case-sensitive regex on file text). ~0.89 F1 for SATD-or-not. Zero extra data; routes scout attention.
- **`import_count`** — count of import-like lines (`import` / `using` / `require` / `include` / `use`) as an efferent-coupling (Ce) proxy. Pure text.

`mtime` is retained (weak recency); the Wave 5 hotspot supersedes it when git is present.

Counting must follow the existing platform-safe LOC discipline: iterate the opened file, never `read_text` (avoids Windows CRLF translation).

### Wave 3 — Infrastructure-debt scout (7th category)

File: `categories.py`.

- New `infrastructure-debt` category prompt: read dependency manifests (`package.json`, `pom.xml`, `requirements.txt`, `go.mod`, `*.csproj`, `Cargo.toml`) as **pure text** and flag obviously-ancient pinned versions and EOL runtimes. **No network, no CVE database** — purely what is visible in the manifest text.
- `CATEGORIES` tuple gains `infrastructure-debt`. This cascades automatically to the synthesis category check (`validate_synthesis_output` validates `category in CATEGORIES`).
- Closes the infrastructure gap in the 8-category taxonomy.

### Wave 4 — Change profile + richer PBI bundle

Files: `design_writer.py`, `bundle_writer.py`.

No hours, no TDR. The scanner feeds an autonomous coder (ralph) via a human's dispatch decision, so wall-clock time estimates and stakeholder dollar-framing (TDR) are meaningless here. Quantification is expressed as the `change_size` + `change_risk` profile instead.

- **`design_writer.py`** — render each finding's `change_size` + `change_risk` profile (and `disposition`) in design.md. Add the new `confidence`/`change_size`/`change_risk`/`disposition` keys to the per-finding yaml anchor in `_render_finding`.
- **`bundle_writer.py`** — `_render_pbi` gains the missing good-ticket fields:
  - **why-now** — the CoD/hotspot signal (e.g. "high-churn hotspot" when git present).
  - **scope-boundary** — what is explicitly OUT of the ticket.
  - **acceptance-criteria** — a verifiable done-signal for the agent.
  - **change_size** — carried from the schema field (scope, not time).
  - **change_risk** — carried from the schema field (informational; helps the human decide whether to hand it to ralph).

  These come from the finding body/anchor; the promote orchestrator passes them through. They directly raise ralph autonomous-agent success.

### Wave 5 — Git-gated hotspot ranking

Files: `inventory.py`, `build_synthesis_prompt.py`.

- **`inventory.py`** — when `.git` is present at the scan root, run `git log --numstat` (or equivalent commit-touch tally) to compute **`git_churn`** per file (number of commits touching the file). When git is absent, the field is omitted/null — no abort.
- **`build_synthesis_prompt.py`** — synthesis sort key becomes **`severity × log1p(churn)`** (locked formula) when churn is available; falls back to severity-only when churn is null. Replaces gut-feel ranking with a reproducible hotspot signal. The `MAX_FINDINGS=30` cap and `TOP5_COUNT=5` are unchanged.

## Schema Cascade

The four new fields (`confidence`, `change_size`, `change_risk`, `disposition`) touch exactly five files, in order:

1. `build_synthesis_prompt.py` — extend `_REQUIRED_ITEM_FIELDS`, `_OUTPUT_SCHEMA`, and `validate_synthesis_output` (type + enum checks).
2. `design_writer.py` — emit the four keys in the `_render_finding` yaml anchor.
3. `design_parser.py` — extend `REQUIRED_KEYS` so the round-trip parse enforces them.
4. `bundle_writer.py` — surface `change_size`, `change_risk`, and `disposition` into PBI frontmatter/body.
5. `validation.py` — add `validate_change_size`, `validate_change_risk`, and `validate_disposition` enums.

Each edit is small; the chain is the work. The `design_writer` round-trip self-check (it re-parses its own output) will catch any anchor/parser drift at write time.

## Explicitly Deferred (Waves 6-7 — separate later spec)

- Persistent results register (JSON per run).
- Finding fingerprint + dedup across runs (stops duplicate PBIs each scan).
- Auto-age / auto-close of fixed findings (re-scan diff).
- Trend output ("module worsened since last scan").

## Rejected (from eval consensus)

- **True AST metrics** (cyclomatic/cognitive exact) — violates language-agnostic invariant; LLM ordinal estimate suffices.
- **jscpd / PMD-CPD hard dependency** — external tool dep; LLM Type-4 clone detection is the differentiator.
- **Change-coupling / temporal-coupling matrix** — cross-file, token-heavy; deferred beyond even Waves 6-7.
- **CVE / vulnerable-dependency lookup** — requires network + CVE DB; out of offline scope. Manifest-text ancient-version flagging (Wave 3) is the in-scope subset.
- **Unverified vendor statistics** (CodeScene 83% vs 13.3%; "-23% velocity" empirical claim) — dropped per consensus skepticism; not cited in prompts or docs.

## Assumptions

The following were inferred rather than explicitly confirmed with the user:

1. **`change_size` T-shirt granularity** (S/M/L/XL) — the user rejected hours as meaningless for a ralph-consumed scanner and asked for a complexity/size measure instead. The S/M/L/XL granularity is my proposal; no hour mapping exists.
2. **`change_size` and `change_risk` are unmapped ordinals** — no numeric hour/probability backing. `change_size` feeds RICE/WSJF ranking ordinally (XL < S in priority-per-unit); `change_risk` is purely informational for the human dispatcher and gates nothing.
3. **ISO 25010 + Fowler quadrant as prose hints, not schema fields** — inferred to avoid cascade bloat; the user elevated only confidence/change_size/change_risk/disposition to real fields.
4. **SATD regex keyword set** (`TODO|FIXME|HACK|XXX|WORKAROUND|KLUDGE`) — taken from the research report's ~0.89 F1 set.
5. **`import_count` keyword set** (`import|using|require|include|use`) — chosen to cover the languages in `EXT_TO_LANG`; a coarse Ce proxy, not exhaustive.
6. **`git_churn` = commit-touch count** (not lines added+deleted) — chosen as the simpler, more robust churn proxy for the `severity × log1p(churn)` formula.
7. **Infrastructure-debt scout is manifest-text-only** — no network; the user approved the "pure text, no CVE DB" framing in the design.
8. **Spec lives in `claude-skills` repo** (the skill's source) on branch `spec/tech-debt-scan-redesign`, not the distribution repo.

Everything else in this spec was explicitly confirmed: two-spec split (Waves 1-5 then 6-7), real schema fields, change-size (not hours) as the size measure, change-risk as informational only, and the `severity × log1p(churn)` hotspot formula.
