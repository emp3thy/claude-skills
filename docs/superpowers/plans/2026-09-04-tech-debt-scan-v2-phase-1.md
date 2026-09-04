# tech-debt-scan v2 Phase 1 (signals) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the deterministic signal layer of tech-debt-scan v2 (config loader, inventory v2 with `coupling.json`, `patterns.py`, `rules.py`, the replayed three-fixture corpus and `evaluate.py`) on `feat/tech-debt-scan-v2-phase-1` with every v1 test still green and `/tech-debt-scan` unchanged.

**Architecture:** Four direct-path scripts under `skills/tech-debt-scan/scripts/` read `.tech-debt.yaml` through one loader and write pinned JSON files under `--workdir` (default `.tech-debt`): `inventory.py` walks the tree once and mines git once (git logic in `git_history.py`, the stem graph in `reference_graph.py`), `patterns.py` mines regex leads and SATD markers, `rules.py` emits tier-A findings for pipeline-infra and ownership, and `evaluate.py` scores output against `planted.json`. The corpus is three fixture trees plus a `history.yaml` each, replayed into a temporary git repository by `tests/helpers/make_history.py` at test time, so churn, coupling, blame age and branches are exercised without committing a `.git` directory.

**Tech Stack:** Python 3.11+ standard library plus pyyaml; git CLI (subprocess, list argv); pytest 8, ruff 0.15, mypy strict; GitHub Actions matrix 3.11 and 3.12.

**Spec:** `docs/superpowers/specs/2026-09-04-tech-debt-scan-v2-design.md` (sections 0, 3.3, 4.1, 4.2, 4.3, 4.4, 4.12, 4.13, 6, 11 "Phase 1: signals").

## Global Constraints

Copied from spec sections 0 and 3.3; every task's requirements include these.

- Python 3.11+ (`requires-python = ">=3.11"`); CI matrix runs 3.11 and 3.12.
- pyyaml is the only runtime dependency; every new script uses the standard library plus `yaml`.
- Every script is direct-path invocable as `python scripts/<name>.py` from `skills/tech-debt-scan/`; sibling imports are flat top-level imports (`from config import load_config`), never package imports. `mypy_path` and `tests/conftest.py` already resolve them.
- Every v2 script accepts `--workdir` (default `.tech-debt`) and reads and writes the pinned file names inside it; `inventory.py` keeps `--out` for compatibility.
- No file list ever appears on a command line; large inputs pass as file paths.
- Rendered output is LF-only: build text as `"\n".join(parts) + "\n"` and write with `write_bytes(text.encode("utf-8"))` (the `design_writer.py` pattern).
- Git and tool calls run with `timeout=120` and return a null result on failure (`OSError`, `subprocess.TimeoutExpired`, non-zero exit); a missing optional signal never aborts a scan.
- A missing pinned output file after a numbered SKILL.md step is exit 5 (SKILL.md step 1 is the only step this phase touches).
- Language-agnostic rule (spec 0(d), 3.3): the only language-aware code is the inventory's extension map (which also supplies comment syntax); every rule in `inventory.py`, `patterns.py` and `rules.py` is a union-of-idioms table; any per-language branch anywhere else is a defect; every pattern rule fires on at least two corpus languages.
- No live LLM in tests; the `live` pytest marker never runs in CI (`addopts = "-m 'not live'"`).
- Gate for every task and for the PR: `ruff check .`, `mypy`, `python skills/tech-debt-scan/scripts/skill_check.py`, `pytest -v`, all run from the repository root.
- Windows-safe argv: every subprocess call is a list, never a shell string; paths are forward-slashed in output.
- Branch `feat/tech-debt-scan-v2-phase-1` already exists and is checked out; every task commits on it (spec 0(g)).
- Commit trailers: every `git commit` in this plan ends its message with the two lines `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01MmhTCQKG5RSWjmpVSkirTU` (pass a second `-m` with both lines, or a heredoc body); the task steps show only the subject line.
- Human review of `design.md` before `promote.py` is unchanged; this phase does not touch the scan or promote workflows beyond the `accepted` count and the step 1 sentence.

## Guardrails (from project memory and standards)

Named anchors with their recorded confidence so tasks can cite them.

- **[[keep-docs-in-sync]]** (confidence 0.95, 7 evidence): `docs/architecture.md`, the README "Output formats" table and module docstrings are updated in the SAME task that changes what they describe; verify every documented flag against argparse; never carry a doc token forward unchecked. Phase 1 must update README's Output formats table (`inventory.json` shape, new `coupling.json`, `patterns.json`, `rule-findings.json` rows), `docs/architecture.md`'s inventory description, SKILL.md step 1's postcondition sentence, and each new script's module docstring. Task 13 carries the cross-file docs; Tasks 5 to 12 each write their own module docstring.
- **[[verify-red-step]]** (0.75, 2 evidence): every "run test, expect FAIL" step states the exact failure (`ModuleNotFoundError`, `ImportError`, `KeyError`, `AttributeError`, `AssertionError` text). A test that would pass against v1 code by accident (`entry.get("x") is None`, or a key-presence check on a key v1 already emits) is not RED; assert on the new value.
- **[[planning-memories-first]]** (0.9): done for this plan; `knowledge_list` (standards/ralph-runtime.md read) and `memory_retrieve` ran before drafting.
- **[[confidence-per-task]]** (standard): every task carries a confidence percentage; under 90 embeds a Step 0 spike or a concrete mitigation inside the task.
- **[[spec-code-not-lint-clean]]** (standard): no unused `import pytest`; `from __future__ import annotations` at the top of every script and test; py311 target so `datetime.UTC` not `timezone.utc` (UP017), `StrEnum` not `(str, Enum)` (UP042); line length 100; imports sorted (I rules); no `B` bugbear violations (no mutable default args, no bare `except: pass`, no unused loop variables, `zip(..., strict=True)`); mypy strict on `scripts/`: every function annotated, `dict[str, Any]` typed, no implicit Optional, `subprocess.run(..., text=True, check=False)` results typed as `CompletedProcess[str]`.
- **[[forward-reference-ordering]]** (standard): no task imports a symbol a later task creates; the Interfaces block of each task states which task defines every name it consumes.
- **[[cross-read-prose-vs-code]]** (standard): every code block in a task agrees with its prose and with the spec's schema keys; a mismatch is a defect.
- **[[language-agnostic]]** (spec 0(d), user instruction 2026-09-02): any `if language == ...` branch outside the extension map is a defect; rules are union regex tables; each pattern rule has a positive fixture in two languages; Task 10 adds a grep test over every script.
- **[[feature-branch-at-start]]** (standard): the branch exists; every task's commit step commits on it.

Dismissed, one line each:

- mkstemp+fdopen fd leak (0.6): `make_history.py` uses `tempfile.TemporaryDirectory` in tests and `pathlib` writes, no `mkstemp`.
- TypeScript `Partial<T>` (0.6): no TypeScript is executed; the TypeScript files are fixtures only.
- Playwright `has_text` (0.8): no browser tests.
- Paired enter/exit logging (0.55): no hang debugging in this plan.
- ralph-queue dispatch rule (0.9): the user executes this plan here, not via the queue.
- Fail-fast ordering comment (0.55): no composed guards of that shape.

## File structure

All paths are relative to the repository root `C:\Users\gethi\source\claude-skills`. `S` = `skills/tech-debt-scan/scripts`, `T` = `skills/tech-debt-scan/tests`.

`inventory.py` would pass 1,000 lines with the git pass and the graph inside it, so the git pass lives in `S/git_history.py` and the stem graph in `S/reference_graph.py`, both imported by flat top-level imports exactly as `promote.py` imports `bundle_writer`; `mypy_path` already covers `S/`. The lead's function names map as follows: `_git_log_pass` is `git_history.git_log_pass`, `_derive_file_history` is `git_history.derive_file_history`, `_change_coupling` is `git_history.change_coupling`, `_stem_graph` is `reference_graph.build_reference_graph`, `_tarjan_scc` is `reference_graph.tarjan_scc`; the underscore names stay inside `inventory.py`.

| File | Status | Responsibility |
|---|---|---|
| `S/config.py` | new (Task 1) | `.tech-debt.yaml` loader: `DEFAULTS`, `deep_merge`, `load_config`, unknown-key warning with line, `enabled_families`, `FAMILY_SETS`. |
| `S/validation.py` | modified (Task 2) | `accepted` status, four new debt types, `validate_type_id`, `validate_tier`, `VALID_TIERS`. |
| `S/promote.py` | modified (Task 2) | `PromoteResult.accepted_count`; summary line prints `accepted:`. |
| `T/helpers/__init__.py`, `T/helpers/make_history.py` | new (Task 3) | `replay_history`, `replay_fixture`, `git_output`: replay `history.yaml` into a git repository (ruff only, not mypy). |
| `T/conftest.py` | modified (Tasks 3, 4) | adds `tests/helpers` to `sys.path`; session-scoped replayed corpus fixtures `service_py_repo`, `web_ts_repo`, `mixed_decoys_repo`. |
| `T/fixtures/corpus/service-py/{files/**,history.yaml,planted.json}` | new (Task 4) | Python fixture: hotspot, coupled pair, knowledge island, empty except around a write, untested module, two-year-old FIXME, Dockerfile without USER, workflow without timeout, seeded credential, non-ASCII doc path, deleted file in history, unmerged `hotfix/*` branch, two tags. |
| `T/fixtures/corpus/web-ts/{files/**,history.yaml,planted.json}` | new (Task 4) | TypeScript fixture: three-file import cycle, co-committed near-duplicate pair, `@deprecated` helper still imported, permanently-off flag, empty `catch (e) {}`, two lockfile kinds, `tslint` beside `eslint`, clean CI workflow decoy, `release/*` branch, two tags. |
| `T/fixtures/corpus/mixed-decoys/{files/**,history.yaml,planted.json}` | new (Task 4) | Go fixture (chosen so the third language covers `if err != nil {` swallows, catch-less error idioms, a static-typed package layout with no build step): 300-line lookup table, `main.go` with no importer, string-dispatch map, fluent builder, `main()` that logs and `os.Exit(1)`, documented kill-switch flag, `docker-compose.dev.yml` with `latest`, `if err != nil { return nil }` swallow, two human authors (ownership suppressed), `staging` branch. |
| `S/inventory.py` | modified (Tasks 5, 7, 9) | adds `LANG_COMMENT`, `MANIFEST_NAMES`, `PATH_CLASS_GLOBS`, `ARTEFACT_CLASSES`, `_classify_path`, `_walk_artefacts`, `_conditional_ignore`, `_line_metrics` (5-tuple), `_hotspot_band`, `_map_tests`, `_tests_block`, `_docs_block`, `build_all`, `write_outputs`; `FileEntry` gains the v2 fields; `walk_inventory` becomes a wrapper over `build_all`; `--workdir` CLI. |
| `S/git_history.py` | new (Task 6, extended Task 7) | `Commit`, `FileHistory`, `git_log_pass`, `parse_log`, `is_bot`, `derive_file_history`, `list_branches`, `list_tags`, `blame_top_share`, `repo_authors`, `change_coupling`. |
| `S/reference_graph.py` | new (Task 8) | `IMPORT_LINE_RE`, `TOKEN_RE`, `GraphFile`, `GraphResult`, `file_stem`, `import_lines`, `identifier_tokens`, `build_reference_graph`, `tarjan_scc`, `directory_aggregates`. |
| `S/patterns.py` | new (Task 10) | rule table `RULES`, `SATD_MARKERS`, comment stripping via `LANG_COMMENT`, `run_patterns`, `capped_leads`, `write_patterns`, inline-disable write-back, `--no-blame`, `--workdir`. |
| `S/rules.py` | new (Task 11) | `run_rules` over ci, container, iac, manifest, release, ownership groups; `rule-findings.json` in the 4.7 candidate schema; migration leads. |
| `S/evaluate.py` | new (Task 12) | `evaluate` scoring findings against `planted.json`; table and `--json` output. |
| `T/test_config.py` | new (Task 1) | defaults, partial merge, unknown key line, four `enabled` forms, non-mapping error. |
| `T/test_validation.py`, `T/test_promote.py` | modified (Task 2) | new accept cases, `type_id`, tier, `accepted` count. |
| `T/test_make_history.py` | new (Task 3) | two-commit replay, branch, tag, delete. |
| `T/test_corpus.py` | new (Task 4) | commit counts per fixture, planted paths exist, replayed tree equals `files/`. |
| `T/test_inventory.py` | unchanged | the v1 pins (counts at lines 12, 23, 31; hotspot key set at line 72; churn 0 without git at line 81) must keep passing untouched. |
| `T/test_inventory_v2.py` | new (Tasks 5 to 9) | path and artefact classes, git pass, coupling, graph, band, mapping, docs block, CLI. |
| `T/test_patterns.py` | new (Task 10) | per-rule positives in two languages plus decoys, redaction, `--no-blame`, SATD age, language-conditional grep. |
| `T/test_rules.py` | new (Task 11) | per-rule positive and decoy, thresholds from config, ownership suppression and island bump. |
| `T/test_evaluate.py` | new (Task 12) | precision, recall, decoy tiers, top-N decoy over a hand-written `verified.json`. |
| `README.md`, `docs/architecture.md`, `skills/tech-debt-scan/SKILL.md` | modified (Task 13) | Output formats rows, inventory section, step 1 postcondition sentence. |

---

### Task 1: `config.py` and the `.tech-debt.yaml` loader

**Files:**
- Create: `skills/tech-debt-scan/scripts/config.py`
- Create: `skills/tech-debt-scan/tests/test_config.py`

**Interfaces:**
- Consumes: nothing from other tasks (`yaml` and the standard library only).
- Produces (used by Tasks 5 to 12):
  - `CONFIG_FILENAME: Final[str] = ".tech-debt.yaml"`
  - `DEFAULTS: Final[dict[str, Any]]` (the spec 4.1 defaults verbatim)
  - `FAMILY_SETS: Final[dict[str, tuple[str, ...]]]` with keys `default`, `quick`, `deep` (spec 2.4)
  - `class ConfigError(Exception)`
  - `def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]`
  - `def load_config(root: Path) -> dict[str, Any]` (deep copy of defaults merged with the file; unknown top-level keys warned to stderr with their line and dropped)
  - `def enabled_families(config: dict[str, Any]) -> list[str]`

**Spec:** 4.1 (defaults, four `enabled` forms, unknown key with line), 2.4 (family sets), 3.3 (direct-path).

**Confidence:** 96% (yaml.compose node marks verified on this machine: root `MappingNode.value` is a list of `(key_node, value_node)` and `key_node.start_mark.line` is zero-based; `yaml.compose("")` returns `None`).

- [ ] **Step 1: Write the failing tests**

Create `skills/tech-debt-scan/tests/test_config.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest
from config import DEFAULTS, ConfigError, deep_merge, enabled_families, load_config


def test_defaults_load_without_a_file(tmp_path: Path) -> None:
    cfg = load_config(tmp_path)
    assert cfg == DEFAULTS
    assert cfg is not DEFAULTS
    assert cfg["churn_months"] == 12
    assert cfg["coupling"] == {"min_shared": 3, "min_ratio": 0.30, "bulk_threshold": 50}
    assert cfg["hotspot_band"] == {"fraction": 0.10, "min": 5, "max": 50}
    assert cfg["fan_in"]["stoplist"] == [
        "utils", "config", "index", "main", "types", "common", "base", "core", "helpers", "models",
    ]
    assert cfg["rules"]["ownership"]["island_share"] == 0.8
    assert cfg["families"]["enabled"] == "default"


def test_defaults_are_not_mutated_by_a_caller(tmp_path: Path) -> None:
    cfg = load_config(tmp_path)
    cfg["fan_in"]["stoplist"].append("zzz")
    assert "zzz" not in DEFAULTS["fan_in"]["stoplist"]


def test_partial_file_merges_over_defaults(tmp_path: Path) -> None:
    (tmp_path / ".tech-debt.yaml").write_text(
        "churn_months: 6\ncoupling:\n  min_shared: 5\nbot_authors: [robot]\n", encoding="utf-8"
    )
    cfg = load_config(tmp_path)
    assert cfg["churn_months"] == 6
    assert cfg["coupling"]["min_shared"] == 5
    assert cfg["coupling"]["min_ratio"] == 0.30
    assert cfg["coupling"]["bulk_threshold"] == 50
    assert cfg["bot_authors"] == ["robot"]
    assert cfg["hotspot_band"]["max"] == 50


def test_unknown_top_level_key_is_reported_with_line_and_ignored(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".tech-debt.yaml").write_text(
        "churn_months: 6\nbogus_key: 1\ncoupling:\n  min_shared: 4\n", encoding="utf-8"
    )
    cfg = load_config(tmp_path)
    assert "bogus_key" not in cfg
    assert cfg["coupling"]["min_shared"] == 4
    err = capsys.readouterr().err
    assert ".tech-debt.yaml" in err
    assert "line 2" in err
    assert "bogus_key" in err


@pytest.mark.parametrize(
    ("enabled", "expected_first", "expected_len"),
    [
        ("default", "complex-units", 12),
        ("quick", "complex-units", 6),
        ("deep", "complex-units", 14),
        (["security", "dead-code"], "security", 2),
    ],
)
def test_families_enabled_accepts_four_forms(
    tmp_path: Path, enabled: str | list[str], expected_first: str, expected_len: int
) -> None:
    import yaml

    (tmp_path / ".tech-debt.yaml").write_text(
        yaml.safe_dump({"families": {"enabled": enabled}}), encoding="utf-8"
    )
    cfg = load_config(tmp_path)
    fams = enabled_families(cfg)
    assert fams[0] == expected_first
    assert len(fams) == expected_len


def test_unknown_family_set_name_raises(tmp_path: Path) -> None:
    (tmp_path / ".tech-debt.yaml").write_text("families:\n  enabled: turbo\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="turbo"):
        enabled_families(load_config(tmp_path))


def test_non_mapping_root_raises(tmp_path: Path) -> None:
    (tmp_path / ".tech-debt.yaml").write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="mapping"):
        load_config(tmp_path)


def test_empty_file_gives_defaults(tmp_path: Path) -> None:
    (tmp_path / ".tech-debt.yaml").write_text("", encoding="utf-8")
    assert load_config(tmp_path) == DEFAULTS


def test_deep_merge_replaces_lists_and_recurses_into_dicts() -> None:
    merged = deep_merge({"a": {"b": 1, "c": [1]}, "d": 2}, {"a": {"c": [9]}, "d": 3})
    assert merged == {"a": {"b": 1, "c": [9]}, "d": 3}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest skills/tech-debt-scan/tests/test_config.py -v`
Expected: collection error `ModuleNotFoundError: No module named 'config'` (the import at the top of the test file fails before any test runs).

- [ ] **Step 3: Write `config.py`**

Create `skills/tech-debt-scan/scripts/config.py`:

```python
"""Load ``.tech-debt.yaml`` from the repository root with spec defaults.

One loader imported by every v2 script (spec 4.1). Every key is optional; the
``DEFAULTS`` mapping below applies when the file or a key is absent. A partial
file deep-merges over the defaults (mappings recurse, lists and scalars
replace). Unknown top-level keys are reported to stderr with their line number
and ignored, never fatal, because a typo must not abort a scan.

``families.enabled`` accepts ``default``, ``quick``, ``deep`` or an explicit
list; ``enabled_families`` expands the named sets of spec 2.4.

Only ``yaml.safe_load``/``yaml.compose`` are used (never ``yaml.load``). The
file is read as UTF-8; ``yaml.compose`` supplies the node marks that give the
unknown-key line numbers.

Direct-path invocable: `python config.py <root>` prints the effective config
as JSON so a user can check what a scan will read.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any, Final

import yaml

CONFIG_FILENAME: Final[str] = ".tech-debt.yaml"

DEFAULTS: Final[dict[str, Any]] = {
    "schema_version": 1,
    "ignore": [],
    "path_classes": {"tests": [], "generated": [], "vendored": [], "docs": []},
    "families": {
        "enabled": "default",
        "disabled": [],
        "per_path_class": {
            "tests": {"disable": ["duplication", "complex-units", "god-classes"]},
            "generated": {"disable": "all"},
            "vendored": {"disable": "all"},
        },
    },
    "churn_months": 12,
    "bot_authors": ["[bot]", "Claude", "dependabot", "renovate", "github-actions"],
    "hotspot_band": {"fraction": 0.10, "min": 5, "max": 50},
    "coupling": {"min_shared": 3, "min_ratio": 0.30, "bulk_threshold": 50},
    "fan_in": {
        "mode": "auto",
        "min_stem_length": 4,
        "ambiguous": {
            "shared_stem": True,
            "package_files": ["__init__", "__main__", "index", "mod", "lib"],
            "harness_files": ["conftest", "setup"],
        },
        "stoplist": [
            "utils", "config", "index", "main", "types",
            "common", "base", "core", "helpers", "models",
        ],
    },
    "scout_cap": 12,
    "top": 5,
    "chunking": {"max_files": 1500, "max_loc": 200000},
    "verifier": {
        "batch_size": 6,
        "context_lines": 30,
        "min_candidates": 30,
        "top_multiple": 3,
        "max_candidates": 72,
        "always_families": ["security"],
        "always_min_severity": 5,
    },
    "ranking": {
        "preset": "balanced",
        "weights": {"wH": 1.0, "wC": 0.5, "wF": 0.5},
        "tractability": {"S": 1.0, "M": 0.75, "L": 0.5},
        "spread_cap": 0.5,
    },
    "tools": {"allow": "all", "deny": [], "network": True, "timeout_s": 120},
    "rules": {
        "ownership": {
            "island_share": 0.8,
            "island_max_authors": 2,
            "inactive_days": 180,
            "min_human_authors": 3,
            "max_stale_branches": 10,
        },
        "release": {"stale_branch_days": 90, "min_tags": 5, "gap_multiple": 4},
    },
    "ci_enforces": [],
    "baseline": ".tech-debt/baseline.json",
    "suppressions": [],
    "traps": [],
}

# Spec 2.4. Order is dispatch order; plan_scan.py (phase 2) reads these.
FAMILY_SETS: Final[dict[str, tuple[str, ...]]] = {
    "default": (
        "complex-units", "god-classes", "duplication", "dead-code", "error-masking",
        "test-gaps", "half-finished", "migration", "dependency-debt", "doc-drift",
        "architecture", "security",
    ),
    "quick": (
        "complex-units", "error-masking", "test-gaps", "half-finished",
        "dependency-debt", "security",
    ),
    "deep": (
        "complex-units", "god-classes", "duplication", "dead-code", "error-masking",
        "test-gaps", "half-finished", "migration", "dependency-debt", "doc-drift",
        "architecture", "security", "test-quality", "pipeline-infra",
    ),
}


class ConfigError(Exception):
    """Raised when ``.tech-debt.yaml`` cannot be used at all (not a mapping)."""


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Return a new dict: ``override`` merged over ``base``, recursing into dicts."""
    merged: dict[str, Any] = copy.deepcopy(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = deep_merge(current, value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _key_lines(text: str) -> dict[str, int]:
    """Map each top-level key to its 1-based line using yaml node marks."""
    node = yaml.compose(text)
    if node is None:
        return {}
    if not isinstance(node, yaml.MappingNode):
        raise ConfigError(f"{CONFIG_FILENAME}: top level must be a mapping")
    lines: dict[str, int] = {}
    for key_node, _value_node in node.value:
        lines[str(key_node.value)] = key_node.start_mark.line + 1
    return lines


def load_config(root: Path) -> dict[str, Any]:
    """Load ``<root>/.tech-debt.yaml`` merged over ``DEFAULTS``.

    Unknown top-level keys are printed to stderr as
    ``warning: .tech-debt.yaml line N: unknown key 'x' ignored`` and dropped.
    Raises ConfigError only when the file's top level is not a mapping.
    """
    path = root / CONFIG_FILENAME
    if not path.is_file():
        return copy.deepcopy(DEFAULTS)
    text = path.read_text(encoding="utf-8")
    key_lines = _key_lines(text)
    raw = yaml.safe_load(text)
    if raw is None:
        return copy.deepcopy(DEFAULTS)
    if not isinstance(raw, dict):
        raise ConfigError(f"{CONFIG_FILENAME}: top level must be a mapping")
    known: dict[str, Any] = {}
    for key, value in raw.items():
        name = str(key)
        if name in DEFAULTS:
            known[name] = value
        else:
            line = key_lines.get(name, 0)
            print(
                f"warning: {CONFIG_FILENAME} line {line}: unknown key {name!r} ignored",
                file=sys.stderr,
            )
    return deep_merge(DEFAULTS, known)


def enabled_families(config: dict[str, Any]) -> list[str]:
    """Expand ``families.enabled`` (a set name or an explicit list) to a list."""
    enabled = config["families"]["enabled"]
    if isinstance(enabled, list):
        return [str(item) for item in enabled]
    name = str(enabled)
    if name not in FAMILY_SETS:
        raise ConfigError(
            f"families.enabled must be one of {sorted(FAMILY_SETS)} or a list, got {name!r}"
        )
    return list(FAMILY_SETS[name])


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print the effective tech-debt-scan config")
    parser.add_argument("root", help="repository root holding .tech-debt.yaml")
    args = parser.parse_args(argv)
    try:
        cfg = load_config(Path(args.root))
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(cfg, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest skills/tech-debt-scan/tests/test_config.py -v`
Expected: 12 passed (9 functions, the parametrised one expands to 4).

- [ ] **Step 5: Lint and type-check**

Run: `ruff check skills/tech-debt-scan/scripts/config.py skills/tech-debt-scan/tests/test_config.py && mypy`
Expected: `All checks passed!` and `Success: no issues found in N source files`.

- [ ] **Step 6: Commit**

```bash
git add skills/tech-debt-scan/scripts/config.py skills/tech-debt-scan/tests/test_config.py
git commit -m "feat(tech-debt-scan): add config.py loader for .tech-debt.yaml"
```

---

### Task 2: `validation.py` and `promote.py` (`accepted`, new debt types, `type_id`, tier)

**Files:**
- Modify: `skills/tech-debt-scan/scripts/validation.py:7-32` (constants) and append two validators
- Modify: `skills/tech-debt-scan/scripts/promote.py:16-20` (docstring counters), `:48-56` (dataclass), `:106-111` (status branches), `:135-140` (summary)
- Modify: `skills/tech-debt-scan/tests/test_validation.py` (append), `skills/tech-debt-scan/tests/test_promote.py` (append)

**Interfaces:**
- Consumes: existing `ValidationError`, `PromoteResult`, `run_promote`, `_main` in those files.
- Produces (used by phase 2 and 3, and by Task 11's finding schema):
  - `VALID_TIERS: Final[frozenset[str]] = frozenset({"A", "B", "C"})`
  - `def validate_type_id(value: str) -> None` (regex `^TD-\d{2}$`, range 01 to 35)
  - `def validate_tier(value: str) -> None`
  - `PromoteResult.accepted_count: int`

**Spec:** 4.13 (all five bullets; `validate_confidence` stays until phase 3), 4.12 ("`promote.py` counts `accepted` separately from phase 1").

**Confidence:** 97% (pure constant and branch additions; the existing reject lists `""`, `Code`, `perf`, `tests` and `pending `, `APPROVED`, `yes`, `no` do not collide with the new values).

- [ ] **Step 1: Write the failing validation tests**

Append to `skills/tech-debt-scan/tests/test_validation.py` (extend the import block first so it reads):

```python
from validation import (
    VALID_CONFIDENCES,
    VALID_DEBT_TYPES,
    VALID_EFFORTS,
    VALID_STATUSES,
    VALID_TIERS,
    ValidationError,
    validate_confidence,
    validate_debt_type,
    validate_effort,
    validate_slug,
    validate_status,
    validate_tier,
    validate_type_id,
)
```

then append at the end of the file:

```python
def test_accepted_is_a_valid_status() -> None:
    assert "accepted" in VALID_STATUSES
    validate_status("accepted")


@pytest.mark.parametrize("good", ["security", "infrastructure", "knowledge-process", "defect"])
def test_new_debt_types_accepted(good: str) -> None:
    assert good in VALID_DEBT_TYPES
    validate_debt_type(good)


@pytest.mark.parametrize("reserved", ["data", "ml-ai", "performance"])
def test_reserved_debt_types_still_rejected(reserved: str) -> None:
    with pytest.raises(ValidationError, match="unknown debt_type"):
        validate_debt_type(reserved)


@pytest.mark.parametrize("good", ["TD-01", "TD-13", "TD-35"])
def test_validate_type_id_accepts(good: str) -> None:
    validate_type_id(good)


@pytest.mark.parametrize("bad", ["", "TD-00", "TD-36", "TD-1", "td-01", "TD-013", "TD-13 "])
def test_validate_type_id_rejects(bad: str) -> None:
    with pytest.raises(ValidationError, match="invalid type_id"):
        validate_type_id(bad)


@pytest.mark.parametrize("good", sorted(VALID_TIERS))
def test_validate_tier_accepts(good: str) -> None:
    validate_tier(good)


@pytest.mark.parametrize("bad", ["", "a", "D", "AA", "A "])
def test_validate_tier_rejects(bad: str) -> None:
    with pytest.raises(ValidationError, match="unknown tier"):
        validate_tier(bad)
```

- [ ] **Step 2: Run the validation tests to verify they fail**

Run: `pytest skills/tech-debt-scan/tests/test_validation.py -v`
Expected: collection error `ImportError: cannot import name 'VALID_TIERS' from 'validation'`.

- [ ] **Step 3: Extend `validation.py`**

Replace lines 7 to 26 of `skills/tech-debt-scan/scripts/validation.py` so the constants read:

```python
VALID_STATUSES: Final[frozenset[str]] = frozenset(
    {"pending", "approved", "rejected", "accepted", "promoted"}
)

# Debt-type axis (classification, orthogonal to the scout family). Derived
# from the SATD / Alves taxonomies: code and design debt are merged into
# "code" vs "design" at the scout's discretion; the rest are the widely-agreed
# artifact buckets. v2 (spec 2.2) adds security, infrastructure,
# knowledge-process and defect; data and ml-ai are reserved for the data-ml
# follow-on and performance is deliberately absent.
VALID_DEBT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "code",
        "design",
        "architecture",
        "test",
        "documentation",
        "dependency",
        "build",
        "requirement",
        "security",
        "infrastructure",
        "knowledge-process",
        "defect",
    }
)

# Evidence tier earned after verification (spec 4.8): A corroborated, B
# confirmed only, C unverified or downgraded.
VALID_TIERS: Final[frozenset[str]] = frozenset({"A", "B", "C"})

# Optional taxonomy id TD-01 to TD-35 (spec 2.1); checked only when present.
_TYPE_ID_RE: Final[re.Pattern[str]] = re.compile(r"^TD-\d{2}$")
_TYPE_ID_MAX: Final[int] = 35
```

and append after `validate_confidence`:

```python
def validate_type_id(value: str) -> None:
    if not _TYPE_ID_RE.fullmatch(value) or not 1 <= int(value[3:]) <= _TYPE_ID_MAX:
        raise ValidationError(f"invalid type_id: {value!r}; expected TD-01 to TD-{_TYPE_ID_MAX}")


def validate_tier(value: str) -> None:
    if value not in VALID_TIERS:
        raise ValidationError(f"unknown tier: {value!r}; expected one of {sorted(VALID_TIERS)}")
```

- [ ] **Step 4: Run the validation tests to verify they pass**

Run: `pytest skills/tech-debt-scan/tests/test_validation.py -v`
Expected: all pass (the pre-existing 40 cases plus 22 new).

- [ ] **Step 5: Write the failing promote tests**

Append to `skills/tech-debt-scan/tests/test_promote.py`:

```python
def test_accepted_counted_separately_from_pending(tmp_path: Path) -> None:
    src = tmp_path / "design.md"
    src.write_text(GOLDEN.read_text().replace("status: pending", "status: accepted", 1))
    result = run_promote(src, out_root=tmp_path / "out", date="2026-05-31")
    assert result.exit_code == 0
    assert result.emitted_count == 0
    assert result.accepted_count == 1
    assert result.pending_count == 4
    assert result.rejected_count == 0
    assert "status: accepted" in src.read_text()


def test_summary_line_reports_accepted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from promote import _main

    src = tmp_path / "design.md"
    src.write_text(GOLDEN.read_text().replace("status: pending", "status: accepted", 2))
    assert _main([str(src), "--out", str(tmp_path / "out")]) == 0
    out = capsys.readouterr().out
    assert "accepted: 2" in out
    assert "pending: 3" in out
```

and add `import pytest` to the import block of `test_promote.py` (it is used by the `capsys` annotation).

- [ ] **Step 6: Run the promote tests to verify they fail**

Run: `pytest skills/tech-debt-scan/tests/test_promote.py -v`
Expected: `test_accepted_counted_separately_from_pending` FAILS with `AttributeError: 'PromoteResult' object has no attribute 'accepted_count'` (the design now parses because Step 3 made `accepted` valid); `test_summary_line_reports_accepted` FAILS with `AssertionError: assert 'accepted: 2' in 'emitted: 0, already-promoted: 0, rejected: 0, pending: 5\n'`.

- [ ] **Step 7: Teach `promote.py` to count `accepted`**

In `skills/tech-debt-scan/scripts/promote.py`:

Replace the docstring paragraph at lines 16 to 20 with:

```
Counters are kept separate (per [[852f5ae9]]): ``emitted_count`` (bundles
written this run), ``already_promoted_count`` (findings already ``promoted`` on
disk, i.e. a prior run handled them), ``rejected_count``, ``accepted_count``
(deliberate deferrals, spec 4.12; never reported as pending) and
``pending_count``. "No-op because already promoted" is never conflated with
"no-op because nothing was approved".
```

Add to `PromoteResult` after `rejected_count: int = 0`:

```python
    accepted_count: int = 0
```

Replace the status branches (lines 106 to 111) with:

```python
        elif status == "promoted":
            result.already_promoted_count += 1
        elif status == "rejected":
            result.rejected_count += 1
        elif status == "accepted":
            result.accepted_count += 1
        else:  # pending
            result.pending_count += 1
```

Replace the summary `print` in `_main` with:

```python
    print(
        f"emitted: {result.emitted_count}, "
        f"already-promoted: {result.already_promoted_count}, "
        f"rejected: {result.rejected_count}, "
        f"accepted: {result.accepted_count}, "
        f"pending: {result.pending_count}"
    )
```

- [ ] **Step 8: Run the whole suite to verify everything passes**

Run: `pytest -v`
Expected: all pass, including the untouched `test_e2e.py` and `test_design_parser.py`.

- [ ] **Step 9: Lint and type-check**

Run: `ruff check . && mypy`
Expected: `All checks passed!` and `Success: no issues found`.

- [ ] **Step 10: Commit**

```bash
git add skills/tech-debt-scan/scripts/validation.py skills/tech-debt-scan/scripts/promote.py skills/tech-debt-scan/tests/test_validation.py skills/tech-debt-scan/tests/test_promote.py
git commit -m "feat(tech-debt-scan): accepted status, v2 debt types, type_id and tier validators"
```

---

### Task 3: `tests/helpers/make_history.py`, conftest path and a smoke test

**Files:**
- Create: `skills/tech-debt-scan/tests/helpers/__init__.py` (empty)
- Create: `skills/tech-debt-scan/tests/helpers/make_history.py`
- Modify: `skills/tech-debt-scan/tests/conftest.py:1-9` (whole file)
- Create: `skills/tech-debt-scan/tests/test_make_history.py`

**Interfaces:**
- Consumes: nothing from other tasks (`yaml`, `subprocess`, `pathlib`).
- Produces (used by Task 4's fixtures and every test from Task 6 on):
  - `CORPUS_ROOT: Path` (`tests/fixtures/corpus`)
  - `FINAL: str = "@final"` (a `files:` value meaning "copy this path from `files/`")
  - `class HistoryError(Exception)`
  - `def replay_history(history_yaml: Path, files_root: Path, dest: Path) -> Path`
  - `def replay_fixture(name: str, dest: Path) -> Path`
  - `def git_output(repo: Path, *args: str) -> str` (runs git in `repo` with the fixed `-c` options, raises `HistoryError` on non-zero exit, returns stdout)

**`history.yaml` schema** (spec 6: "an ordered list of commits, each with author, date, subject and the files it touches with their content at that point"; the lead adds `branch:` and `tag:`):

```yaml
commits:
  - author: "Ada Lovelace <ada@example.com>"   # required, git --author form
    date: "2024-09-10T10:00:00+00:00"          # required, quoted ISO 8601; also GIT_COMMITTER_DATE
    subject: "feat: initial"                   # required
    branch: main                               # optional: checkout (creating if absent) before writing
    files:                                     # optional: path -> content at this point
      src/app.py: |                            #   a block scalar is the literal content
        x = 1
      README.md: "@final"                      #   "@final" copies files/README.md
    delete: [src/old.py]                       # optional: paths removed in this commit
    tag: v0.1.0                                # optional: lightweight tag on this commit
```

The repository is created with `git init -q` then `git symbolic-ref HEAD refs/heads/main`, so the first commit lands on `main` on every git version. Every git call is `git -C <dest> -c user.name=Fixture -c user.email=fixture@example.com -c commit.gpgsign=false -c core.autocrlf=false -c core.quotePath=false <args>` as a list (Windows-safe, no shell). Verified on this machine (git 2.51): `%aI` renders a `+00:00` date as `2024-09-10T10:00:00Z`, so tests compare with `startswith("...T10:00:00")`; a lightweight tag's `creatordate` is the tagged commit's committer date, which `GIT_COMMITTER_DATE` fixes.

**Spec:** 6 (helper, fixtures without a committed `.git`; "mypy covers only `scripts/`, so the helper gets ruff but not mypy"), 3.3 (Windows-safe argv, 120 s timeouts).

**Confidence:** 94% (every git invocation and output format in this task was run on this machine before the plan was written; the only untested path is git absent, which the test skips).

- [ ] **Step 1: Add `tests/helpers` to `sys.path` in conftest**

Replace the whole of `skills/tech-debt-scan/tests/conftest.py` with:

```python
"""Pytest path setup so scripts/ and tests/helpers imports work in tests."""
from __future__ import annotations

import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = _TESTS_DIR.parent / "scripts"
HELPERS_DIR = _TESTS_DIR / "helpers"
for _dir in (SCRIPTS_DIR, HELPERS_DIR):
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))
```

Create the empty file `skills/tech-debt-scan/tests/helpers/__init__.py`.

- [ ] **Step 2: Write the failing smoke test**

Create `skills/tech-debt-scan/tests/test_make_history.py`:

```python
"""Smoke test for the history.yaml replay helper (spec section 6)."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from make_history import HistoryError, git_output, replay_history

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

HISTORY = """\
commits:
  - author: "Ada Lovelace <ada@example.com>"
    date: "2024-09-10T10:00:00+00:00"
    subject: "feat: initial"
    files:
      src/app.py: |
        x = 1
      src/old.py: |
        z = 3
      README.md: "@final"
    tag: v0.1.0
  - author: "Grace Hopper <grace@example.com>"
    date: "2025-03-01T09:00:00+00:00"
    subject: "fix: rounding\\twith tab"
    branch: hotfix/rounding
    files:
      src/app.py: |
        x = 3
  - author: "Grace Hopper <grace@example.com>"
    date: "2025-04-01T09:00:00+00:00"
    subject: "fix: rounding"
    branch: main
    files:
      src/app.py: "@final"
    delete: [src/old.py]
"""


def _write_history(tmp_path: Path) -> tuple[Path, Path]:
    files_root = tmp_path / "files"
    (files_root / "src").mkdir(parents=True)
    (files_root / "src" / "app.py").write_bytes(b"x = 2\n")
    (files_root / "README.md").write_bytes(b"# demo\n")
    history = tmp_path / "history.yaml"
    history.write_text(HISTORY, encoding="utf-8")
    return history, files_root


def test_replay_authors_dates_and_subjects_on_main(tmp_path: Path) -> None:
    history, files_root = _write_history(tmp_path)
    repo = replay_history(history, files_root, tmp_path / "repo")
    log = git_output(repo, "log", "--reverse", "--format=%aN|%aI|%s").splitlines()
    assert len(log) == 2  # the hotfix commit is on its own branch, not on main
    assert log[0].startswith("Ada Lovelace|2024-09-10T10:00:00")
    assert log[0].endswith("|feat: initial")
    assert log[1].startswith("Grace Hopper|2025-04-01T09:00:00")
    committer = git_output(repo, "log", "-1", "--format=%cI").strip()
    assert committer.startswith("2025-04-01T09:00:00")


def test_replay_final_tree_branch_tag_and_delete(tmp_path: Path) -> None:
    history, files_root = _write_history(tmp_path)
    repo = replay_history(history, files_root, tmp_path / "repo")
    assert (repo / "src" / "app.py").read_bytes() == b"x = 2\n"
    assert (repo / "README.md").read_bytes() == b"# demo\n"
    assert not (repo / "src" / "old.py").exists()
    assert git_output(repo, "tag").split() == ["v0.1.0"]
    heads = git_output(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()
    assert heads == ["hotfix/rounding", "main"]
    assert git_output(repo, "symbolic-ref", "--short", "HEAD").strip() == "main"
    subject = git_output(repo, "log", "-1", "--format=%s", "hotfix/rounding").rstrip("\n")
    assert subject == "fix: rounding\twith tab"


def test_malformed_history_raises(tmp_path: Path) -> None:
    history = tmp_path / "history.yaml"
    history.write_text("commits:\n  - author: x\n", encoding="utf-8")
    with pytest.raises(HistoryError, match="missing 'date'"):
        replay_history(history, tmp_path, tmp_path / "repo")


def test_git_output_raises_on_failure(tmp_path: Path) -> None:
    history, files_root = _write_history(tmp_path)
    repo = replay_history(history, files_root, tmp_path / "repo")
    with pytest.raises(HistoryError, match="rev-parse"):
        git_output(repo, "rev-parse", "--verify", "refs/heads/does-not-exist")
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `pytest skills/tech-debt-scan/tests/test_make_history.py -v`
Expected: collection error `ModuleNotFoundError: No module named 'make_history'`.

- [ ] **Step 4: Write the helper**

Create `skills/tech-debt-scan/tests/helpers/make_history.py`:

```python
"""Replay a corpus ``history.yaml`` into a fresh git repository (spec 6).

Fixtures under ``tests/fixtures/corpus/<name>/`` keep their final tree in
``files/`` and their history in ``history.yaml`` (an ordered list of commits:
author, date, subject, the files touched with their content at that point,
optional ``branch``, ``delete`` and ``tag``). Replaying at test time gives
churn, coupling, blame age, authorship, branches and tags without committing
a ``.git`` directory.

Every git call is a list argv with fixed identity and safety options
(``user.name``, ``user.email``, ``commit.gpgsign=false``,
``core.autocrlf=false``, ``core.quotePath=false``) so the replay is identical
on Windows and Linux. ``GIT_COMMITTER_DATE`` is set to the commit date so
committer dates, and therefore lightweight-tag creator dates, are fixed.

A ``files:`` value of ``"@final"`` copies the path from ``files/``; any other
string is written literally (UTF-8, LF as given). This module is covered by
ruff but not mypy (mypy's ``files`` is ``scripts/`` only).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

CORPUS_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "corpus"
FINAL = "@final"

_GIT_FIXED: tuple[str, ...] = (
    "-c", "user.name=Fixture",
    "-c", "user.email=fixture@example.com",
    "-c", "commit.gpgsign=false",
    "-c", "core.autocrlf=false",
    "-c", "core.quotePath=false",
)


class HistoryError(Exception):
    """Raised when history.yaml is malformed or a git command fails."""


def _run(
    repo: Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *_GIT_FIXED, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
        timeout=120,
    )


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    proc = _run(repo, *args, env=env)
    if proc.returncode != 0:
        raise HistoryError(
            f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}"
        )
    return proc.stdout


def git_output(repo: Path, *args: str) -> str:
    """Run ``git <args>`` in ``repo`` and return stdout; raise HistoryError on failure."""
    return _git(repo, *args)


def _branch_exists(repo: Path, name: str) -> bool:
    return _run(repo, "rev-parse", "--verify", "-q", f"refs/heads/{name}").returncode == 0


def _current_branch(repo: Path) -> str:
    return _run(repo, "symbolic-ref", "--short", "HEAD").stdout.strip()


def _checkout(repo: Path, name: str) -> None:
    if name == _current_branch(repo):
        return
    if _branch_exists(repo, name):
        _git(repo, "checkout", "-q", name)
    else:
        _git(repo, "checkout", "-q", "-b", name)


def _write(dest: Path, rel: str, value: Any, files_root: Path) -> None:
    target = dest / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    text = "" if value is None else str(value)
    if text == FINAL:
        source = files_root / rel
        if not source.is_file():
            raise HistoryError(f"{rel}: '@final' but {source} does not exist")
        shutil.copyfile(source, target)
    else:
        target.write_bytes(text.encode("utf-8"))


def _date_string(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def replay_history(history_yaml: Path, files_root: Path, dest: Path) -> Path:
    """Create a git repository at ``dest`` by replaying ``history_yaml``.

    Returns ``dest``. HEAD ends on whichever branch the last commit named
    (``main`` when none did).
    """
    raw = yaml.safe_load(history_yaml.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("commits"), list):
        raise HistoryError(f"{history_yaml}: expected a mapping with a 'commits' list")
    dest.mkdir(parents=True, exist_ok=True)
    _git(dest, "init", "-q")
    _git(dest, "symbolic-ref", "HEAD", "refs/heads/main")
    for index, commit in enumerate(raw["commits"], start=1):
        if not isinstance(commit, dict):
            raise HistoryError(f"commit {index}: not a mapping")
        for key in ("author", "date", "subject"):
            if key not in commit:
                raise HistoryError(f"commit {index}: missing {key!r}")
        date = _date_string(commit["date"])
        branch = commit.get("branch")
        if branch is not None:
            _checkout(dest, str(branch))
        files = commit.get("files") or {}
        if not isinstance(files, dict):
            raise HistoryError(f"commit {index}: 'files' must be a mapping")
        for rel, value in files.items():
            _write(dest, str(rel), value, files_root)
        for rel in commit.get("delete") or []:
            (dest / str(rel)).unlink()
        _git(dest, "add", "-A")
        env = {**os.environ, "GIT_COMMITTER_DATE": date}
        _git(
            dest, "commit", "-q", "--allow-empty",
            "--author", str(commit["author"]), "--date", date, "-m", str(commit["subject"]),
            env=env,
        )
        tag = commit.get("tag")
        if tag is not None:
            _git(dest, "tag", str(tag), env=env)
    return dest


def replay_fixture(name: str, dest: Path) -> Path:
    """Replay ``tests/fixtures/corpus/<name>`` into ``dest`` and return ``dest``."""
    base = CORPUS_ROOT / name
    return replay_history(base / "history.yaml", base / "files", dest)
```

- [ ] **Step 5: Run the smoke test to verify it passes**

Run: `pytest skills/tech-debt-scan/tests/test_make_history.py -v`
Expected: 4 passed.

- [ ] **Step 6: Lint**

Run: `ruff check skills/tech-debt-scan/tests && mypy`
Expected: `All checks passed!`; mypy unchanged (helpers are outside its `files`).

- [ ] **Step 7: Commit**

```bash
git add skills/tech-debt-scan/tests/conftest.py skills/tech-debt-scan/tests/helpers skills/tech-debt-scan/tests/test_make_history.py
git commit -m "test(tech-debt-scan): add history.yaml replay helper for the fixture corpus"
```

---

### Task 4: the fixture corpus (`service-py`, `web-ts`, `mixed-decoys`)

**Files:**
- Create: `skills/tech-debt-scan/tests/fixtures/corpus/service-py/files/**`, `.../service-py/history.yaml`, `.../service-py/planted.json`
- Create: `skills/tech-debt-scan/tests/fixtures/corpus/web-ts/files/**`, `.../web-ts/history.yaml`, `.../web-ts/planted.json`
- Create: `skills/tech-debt-scan/tests/fixtures/corpus/mixed-decoys/files/**`, `.../mixed-decoys/history.yaml`, `.../mixed-decoys/planted.json`
- Modify: `skills/tech-debt-scan/tests/conftest.py` (append three session fixtures)
- Modify: `pyproject.toml:20-22` (`[tool.ruff]` gains `extend-exclude` for the corpus, whose Python deliberately contains `except Exception: pass`, string SQL and long table rows)
- Create: `skills/tech-debt-scan/tests/test_corpus.py`

**Interfaces:**
- Consumes: `replay_fixture`, `git_output`, `CORPUS_ROOT` from `make_history.py` (Task 3).
- Produces (used by Tasks 5 to 12): the three trees with the exact paths and line numbers listed in each `planted.json`; the session-scoped fixtures `service_py_repo`, `web_ts_repo`, `mixed_decoys_repo` (each a `Path` to a replayed repository whose HEAD is `main`). These fixtures are shared for the whole session: a test that must write into a repository copies it first with `shutil.copytree(repo, tmp_path / "copy")`.

**Facts every later test relies on** (derived from the histories below; recount if you edit a history):

| Fixture | Commits on `main` | Human authors | Bot | Branches besides `main` | Tags |
|---|---|---|---|---|---|
| service-py | 16 | Ada Lovelace, Grace Hopper, Linus Torvalds | `dependabot[bot]` | `hotfix/ledger-rounding` (unmerged, last commit 2026-04-10) | `v0.1.0` (2024-10-05), `v0.2.0` (2026-02-20) |
| web-ts | 10 | Dan Kim, Eve Adams, Faye Wong | `github-actions[bot]` | `release/1.2` (unmerged, 2026-04-15) | `v1.0.0` (2025-08-19), `v1.1.0` (2026-02-28) |
| mixed-decoys | 6 | Hal Finney, Ivy Lee | `renovate[bot]` | `staging` (unmerged, 2026-03-09) | `v0.1.0` (2025-07-22), `v0.2.0` (2026-04-20) |

service-py per-file facts over a 240-month window (every commit in the window): `src/pay/refund.py` churn 7 (c1, c6, c7, c9, c11, c14, c16), all by Ada, `bugfix_share` 2/7, `untested_change_share` 4/7 (c7, c9, c11, c16 carry no tests-class file); `src/pay/ledger.py` churn 7 (c1, c5, c6, c7, c8, c9, c11) by Ada (5), Grace (c5), Linus (c8); repo-wide commit counts Ada 7, Linus 5, Grace 3; the pair shares 5 commits (c1, c6, c7, c9, c11), ratio 5/7; `src/pay/ledger.py` and `src/pay/models.py` share only c1 and c8; `src/pay/gateway.py` churn 2, one author (Linus), `migration_commits` 1 (c12), no mapped test; `tests/test_ledger.py` `flaky_commits` 1 (c15); `src/pay/old_helper.py` is in c1 and deleted in c17 so it has history but is absent at HEAD; `docs/übersicht.md` is a non-ASCII path touched once. Fixture dates are fixed in the past, so tests that count churn pass `churn_months=240` (every commit inside) or `churn_months=1` (none inside); never assert on the default 12-month window.

**Spec:** 6 (corpus contents per fixture, `planted.json` schema, multi-language requirement), 4.3 (each rule needs a positive in two languages), 2.3 (traps the decoys exercise).

**Confidence:** 90% (content is fixed text; the risk is a line number in `planted.json` drifting from the file, mitigated by Step 10's assertion that every planted path and line range exists in the replayed tree).

- [ ] **Step 1: Exclude the corpus from ruff and write the failing corpus test**

In `pyproject.toml` change the `[tool.ruff]` table to:

```toml
[tool.ruff]
line-length = 100
target-version = "py311"
extend-exclude = ["skills/tech-debt-scan/tests/fixtures/corpus"]
```

Append to `skills/tech-debt-scan/tests/conftest.py`:

```python
import pytest


@pytest.fixture(scope="session")
def service_py_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from make_history import replay_fixture

    return replay_fixture("service-py", tmp_path_factory.mktemp("service-py"))


@pytest.fixture(scope="session")
def web_ts_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from make_history import replay_fixture

    return replay_fixture("web-ts", tmp_path_factory.mktemp("web-ts"))


@pytest.fixture(scope="session")
def mixed_decoys_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from make_history import replay_fixture

    return replay_fixture("mixed-decoys", tmp_path_factory.mktemp("mixed-decoys"))
```

(`import pytest` sits after the `sys.path` loop; ruff E402 is not in the selected rule set, and the loop must run before any helper import. The `replay_fixture` import is inside each fixture for the same reason.)

Create `skills/tech-debt-scan/tests/test_corpus.py`:

```python
"""The three-fixture corpus replays and matches its planted.json (spec 6)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from make_history import CORPUS_ROOT, git_output

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

EXPECTED_COMMITS = {"service-py": 16, "web-ts": 10, "mixed-decoys": 6}
EXPECTED_TAGS = {
    "service-py": ["v0.1.0", "v0.2.0"],
    "web-ts": ["v1.0.0", "v1.1.0"],
    "mixed-decoys": ["v0.1.0", "v0.2.0"],
}
EXPECTED_BRANCHES = {
    "service-py": ["hotfix/ledger-rounding", "main"],
    "web-ts": ["main", "release/1.2"],
    "mixed-decoys": ["main", "staging"],
}


def _tree(root: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for path in root.rglob("*"):
        if path.is_file() and ".git" not in path.relative_to(root).parts:
            out[path.relative_to(root).as_posix()] = path.read_bytes()
    return out


@pytest.fixture(params=["service-py", "web-ts", "mixed-decoys"])
def corpus(request: pytest.FixtureRequest) -> tuple[str, Path]:
    name = str(request.param)
    fixture_name = {
        "service-py": "service_py_repo",
        "web-ts": "web_ts_repo",
        "mixed-decoys": "mixed_decoys_repo",
    }[name]
    repo: Path = request.getfixturevalue(fixture_name)
    return name, repo


def test_commit_count_tags_and_branches(corpus: tuple[str, Path]) -> None:
    name, repo = corpus
    assert len(git_output(repo, "log", "--format=%H").split()) == EXPECTED_COMMITS[name]
    assert git_output(repo, "tag", "--sort=creatordate").split() == EXPECTED_TAGS[name]
    heads = git_output(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()
    assert heads == EXPECTED_BRANCHES[name]
    assert git_output(repo, "symbolic-ref", "--short", "HEAD").strip() == "main"


def test_replayed_tree_equals_files_dir(corpus: tuple[str, Path]) -> None:
    name, repo = corpus
    assert _tree(repo) == _tree(CORPUS_ROOT / name / "files")


def test_planted_paths_and_lines_exist(corpus: tuple[str, Path]) -> None:
    name, repo = corpus
    planted = json.loads((CORPUS_ROOT / name / "planted.json").read_text(encoding="utf-8"))
    assert planted["planted"], "every fixture plants at least one item"
    assert planted["decoys"], "every fixture plants at least one decoy"
    for item in planted["planted"]:
        assert set(item) >= {"id", "family", "type_id", "path", "lines", "expect_tier"}
        if item["path"] is None:
            continue
        target = repo / item["path"]
        assert target.is_file(), item["id"]
        line_count = target.read_bytes().count(b"\n")
        start, end = item["lines"]
        assert 1 <= start <= end <= line_count, f"{item['id']}: {start}-{end} of {line_count}"
    for decoy in planted["decoys"]:
        assert set(decoy) >= {"id", "family", "path", "why"}
        assert (repo / decoy["path"]).is_file(), decoy["id"]
```

- [ ] **Step 2: Run the corpus test to verify it fails**

Run: `pytest skills/tech-debt-scan/tests/test_corpus.py -v`
Expected: every test ERRORs at fixture setup with `FileNotFoundError: [Errno 2] No such file or directory: '...corpus/service-py/history.yaml'` (raised from `history_yaml.read_text` inside `replay_history`).

- [ ] **Step 3: Create the `service-py` tree**

Create every file below under `skills/tech-debt-scan/tests/fixtures/corpus/service-py/files/`. Write each with LF endings and a trailing newline (the tree is compared byte for byte with the replayed repository).

`README.md`:

```markdown
# pay-service

Refund and ledger service.

## Run

    python -m pay.refund --help

Code lives in `src/pay/refund.py`; the design is in `docs/adr/0001-ledger.md`.
The old `src/pay/exporter.py` job was removed in 0.1.0.
```

`CHANGELOG.md`:

```markdown
# Changelog

## 0.1.0 - 2024-10-05

- initial refund and ledger flow
```

`pyproject.toml`:

```toml
[project]
name = "pay-service"
version = "0.2.0"
requires-python = ">=3.11"
dependencies = ["requests>=2.31"]

[tool.coverage.report]
fail_under = 80
```

`requirements.txt`:

```
requests==2.32.3
```

`setup.py`:

```python
"""Legacy packaging shim; pyproject.toml is the source of truth."""
from setuptools import setup

setup(name="pay-service")
```

`Dockerfile`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y curl
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY src/ ./src
CMD ["python", "-m", "pay.refund"]
```

`.github/workflows/ci.yml`:

```yaml
name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: pytest -q
```

`.github/workflows/release.yml`:

```yaml
name: release
on:
  push:
    tags: ["v*"]
jobs:
  publish:
    runs-on: ubuntu-22.04
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11
      - run: python -m build
      - run: twine upload dist/*
```

`docs/adr/0001-ledger.md`:

```markdown
# ADR 0001: append-only ledger

Status: accepted, 2024-10-05.

We store ledger entries as JSON lines in `src/pay/ledger.py` and never rewrite
history; reversals are new entries.
```

`docs/übersicht.md` (the file name contains U+00FC; save as UTF-8):

```markdown
# Übersicht

Kurze Notizen zum Zahlungsdienst.
```

`src/pay/__init__.py`:

```python
"""Payment service package."""
```

`src/pay/models.py`:

```python
"""Ledger and refund records."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Entry:
    account: str
    amount_cents: int
    reason: str = ""


@dataclass
class Refund:
    order_id: str
    amount_cents: int
    reason_code: str = "other"
```

`src/pay/utils.py`:

```python
"""Small helpers shared by the payment modules."""
from __future__ import annotations

import hashlib


def cents(amount: float) -> int:
    return int(round(amount))


def fingerprint(order_id: str) -> str:
    return hashlib.md5(order_id.encode("utf-8")).hexdigest()
```

`src/pay/ledger.py` (the `record =` line survives from Linus's c8 so blame shows more than one author):

```python
"""Append-only ledger stored as JSON lines."""
from __future__ import annotations

import json
from pathlib import Path

from pay.models import Entry

LEDGER_PATH = Path("ledger.jsonl")


def post(entry: Entry, path: Path = LEDGER_PATH) -> None:
    record = {"account": entry.account, "amount": int(entry.amount_cents), "reason": entry.reason}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def balance(account: str, path: Path = LEDGER_PATH) -> int:
    total = 0
    if not path.exists():
        return total
    for raw in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(raw)
        if record["account"] == account:
            total += int(record["amount"])
    return total


def reverse(entry: Entry) -> Entry:
    return Entry(account=entry.account, amount_cents=-entry.amount_cents, reason="reversal")
```

`src/pay/gateway.py` (line 11 is the seeded live credential; the `requests.post(` call spans lines 20 to 25 and has no `timeout=`; line 24 disables TLS verification):

```python
"""HTTP client for the payment gateway (v2 API)."""
from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)

API_BASE = "https://gateway.example.com/v2"
api_key = "sk_live_51H8f2kL9mN3pQ7rS4tU6vW"
CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}


class Gateway:
    def __init__(self, base: str = API_BASE) -> None:
        self.base = base

    def refund(self, order_id: str, amount_cents: int) -> bool:
        response = requests.post(
            f"{self.base}/refunds",
            json={"order": order_id, "amount": amount_cents},
            headers={"Authorization": f"Bearer {api_key}", **CORS_HEADERS},
            verify=False,
        )
        log.info("gateway responded %s", response.status_code)
        return response.status_code == 200
```

`src/pay/refund.py` (the hotspot; lines 31 to 34 are the empty except around the ledger write, line 35 the FIXME that blame dates to 2024-08-15, line 41 the `print(`):

```python
"""Refund workflow: validate, post to the ledger, notify the gateway."""
from __future__ import annotations

import logging

from pay import ledger
from pay.gateway import Gateway
from pay.models import Entry, Refund
from pay.utils import cents

log = logging.getLogger(__name__)

REASON_CODES = ("other", "duplicate", "fraud", "requested")
_seen: set[str] = set()


def validate(refund: Refund) -> None:
    if refund.amount_cents <= 0:
        raise ValueError("refund amount must be positive")
    if refund.reason_code not in REASON_CODES:
        raise ValueError(f"unknown reason code: {refund.reason_code}")


def issue(refund: Refund, gateway: Gateway) -> bool:
    """Post the refund to the ledger, then ask the gateway to move the money."""
    validate(refund)
    if refund.order_id in _seen:
        return False
    _seen.add(refund.order_id)
    entry = Entry(account=refund.order_id, amount_cents=-refund.amount_cents, reason=refund.reason_code)
    try:
        ledger.post(entry)
    except Exception:
        pass
    # FIXME: the gateway retries on our behalf, so a duplicate refund can post twice
    try:
        accepted = gateway.refund(refund.order_id, refund.amount_cents)
    except OSError as exc:
        log.exception("gateway unreachable for %s", refund.order_id)
        raise RuntimeError("gateway unreachable") from exc
    print(f"refund {refund.order_id} accepted={accepted}")
    return accepted


def issue_partial(refund: Refund, gateway: Gateway, fraction: float) -> bool:
    amount = cents(refund.amount_cents * fraction / 100)
    partial = Refund(order_id=refund.order_id, amount_cents=amount, reason_code=refund.reason_code)
    return issue(partial, gateway)


def audit_trail(refund: Refund) -> list[str]:
    return [f"{refund.order_id}:{refund.amount_cents}:{refund.reason_code}"]
```

`src/pay/legacy_export.py` (line 11 string-built SQL with `# nosec`, line 13 `shell=True` with `# noqa`, lines 17 to 19 commented-out code):

```python
"""Legacy CSV export kept for the v1 reporting job."""
from __future__ import annotations

import sqlite3
import subprocess

# TODO(#42): delete once finance moves to the v2 report
def export_v1(refund_id: str, db: str = "refunds.db") -> list[tuple[str, int]]:
    con = sqlite3.connect(db)
    cur = con.cursor()
    cur.execute(f"SELECT id, amount FROM refunds WHERE id = '{refund_id}'")  # nosec
    rows = cur.fetchall()
    subprocess.run("mail -s report finance@example.com", shell=True)  # noqa: S602
    return rows


# def export_v0(refund_id):
#     rows = fetch(refund_id)
#     return rows
```

`tests/conftest.py`:

```python
"""Shared fixtures."""
from __future__ import annotations

import pytest

from pay.models import Refund


@pytest.fixture
def refund() -> Refund:
    return Refund(order_id="o-1", amount_cents=500)
```

`tests/test_refund.py`:

```python
"""Refund workflow tests."""
from __future__ import annotations

import pytest

from pay import refund as refund_mod
from pay.models import Refund


def test_validate_rejects_zero() -> None:
    with pytest.raises(ValueError):
        refund_mod.validate(Refund(order_id="o-1", amount_cents=0))


def test_audit_trail_format(refund: Refund) -> None:
    assert refund_mod.audit_trail(refund) == ["o-1:500:other"]


@pytest.mark.skip(reason="gateway stub not written yet")
def test_issue_calls_gateway() -> None:
    raise NotImplementedError
```

`tests/test_ledger.py` (line 13 sleeps; the test at lines 17 to 18 has no assertion):

```python
"""Ledger tests."""
from __future__ import annotations

import time
from pathlib import Path

from pay import ledger
from pay.models import Entry


def test_post_then_balance(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    ledger.post(Entry(account="a", amount_cents=100), path)
    time.sleep(0.05)  # flaky on CI without this; retried in the workflow
    assert ledger.balance("a", path) == 100


def test_reverse_smoke() -> None:
    ledger.reverse(Entry(account="a", amount_cents=100))
```

`tests/fixtures/seed.py`:

```python
"""Seed data for tests; duplicated on purpose so each test owns its copy."""
api_key = "sk_test_placeholder_xxx_do_not_use"

SEED_A = [{"account": "a", "amount": 100}, {"account": "b", "amount": 200}]
SEED_B = [{"account": "a", "amount": 100}, {"account": "b", "amount": 200}]
```

- [ ] **Step 4: Write `service-py/history.yaml`**

Create `skills/tech-debt-scan/tests/fixtures/corpus/service-py/history.yaml`. Every intermediate version is literal; `"@final"` copies from `files/`. The FIXME line in `src/pay/refund.py` is byte-identical in every version so `git blame -w` attributes it to c1.

```yaml
commits:
  - author: "Ada Lovelace <ada@example.com>"
    date: "2024-08-15T10:00:00+00:00"
    subject: "feat: initial payment service"
    files:
      README.md: "@final"
      pyproject.toml: "@final"
      requirements.txt: |
        requests==2.31.0
      setup.py: "@final"
      .github/workflows/ci.yml: "@final"
      src/pay/__init__.py: "@final"
      src/pay/utils.py: "@final"
      src/pay/legacy_export.py: "@final"
      src/pay/old_helper.py: |
        """Retired helper."""


        def helper() -> int:
            return 1
      src/pay/models.py: |
        """Ledger and refund records."""
        from __future__ import annotations

        from dataclasses import dataclass


        @dataclass
        class Entry:
            account: str
            amount_cents: int


        @dataclass
        class Refund:
            order_id: str
            amount_cents: int
      src/pay/ledger.py: |
        """Append-only ledger."""
        from __future__ import annotations

        import json
        from pathlib import Path

        from pay.models import Entry

        LEDGER_PATH = Path("ledger.jsonl")


        def post(entry: Entry, path: Path = LEDGER_PATH) -> None:
            record = {"account": entry.account, "amount": entry.amount_cents}
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")
      src/pay/refund.py: |
        """Refund workflow."""
        from __future__ import annotations

        from pay import ledger
        from pay.models import Entry, Refund


        def validate(refund: Refund) -> None:
            if refund.amount_cents <= 0:
                raise ValueError("refund amount must be positive")


        def issue(refund: Refund) -> None:
            validate(refund)
            entry = Entry(account=refund.order_id, amount_cents=-refund.amount_cents)
            ledger.post(entry)
            # FIXME: the gateway retries on our behalf, so a duplicate refund can post twice
      tests/conftest.py: "@final"
      tests/fixtures/seed.py: "@final"
      tests/test_ledger.py: |
        """Ledger tests."""
        from __future__ import annotations

        from pathlib import Path

        from pay import ledger
        from pay.models import Entry


        def test_post_writes_a_line(tmp_path: Path) -> None:
            path = tmp_path / "ledger.jsonl"
            ledger.post(Entry(account="a", amount_cents=100), path)
            assert path.read_text(encoding="utf-8").count("\n") == 1
  - author: "Grace Hopper <grace@example.com>"
    date: "2024-09-01T09:00:00+00:00"
    subject: "chore: add Dockerfile and release workflow"
    files:
      Dockerfile: "@final"
      .github/workflows/release.yml: "@final"
  - author: "Linus Torvalds <linus@example.com>"
    date: "2024-10-05T09:00:00+00:00"
    subject: "docs: changelog, ledger ADR and overview"
    files:
      CHANGELOG.md: "@final"
      docs/adr/0001-ledger.md: "@final"
      docs/übersicht.md: "@final"
    tag: v0.1.0
  - author: "Linus Torvalds <linus@example.com>"
    date: "2025-01-20T09:00:00+00:00"
    subject: "feat: gateway client"
    files:
      src/pay/gateway.py: |
        """HTTP client for the payment gateway."""
        from __future__ import annotations

        import requests

        API_BASE = "https://gateway.example.com/v1"


        class Gateway:
            def __init__(self, base: str = API_BASE) -> None:
                self.base = base

            def refund(self, order_id: str, amount_cents: int) -> bool:
                response = requests.post(f"{self.base}/refunds", json={"order": order_id}, timeout=10)
                return response.status_code == 200
  - author: "Grace Hopper <grace@example.com>"
    date: "2025-03-10T09:00:00+00:00"
    subject: "fix: ledger rounding bug"
    files:
      src/pay/ledger.py: |
        """Append-only ledger."""
        from __future__ import annotations

        import json
        from pathlib import Path

        from pay.models import Entry

        LEDGER_PATH = Path("ledger.jsonl")


        def post(entry: Entry, path: Path = LEDGER_PATH) -> None:
            record = {"account": entry.account, "amount": int(entry.amount_cents)}
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")
  - author: "Ada Lovelace <ada@example.com>"
    date: "2025-09-20T09:00:00+00:00"
    subject: "feat: partial refunds"
    files:
      src/pay/refund.py: |
        """Refund workflow."""
        from __future__ import annotations

        from pay import ledger
        from pay.models import Entry, Refund
        from pay.utils import cents


        def validate(refund: Refund) -> None:
            if refund.amount_cents <= 0:
                raise ValueError("refund amount must be positive")


        def issue(refund: Refund) -> None:
            validate(refund)
            entry = Entry(account=refund.order_id, amount_cents=-refund.amount_cents)
            ledger.post(entry)
            # FIXME: the gateway retries on our behalf, so a duplicate refund can post twice


        def issue_partial(refund: Refund, fraction: float) -> None:
            amount = cents(refund.amount_cents * fraction / 100)
            issue(Refund(order_id=refund.order_id, amount_cents=amount))
      src/pay/ledger.py: |
        """Append-only ledger."""
        from __future__ import annotations

        import json
        from pathlib import Path

        from pay.models import Entry

        LEDGER_PATH = Path("ledger.jsonl")


        def post(entry: Entry, path: Path = LEDGER_PATH) -> None:
            record = {"account": entry.account, "amount": int(entry.amount_cents)}
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")


        def balance(account: str, path: Path = LEDGER_PATH) -> int:
            total = 0
            for raw in path.read_text(encoding="utf-8").splitlines():
                record = json.loads(raw)
                if record["account"] == account:
                    total += int(record["amount"])
            return total
      tests/test_refund.py: |
        """Refund workflow tests."""
        from __future__ import annotations

        import pytest

        from pay import refund as refund_mod
        from pay.models import Refund


        def test_validate_rejects_zero() -> None:
            with pytest.raises(ValueError):
                refund_mod.validate(Refund(order_id="o-1", amount_cents=0))
  - author: "Ada Lovelace <ada@example.com>"
    date: "2025-10-14T09:00:00+00:00"
    subject: "fix: refund double-post regression"
    files:
      src/pay/refund.py: |
        """Refund workflow."""
        from __future__ import annotations

        from pay import ledger
        from pay.models import Entry, Refund
        from pay.utils import cents

        _seen: set[str] = set()


        def validate(refund: Refund) -> None:
            if refund.amount_cents <= 0:
                raise ValueError("refund amount must be positive")


        def issue(refund: Refund) -> bool:
            validate(refund)
            if refund.order_id in _seen:
                return False
            _seen.add(refund.order_id)
            entry = Entry(account=refund.order_id, amount_cents=-refund.amount_cents)
            ledger.post(entry)
            # FIXME: the gateway retries on our behalf, so a duplicate refund can post twice
            return True


        def issue_partial(refund: Refund, fraction: float) -> bool:
            amount = cents(refund.amount_cents * fraction / 100)
            return issue(Refund(order_id=refund.order_id, amount_cents=amount))
      src/pay/ledger.py: |
        """Append-only ledger."""
        from __future__ import annotations

        import json
        from pathlib import Path

        from pay.models import Entry

        LEDGER_PATH = Path("ledger.jsonl")


        def post(entry: Entry, path: Path = LEDGER_PATH) -> None:
            record = {"account": entry.account, "amount": int(entry.amount_cents)}
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")


        def balance(account: str, path: Path = LEDGER_PATH) -> int:
            total = 0
            if not path.exists():
                return total
            for raw in path.read_text(encoding="utf-8").splitlines():
                record = json.loads(raw)
                if record["account"] == account:
                    total += int(record["amount"])
            return total
  - author: "Linus Torvalds <linus@example.com>"
    date: "2025-11-02T09:00:00+00:00"
    subject: "refactor: ledger entry model"
    files:
      src/pay/models.py: "@final"
      src/pay/ledger.py: |
        """Append-only ledger."""
        from __future__ import annotations

        import json
        from pathlib import Path

        from pay.models import Entry

        LEDGER_PATH = Path("ledger.jsonl")


        def post(entry: Entry, path: Path = LEDGER_PATH) -> None:
            record = {"account": entry.account, "amount": int(entry.amount_cents), "reason": entry.reason}
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")


        def balance(account: str, path: Path = LEDGER_PATH) -> int:
            total = 0
            if not path.exists():
                return total
            for raw in path.read_text(encoding="utf-8").splitlines():
                record = json.loads(raw)
                if record["account"] == account:
                    total += int(record["amount"])
            return total
  - author: "Ada Lovelace <ada@example.com>"
    date: "2025-12-08T09:00:00+00:00"
    subject: "feat: refund reason codes"
    files:
      src/pay/refund.py: |
        """Refund workflow."""
        from __future__ import annotations

        from pay import ledger
        from pay.models import Entry, Refund
        from pay.utils import cents

        REASON_CODES = ("other", "duplicate", "fraud", "requested")
        _seen: set[str] = set()


        def validate(refund: Refund) -> None:
            if refund.amount_cents <= 0:
                raise ValueError("refund amount must be positive")
            if refund.reason_code not in REASON_CODES:
                raise ValueError(f"unknown reason code: {refund.reason_code}")


        def issue(refund: Refund) -> bool:
            validate(refund)
            if refund.order_id in _seen:
                return False
            _seen.add(refund.order_id)
            entry = Entry(account=refund.order_id, amount_cents=-refund.amount_cents, reason=refund.reason_code)
            ledger.post(entry)
            # FIXME: the gateway retries on our behalf, so a duplicate refund can post twice
            return True


        def issue_partial(refund: Refund, fraction: float) -> bool:
            amount = cents(refund.amount_cents * fraction / 100)
            partial = Refund(order_id=refund.order_id, amount_cents=amount, reason_code=refund.reason_code)
            return issue(partial)
      src/pay/ledger.py: |
        """Append-only ledger."""
        from __future__ import annotations

        import json
        from pathlib import Path

        from pay.models import Entry

        LEDGER_PATH = Path("ledger.jsonl")


        def post(entry: Entry, path: Path = LEDGER_PATH) -> None:
            record = {"account": entry.account, "amount": int(entry.amount_cents), "reason": entry.reason}
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")


        def balance(account: str, path: Path = LEDGER_PATH) -> int:
            total = 0
            if not path.exists():
                return total
            for raw in path.read_text(encoding="utf-8").splitlines():
                record = json.loads(raw)
                if record["account"] == account:
                    total += int(record["amount"])
            return total


        def reverse(entry: Entry) -> Entry:
            return Entry(account=entry.account, amount_cents=-entry.amount_cents, reason="reversal")
  - author: "dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>"
    date: "2026-01-15T09:00:00+00:00"
    subject: "chore(deps): bump requests from 2.31.0 to 2.32.3"
    files:
      requirements.txt: "@final"
  - author: "Ada Lovelace <ada@example.com>"
    date: "2026-02-20T09:00:00+00:00"
    subject: "fix: tolerate ledger write failures during refund"
    files:
      src/pay/refund.py: |
        """Refund workflow."""
        from __future__ import annotations

        import logging

        from pay import ledger
        from pay.gateway import Gateway
        from pay.models import Entry, Refund
        from pay.utils import cents

        log = logging.getLogger(__name__)

        REASON_CODES = ("other", "duplicate", "fraud", "requested")
        _seen: set[str] = set()


        def validate(refund: Refund) -> None:
            if refund.amount_cents <= 0:
                raise ValueError("refund amount must be positive")
            if refund.reason_code not in REASON_CODES:
                raise ValueError(f"unknown reason code: {refund.reason_code}")


        def issue(refund: Refund, gateway: Gateway) -> bool:
            validate(refund)
            if refund.order_id in _seen:
                return False
            _seen.add(refund.order_id)
            entry = Entry(account=refund.order_id, amount_cents=-refund.amount_cents, reason=refund.reason_code)
            try:
                ledger.post(entry)
            except Exception:
                pass
            # FIXME: the gateway retries on our behalf, so a duplicate refund can post twice
            try:
                accepted = gateway.refund(refund.order_id, refund.amount_cents)
            except OSError as exc:
                log.exception("gateway unreachable for %s", refund.order_id)
                raise RuntimeError("gateway unreachable") from exc
            return accepted


        def issue_partial(refund: Refund, gateway: Gateway, fraction: float) -> bool:
            amount = cents(refund.amount_cents * fraction / 100)
            partial = Refund(order_id=refund.order_id, amount_cents=amount, reason_code=refund.reason_code)
            return issue(partial, gateway)
      src/pay/ledger.py: "@final"
    tag: v0.2.0
  - author: "Linus Torvalds <linus@example.com>"
    date: "2026-03-30T09:00:00+00:00"
    subject: "feat: migrate gateway to v2 API"
    files:
      src/pay/gateway.py: "@final"
  - author: "Grace Hopper <grace@example.com>"
    date: "2026-04-10T09:00:00+00:00"
    subject: "hotfix: ledger rounding for partial refunds"
    branch: hotfix/ledger-rounding
    files:
      src/pay/ledger.py: |
        """Append-only ledger stored as JSON lines."""
        from __future__ import annotations

        import json
        from pathlib import Path

        from pay.models import Entry

        LEDGER_PATH = Path("ledger.jsonl")


        def post(entry: Entry, path: Path = LEDGER_PATH) -> None:
            record = {"account": entry.account, "amount": round(entry.amount_cents), "reason": entry.reason}
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")


        def balance(account: str, path: Path = LEDGER_PATH) -> int:
            total = 0
            if not path.exists():
                return total
            for raw in path.read_text(encoding="utf-8").splitlines():
                record = json.loads(raw)
                if record["account"] == account:
                    total += int(record["amount"])
            return total


        def reverse(entry: Entry) -> Entry:
            return Entry(account=entry.account, amount_cents=-entry.amount_cents, reason="reversal")
  - author: "Ada Lovelace <ada@example.com>"
    date: "2026-05-11T09:00:00+00:00"
    subject: "feat: refund audit trail"
    branch: main
    files:
      src/pay/refund.py: |
        """Refund workflow."""
        from __future__ import annotations

        import logging

        from pay import ledger
        from pay.gateway import Gateway
        from pay.models import Entry, Refund
        from pay.utils import cents

        log = logging.getLogger(__name__)

        REASON_CODES = ("other", "duplicate", "fraud", "requested")
        _seen: set[str] = set()


        def validate(refund: Refund) -> None:
            if refund.amount_cents <= 0:
                raise ValueError("refund amount must be positive")
            if refund.reason_code not in REASON_CODES:
                raise ValueError(f"unknown reason code: {refund.reason_code}")


        def issue(refund: Refund, gateway: Gateway) -> bool:
            validate(refund)
            if refund.order_id in _seen:
                return False
            _seen.add(refund.order_id)
            entry = Entry(account=refund.order_id, amount_cents=-refund.amount_cents, reason=refund.reason_code)
            try:
                ledger.post(entry)
            except Exception:
                pass
            # FIXME: the gateway retries on our behalf, so a duplicate refund can post twice
            try:
                accepted = gateway.refund(refund.order_id, refund.amount_cents)
            except OSError as exc:
                log.exception("gateway unreachable for %s", refund.order_id)
                raise RuntimeError("gateway unreachable") from exc
            print(f"refund {refund.order_id} accepted={accepted}")
            return accepted


        def issue_partial(refund: Refund, gateway: Gateway, fraction: float) -> bool:
            amount = cents(refund.amount_cents * fraction / 100)
            partial = Refund(order_id=refund.order_id, amount_cents=amount, reason_code=refund.reason_code)
            return issue(partial, gateway)


        def audit_trail(refund: Refund) -> list[str]:
            return [f"{refund.order_id}:{refund.amount_cents}:{refund.reason_code}"]
      tests/test_refund.py: "@final"
  - author: "Grace Hopper <grace@example.com>"
    date: "2026-06-03T09:00:00+00:00"
    subject: "test: retry flaky ledger test"
    files:
      tests/test_ledger.py: "@final"
  - author: "Ada Lovelace <ada@example.com>"
    date: "2026-06-22T09:00:00+00:00"
    subject: "chore: tidy refund helpers"
    files:
      src/pay/refund.py: "@final"
  - author: "Linus Torvalds <linus@example.com>"
    date: "2026-07-01T09:00:00+00:00"
    subject: "chore: remove old helper"
    delete: [src/pay/old_helper.py]
```

- [ ] **Step 5: Write `service-py/planted.json`**

Create `skills/tech-debt-scan/tests/fixtures/corpus/service-py/planted.json` (spec 6 schema; `path: null` marks a repository-level fact whose finding carries no file):

```json
{
  "planted": [
    {"id": "p1", "family": "error-masking", "type_id": "TD-13", "path": "src/pay/refund.py", "lines": [31, 34], "expect_tier": "A"},
    {"id": "p2", "family": "half-finished", "type_id": "TD-22", "path": "src/pay/refund.py", "lines": [35, 35], "expect_tier": "B"},
    {"id": "p3", "family": "security", "type_id": "TD-03", "path": "src/pay/gateway.py", "lines": [11, 11], "expect_tier": "B"},
    {"id": "p4", "family": "security", "type_id": "TD-03", "path": "src/pay/gateway.py", "lines": [24, 24], "expect_tier": "B"},
    {"id": "p5", "family": "half-finished", "type_id": "TD-34", "path": "src/pay/gateway.py", "lines": [20, 25], "expect_tier": "B"},
    {"id": "p6", "family": "test-gaps", "type_id": "TD-04", "path": "src/pay/gateway.py", "lines": [1, 27], "expect_tier": "B"},
    {"id": "p7", "family": "ownership", "type_id": "TD-16", "path": "src/pay/refund.py", "lines": [1, 52], "expect_tier": "A"},
    {"id": "p8", "family": "pipeline-infra", "type_id": "TD-19", "path": "Dockerfile", "lines": [1, 7], "expect_tier": "A"},
    {"id": "p9", "family": "pipeline-infra", "type_id": "TD-14", "path": ".github/workflows/ci.yml", "lines": [4, 12], "expect_tier": "A"},
    {"id": "p10", "family": "pipeline-infra", "type_id": "TD-14", "path": ".github/workflows/release.yml", "lines": [5, 12], "expect_tier": "A"},
    {"id": "p11", "family": "dependency-debt", "type_id": "TD-02", "path": "pyproject.toml", "lines": [1, 8], "expect_tier": "A"},
    {"id": "p12", "family": "security", "type_id": "TD-03", "path": "src/pay/legacy_export.py", "lines": [11, 11], "expect_tier": "B"},
    {"id": "p13", "family": "security", "type_id": "TD-03", "path": "src/pay/legacy_export.py", "lines": [13, 13], "expect_tier": "B"},
    {"id": "p14", "family": "dead-code", "type_id": "TD-09", "path": "src/pay/legacy_export.py", "lines": [1, 19], "expect_tier": "B"},
    {"id": "p15", "family": "dead-code", "type_id": "TD-30", "path": "src/pay/legacy_export.py", "lines": [17, 19], "expect_tier": "B"},
    {"id": "p16", "family": "security", "type_id": "TD-03", "path": "src/pay/utils.py", "lines": [11, 11], "expect_tier": "B"},
    {"id": "p17", "family": "test-quality", "type_id": "TD-12", "path": "tests/test_ledger.py", "lines": [13, 13], "expect_tier": "B"},
    {"id": "p18", "family": "test-quality", "type_id": "TD-18", "path": "tests/test_ledger.py", "lines": [17, 18], "expect_tier": "B"},
    {"id": "p19", "family": "pipeline-infra", "type_id": "TD-27", "path": null, "lines": [0, 0], "expect_tier": "A"},
    {"id": "p20", "family": "doc-drift", "type_id": "TD-08", "path": "README.md", "lines": [10, 10], "expect_tier": "B"}
  ],
  "decoys": [
    {"id": "d1", "family": "duplication", "path": "tests/fixtures/seed.py", "why": "intentional fixture duplication in the tests path class"},
    {"id": "d2", "family": "security", "path": "tests/fixtures/seed.py", "why": "placeholder credential (sk_test, placeholder, xxx) in a test fixture"},
    {"id": "d3", "family": "dependency-debt", "path": "requirements.txt", "why": "a pinned requirements file has no lockfile ecosystem and must not be flagged"},
    {"id": "d4", "family": "dead-code", "path": "src/pay/__init__.py", "why": "package file: fan-in is never resolved for it and it is not dead"},
    {"id": "d5", "family": "dead-code", "path": "setup.py", "why": "harness file run by name; fan-in 0 is not dead"},
    {"id": "d6", "family": "test-gaps", "path": "tests/conftest.py", "why": "harness file, not an untested module"},
    {"id": "d7", "family": "ownership", "path": "src/pay/ledger.py", "why": "three human authors on the file; not a knowledge island"},
    {"id": "d8", "family": "half-finished", "path": "src/pay/legacy_export.py", "why": "TODO carries ticket reference #42; not an untracked marker"}
  ]
}
```

- [ ] **Step 6: Create the `web-ts` tree**

Create every file below under `skills/tech-debt-scan/tests/fixtures/corpus/web-ts/files/`.

`README.md`:

```markdown
# web-ts

Cart and checkout front end.

    npm test
```

`package.json`:

```json
{
  "name": "web-ts",
  "version": "1.1.0",
  "private": true,
  "scripts": { "build": "tsc -p tsconfig.json", "test": "jest" },
  "dependencies": { "tiny-emitter": "2.1.0" },
  "devDependencies": { "typescript": "5.4.5", "jest": "29.7.0", "eslint": "9.0.0" },
  "jest": { "coverageThreshold": { "global": { "lines": 80 } } }
}
```

`package-lock.json`:

```json
{ "name": "web-ts", "lockfileVersion": 3, "packages": {} }
```

`yarn.lock`:

```
# yarn lockfile v1

tiny-emitter@2.1.0:
  version "2.1.0"
```

`tsconfig.json`:

```json
{ "compilerOptions": { "target": "ES2020", "module": "ES2020", "strict": true }, "include": ["src"] }
```

`tslint.json`:

```json
{ "extends": "tslint:recommended" }
```

`.eslintrc.json`:

```json
{ "extends": "eslint:recommended" }
```

`.github/workflows/ci.yml` (the clean decoy: every CI rule is satisfied):

```yaml
name: ci
on: [push, pull_request]
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-22.04
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11
      - uses: actions/setup-node@60edb5dd545a775178f52524783378180af0d1f8
        with:
          node-version: "20"
          cache: npm
      - uses: nick-fields/retry@7152eba30c6575329ac0576536151aca5a72780e
        with:
          timeout_minutes: 10
          max_attempts: 3
          command: npm test
```

`docs/architecture.md`:

```markdown
# Architecture

`src/cart` owns items and totals, `src/checkout` owns the flow. Pricing and
stock currently import each other through `src/cart/stock.ts`.
```

`src/index.ts`:

```ts
import { addItem, Cart } from "./cart/cart";
import { checkout } from "./checkout/checkout";

export function main(): void {
  const cart: Cart = { items: [] };
  addItem(cart, { sku: "A1", qty: 1 });
  checkout(cart);
}
```

`src/cart/cart.ts`:

```ts
import { priceOf } from "./pricing";

export interface Item {
  sku: string;
  qty: number;
}

export interface Cart {
  items: Item[];
}

export function addItem(cart: Cart, item: Item): void {
  cart.items.push(item);
}

export function total(cart: Cart): number {
  return cart.items.reduce((sum, item) => sum + priceOf(item.sku) * item.qty, 0);
}
```

`src/cart/pricing.ts`:

```ts
import { reserve } from "./stock";

const PRICES: Record<string, number> = { A1: 1000, B2: 2500 };

export function priceOf(sku: string): number {
  reserve(sku, 0);
  return PRICES[sku] ?? 0;
}
```

`src/cart/stock.ts` (line 1 closes the cart, pricing, stock cycle):

```ts
import type { Cart } from "./cart";

const LEVELS: Record<string, number> = { A1: 10, B2: 3 };

export function reserve(sku: string, qty: number): boolean {
  const left = (LEVELS[sku] ?? 0) - qty;
  LEVELS[sku] = left;
  return left >= 0;
}

export function reserveCart(cart: Cart): boolean {
  return cart.items.every((item) => reserve(item.sku, item.qty));
}
```

`src/checkout/checkout.ts` (line 7 reads the permanently-off flag):

```ts
import { Cart, total } from "../cart/cart";
import { priceOf } from "../cart/pricing";
import { isEnabled } from "../flags";
import { legacyFormat } from "../util/format-legacy";

export function checkout(cart: Cart): string {
  if (isEnabled("newCheckout")) {
    return `new:${total(cart)}`;
  }
  const first = cart.items[0];
  const label = first ? legacyFormat(priceOf(first.sku)) : "";
  return `legacy:${label}`;
}
```

`src/flags.ts`:

```ts
const FLAGS: Record<string, boolean> = {
  // newCheckout has been off since launch; the new flow was never finished
  newCheckout: false,
  betaBanner: true,
};

export function isEnabled(name: string): boolean {
  return FLAGS[name] ?? false;
}
```

`src/util/format.ts`:

```ts
export function formatMoney(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}
```

`src/util/format-legacy.ts` (deprecated at line 3, still imported by checkout.ts):

```ts
import { formatMoney } from "./format";

/** @deprecated use formatMoney */
export function legacyFormat(cents: number): string {
  return formatMoney(cents).replace("$", "USD ");
}
```

`src/api/client.ts` (line 9 is a `fetch(` with no `signal` or `timeout`; line 11 is the empty catch):

```ts
import { isEnabled } from "../flags";

const BASE = "https://api.example.com";
const token = process.env.API_TOKEN ?? "";

export async function getJson(path: string): Promise<unknown> {
  const headers = { Authorization: `Bearer ${token}`, "X-Retry": "3" };
  try {
    const response = await fetch(`${BASE}${path}`, { headers });
    return await response.json();
  } catch (e) {}
  if (isEnabled("betaBanner")) {
    console.log("beta banner shown");
  }
  return null;
}
```

`src/api/client-admin.ts` (the near duplicate; its catch references `e` and its fetch has a timeout signal):

```ts
import { isEnabled } from "../flags";

const BASE = "https://admin.example.com";
const token = process.env.ADMIN_TOKEN ?? "";

export async function getAdminJson(path: string): Promise<unknown> {
  const headers = { Authorization: `Bearer ${token}`, "X-Retry": "3" };
  try {
    const response = await fetch(`${BASE}${path}`, {
      headers,
      signal: AbortSignal.timeout(5000),
    });
    return await response.json();
  } catch (e) {
    console.error("admin request failed", e);
    return null;
  }
}

export function adminEnabled(): boolean {
  return isEnabled("adminPanel");
}
```

`src/__tests__/cart.test.ts`:

```ts
import { addItem, total } from "../cart/cart";

test("total sums items", () => {
  const cart = { items: [] as { sku: string; qty: number }[] };
  addItem(cart, { sku: "A1", qty: 2 });
  expect(total(cart)).toBe(2000);
});
```

`src/__tests__/pricing.spec.ts` (line 7 is a skipped test):

```ts
import { priceOf } from "../cart/pricing";

describe("priceOf", () => {
  it("returns zero for unknown skus", () => {
    expect(priceOf("nope")).toBe(0);
  });
  it.skip("applies bulk pricing", () => {
    expect(priceOf("A1")).toBe(900);
  });
});
```

`src/generated/api-types.ts`:

```ts
/* eslint-disable */
// Generated by openapi-typescript. Do not edit.
export interface RefundRequest {
  order: string;
  amount: number;
  reason: string;
}
```

`vendor/tiny-emitter.js`:

```js
// tiny-emitter 2.1.0 (vendored)
function E() {}
E.prototype = { on: function (name, cb) { (this.e || (this.e = {}))[name] = cb; return this; } };
module.exports = E;
```

- [ ] **Step 7: Write `web-ts/history.yaml` and `web-ts/planted.json`**

Create `skills/tech-debt-scan/tests/fixtures/corpus/web-ts/history.yaml`:

```yaml
commits:
  - author: "Dan Kim <dan@example.com>"
    date: "2024-10-01T09:00:00+00:00"
    subject: "feat: cart, pricing and stock"
    files:
      README.md: "@final"
      package.json: |
        {
          "name": "web-ts",
          "version": "1.0.0",
          "private": true,
          "scripts": { "build": "tsc -p tsconfig.json", "test": "jest" },
          "dependencies": { "tiny-emitter": "2.1.0" },
          "devDependencies": { "typescript": "5.4.5", "jest": "29.7.0", "eslint": "9.0.0" },
          "jest": { "coverageThreshold": { "global": { "lines": 80 } } }
        }
      package-lock.json: "@final"
      tsconfig.json: "@final"
      tslint.json: "@final"
      .eslintrc.json: "@final"
      .github/workflows/ci.yml: "@final"
      docs/architecture.md: "@final"
      src/index.ts: |
        import { addItem, Cart } from "./cart/cart";

        export function main(): void {
          const cart: Cart = { items: [] };
          addItem(cart, { sku: "A1", qty: 1 });
        }
      src/cart/cart.ts: "@final"
      src/cart/pricing.ts: "@final"
      src/cart/stock.ts: "@final"
      src/util/format.ts: "@final"
      src/util/format-legacy.ts: "@final"
      src/__tests__/cart.test.ts: "@final"
      src/__tests__/pricing.spec.ts: "@final"
      src/generated/api-types.ts: |
        /* eslint-disable */
        // Generated by openapi-typescript. Do not edit.
        export interface RefundRequest {
          order: string;
          amount: number;
        }
      vendor/tiny-emitter.js: "@final"
  - author: "Eve Adams <eve@example.com>"
    date: "2025-02-11T09:00:00+00:00"
    subject: "feat: api client"
    files:
      src/api/client.ts: |
        const BASE = "https://api.example.com";

        export async function getJson(path: string): Promise<unknown> {
          const response = await fetch(`${BASE}${path}`);
          return await response.json();
        }
  - author: "Eve Adams <eve@example.com>"
    date: "2025-05-05T09:00:00+00:00"
    subject: "feat: admin api client"
    files:
      src/api/client.ts: |
        const BASE = "https://api.example.com";
        const token = process.env.API_TOKEN ?? "";

        export async function getJson(path: string): Promise<unknown> {
          const headers = { Authorization: `Bearer ${token}` };
          const response = await fetch(`${BASE}${path}`, { headers });
          return await response.json();
        }
      src/api/client-admin.ts: |
        const BASE = "https://admin.example.com";
        const token = process.env.ADMIN_TOKEN ?? "";

        export async function getAdminJson(path: string): Promise<unknown> {
          const headers = { Authorization: `Bearer ${token}` };
          const response = await fetch(`${BASE}${path}`, { headers });
          return await response.json();
        }
  - author: "Faye Wong <faye@example.com>"
    date: "2025-08-19T09:00:00+00:00"
    subject: "feat: checkout behind the newCheckout flag"
    files:
      src/checkout/checkout.ts: "@final"
      src/index.ts: "@final"
      src/flags.ts: |
        const FLAGS: Record<string, boolean> = {
          newCheckout: false,
        };

        export function isEnabled(name: string): boolean {
          return FLAGS[name] ?? false;
        }
    tag: v1.0.0
  - author: "Eve Adams <eve@example.com>"
    date: "2025-10-02T09:00:00+00:00"
    subject: "fix: retry headers on api clients"
    files:
      src/api/client.ts: |
        const BASE = "https://api.example.com";
        const token = process.env.API_TOKEN ?? "";

        export async function getJson(path: string): Promise<unknown> {
          const headers = { Authorization: `Bearer ${token}`, "X-Retry": "3" };
          const response = await fetch(`${BASE}${path}`, { headers });
          return await response.json();
        }
      src/api/client-admin.ts: |
        const BASE = "https://admin.example.com";
        const token = process.env.ADMIN_TOKEN ?? "";

        export async function getAdminJson(path: string): Promise<unknown> {
          const headers = { Authorization: `Bearer ${token}`, "X-Retry": "3" };
          const response = await fetch(`${BASE}${path}`, { headers });
          return await response.json();
        }
  - author: "Dan Kim <dan@example.com>"
    date: "2025-11-20T09:00:00+00:00"
    subject: "chore: add yarn lockfile for the CI cache"
    files:
      yarn.lock: "@final"
  - author: "Eve Adams <eve@example.com>"
    date: "2026-01-12T09:00:00+00:00"
    subject: "fix: timeout handling copied between clients"
    files:
      src/api/client.ts: |
        const BASE = "https://api.example.com";
        const token = process.env.API_TOKEN ?? "";

        export async function getJson(path: string): Promise<unknown> {
          const headers = { Authorization: `Bearer ${token}`, "X-Retry": "3" };
          try {
            const response = await fetch(`${BASE}${path}`, { headers });
            return await response.json();
          } catch (e) {}
          return null;
        }
      src/api/client-admin.ts: |
        const BASE = "https://admin.example.com";
        const token = process.env.ADMIN_TOKEN ?? "";

        export async function getAdminJson(path: string): Promise<unknown> {
          const headers = { Authorization: `Bearer ${token}`, "X-Retry": "3" };
          try {
            const response = await fetch(`${BASE}${path}`, {
              headers,
              signal: AbortSignal.timeout(5000),
            });
            return await response.json();
          } catch (e) {
            console.error("admin request failed");
            return null;
          }
        }
  - author: "Faye Wong <faye@example.com>"
    date: "2026-02-28T09:00:00+00:00"
    subject: "feat: flag defaults and 1.1.0"
    files:
      src/flags.ts: "@final"
      package.json: "@final"
    tag: v1.1.0
  - author: "Dan Kim <dan@example.com>"
    date: "2026-04-15T09:00:00+00:00"
    subject: "chore: bump version for 1.2"
    branch: release/1.2
    files:
      package.json: |
        {
          "name": "web-ts",
          "version": "1.2.0",
          "private": true,
          "scripts": { "build": "tsc -p tsconfig.json", "test": "jest" },
          "dependencies": { "tiny-emitter": "2.1.0" },
          "devDependencies": { "typescript": "5.4.5", "jest": "29.7.0", "eslint": "9.0.0" },
          "jest": { "coverageThreshold": { "global": { "lines": 80 } } }
        }
  - author: "Eve Adams <eve@example.com>"
    date: "2026-05-06T09:00:00+00:00"
    subject: "chore: align admin client logging"
    branch: main
    files:
      src/api/client.ts: "@final"
      src/api/client-admin.ts: "@final"
  - author: "github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>"
    date: "2026-06-01T09:00:00+00:00"
    subject: "chore: regenerate api types"
    files:
      src/generated/api-types.ts: "@final"
```

Create `skills/tech-debt-scan/tests/fixtures/corpus/web-ts/planted.json`:

```json
{
  "planted": [
    {"id": "p1", "family": "architecture", "type_id": "TD-07", "path": "src/cart/stock.ts", "lines": [1, 1], "expect_tier": "B"},
    {"id": "p2", "family": "duplication", "type_id": "TD-05", "path": "src/api/client-admin.ts", "lines": [1, 21], "expect_tier": "A"},
    {"id": "p3", "family": "dead-code", "type_id": "TD-17", "path": "src/util/format-legacy.ts", "lines": [3, 6], "expect_tier": "B"},
    {"id": "p4", "family": "dead-code", "type_id": "TD-09", "path": "src/checkout/checkout.ts", "lines": [7, 9], "expect_tier": "B"},
    {"id": "p5", "family": "error-masking", "type_id": "TD-13", "path": "src/api/client.ts", "lines": [11, 11], "expect_tier": "A"},
    {"id": "p6", "family": "half-finished", "type_id": "TD-34", "path": "src/api/client.ts", "lines": [9, 9], "expect_tier": "B"},
    {"id": "p7", "family": "dependency-debt", "type_id": "TD-02", "path": "package.json", "lines": [1, 9], "expect_tier": "A"},
    {"id": "p8", "family": "migration", "type_id": "TD-06", "path": "tslint.json", "lines": [1, 1], "expect_tier": "B"},
    {"id": "p9", "family": "half-finished", "type_id": "TD-22", "path": "src/__tests__/pricing.spec.ts", "lines": [7, 9], "expect_tier": "B"},
    {"id": "p10", "family": "pipeline-infra", "type_id": "TD-27", "path": null, "lines": [0, 0], "expect_tier": "A"}
  ],
  "decoys": [
    {"id": "d1", "family": "pipeline-infra", "path": ".github/workflows/ci.yml", "why": "pinned SHAs, timeout, permissions, cache and a retry action: no CI rule fires"},
    {"id": "d2", "family": "error-masking", "path": "src/api/client-admin.ts", "lines": [14, 17], "why": "catch logs the caught error e and returns; not a swallow"},
    {"id": "d3", "family": "half-finished", "path": "src/api/client-admin.ts", "lines": [9, 12], "why": "fetch carries an AbortSignal timeout"},
    {"id": "d4", "family": "dead-code", "path": "src/index.ts", "why": "entry point; index is a package and stoplist name, fan-in is never resolved"},
    {"id": "d5", "family": "duplication", "path": "src/generated/api-types.ts", "why": "generated file; every family disabled by path class"},
    {"id": "d6", "family": "dead-code", "path": "vendor/tiny-emitter.js", "why": "vendored; every family disabled by path class"},
    {"id": "d7", "family": "security", "path": "src/api/client.ts", "why": "token is read from the environment, not a literal"},
    {"id": "d8", "family": "pipeline-infra", "path": "src/api/client.ts", "why": "console.log with no logger library in the repository is not an observability lead"}
  ]
}
```

- [ ] **Step 8: Create the `mixed-decoys` (Go) tree**

Create every file below under `skills/tech-debt-scan/tests/fixtures/corpus/mixed-decoys/files/`. Go files use tab indentation.

`README.md`:

```markdown
# app

Go service with a lookup table, a string dispatcher and a fluent builder.
```

`go.mod`:

```
module example.com/app

go 1.22
```

`go.sum`:

```
github.com/example/dep v1.2.0 h1:abc=
```

`docs/runbook.md`:

```markdown
# Runbook

## Kill switch

`payments.killswitch` in `internal/flags/flags.go` is a permanent operational
kill switch. It is off in normal operation and is flipped by on-call during an
incident; do not remove it as dead code.
```

`Dockerfile` (line 8 is an unpinned `apk add`; pipefail is set at line 7 so line 9 is a decoy; `USER` is present):

```dockerfile
FROM golang:1.22 AS build
WORKDIR /src
COPY . .
RUN go build -o /app ./cmd/app

FROM alpine:3.20
SHELL ["/bin/sh", "-o", "pipefail", "-c"]
RUN apk add --no-cache curl
RUN curl -sSL https://example.com/install.sh | sh
COPY --from=build /app /app
USER 10001
ENTRYPOINT ["/app"]
```

`docker-compose.yml`:

```yaml
services:
  db:
    image: postgres:16.3
  cache:
    image: redis:7.2
```

`docker-compose.dev.yml` (dev-only path: the `latest` finding drops one severity):

```yaml
services:
  db:
    image: postgres:latest
  mail:
    image: mailhog/mailhog:latest
```

`k8s/deployment.yaml` (no `resources.limits`, a `latest` image, `privileged: true`):

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app
spec:
  template:
    spec:
      containers:
        - name: app
          image: example/app:latest
          securityContext:
            privileged: true
```

`k8s/service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: app
spec:
  ports:
    - port: 80
```

`.github/workflows/ci.yml` (`continue-on-error`, unpinned actions, a `-latest` runner and a commented-out job; permissions, timeout and cache are present):

```yaml
name: ci
on: [push]
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    continue-on-error: true
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: "1.22"
          cache: true
      - run: go test ./...
# lint:
#   runs-on: ubuntu-latest
#   steps:
#     - run: golangci-lint run
```

`cmd/app/main.go` (entry point with no importer; catches, logs and exits non-zero):

```go
package main

import (
	"log"
	"os"

	"example.com/app/internal/build"
	"example.com/app/internal/dispatch"
	"example.com/app/internal/flags"
	"example.com/app/internal/httpc"
	"example.com/app/internal/store"
)

func main() {
	cfg := build.NewConfig().WithName("app").WithPort(8080).Build()
	s, err := store.Open(cfg.Name)
	if err != nil {
		log.Printf("open store: %v", err)
		os.Exit(1)
	}
	defer s.Close()
	if flags.IsEnabled("payments.killswitch") {
		log.Println("payments disabled by kill switch")
	}
	if err := dispatch.Run(os.Args[1:]); err != nil {
		log.Fatal(err)
	}
	_ = httpc.Fetch("https://example.com/health")
}
```

`internal/store/store.go` (lines 27 to 29 swallow the error; lines 31 to 33 log without the error; line 38 builds SQL with `+`; lines 19 to 21 propagate correctly):

```go
package store

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"os"

	"example.com/app/internal/lookup"
)

type Store struct {
	path string
	db   *sql.DB
}

func Open(name string) (*Store, error) {
	path := lookup.PathFor(name)
	if _, err := os.Stat(path); err != nil {
		return nil, err
	}
	return &Store{path: path}, nil
}

func (s *Store) Load(key string) map[string]string {
	raw, err := os.ReadFile(s.path)
	if err != nil {
		return nil
	}
	out := map[string]string{}
	if err := json.Unmarshal(raw, &out); err != nil {
		fmt.Println("store: unmarshal failed")
	}
	return out
}

func (s *Store) Find(id string) (*sql.Rows, error) {
	return s.db.Query("SELECT * FROM items WHERE id = '" + id + "'")
}

func (s *Store) Close() {}
```

`internal/store/store_test.go` (line 15 sleeps; `TestLoadSmoke` has no assertion):

```go
package store

import (
	"testing"
	"time"
)

func TestOpenMissing(t *testing.T) {
	if _, err := Open("missing"); err == nil {
		t.Fatal("expected error")
	}
}

func TestLoadSmoke(t *testing.T) {
	time.Sleep(10 * time.Millisecond)
	_ = (&Store{path: "x"}).Load("k")
}
```

`internal/lookup/lookup.go` is a 302-line lookup table. Generate it by running this from the repository root (save it as a temporary `.py` file if your shell has no heredoc):

```python
from pathlib import Path

root = Path("skills/tech-debt-scan/tests/fixtures/corpus/mixed-decoys/files/internal/lookup")
root.mkdir(parents=True, exist_ok=True)
lines = [
    "package lookup",
    "",
    "// PathFor maps a logical store name to a file path.",
    "func PathFor(name string) string {",
    "\tif p, ok := paths[name]; ok {",
    "\t\treturn p",
    "\t}",
    '\treturn "data/" + name + ".json"',
    "}",
    "",
    "var paths = map[string]string{",
]
lines += [f'\t"n{i:03d}": "data/n{i:03d}.json",' for i in range(1, 291)]
lines += ["}", ""]
(root / "lookup.go").write_bytes("\n".join(lines).encode("utf-8"))
```

`internal/dispatch/dispatch.go` (handlers are reached only through the map at lines 7 to 12; `legacyHandler` at lines 30 to 32 is a stub with a legacy name):

```go
package dispatch

import "errors"

type handler func(args []string) error

var handlers = map[string]handler{
	"start":  start,
	"stop":   stop,
	"status": status,
	"legacy": legacyHandler,
}

// Run dispatches by command name; handlers are reached only through this map.
func Run(args []string) error {
	if len(args) == 0 {
		return errors.New("no command")
	}
	h, ok := handlers[args[0]]
	if !ok {
		return errors.New("unknown command: " + args[0])
	}
	return h(args[1:])
}

func start(args []string) error  { return nil }
func stop(args []string) error   { return nil }
func status(args []string) error { return nil }

func legacyHandler(args []string) error {
	panic("not implemented")
}
```

`internal/build/builder.go`:

```go
package build

type Config struct {
	Name string
	Port int
	TLS  bool
}

type Builder struct {
	cfg Config
}

func NewConfig() *Builder { return &Builder{} }

func (b *Builder) WithName(name string) *Builder { b.cfg.Name = name; return b }
func (b *Builder) WithPort(port int) *Builder    { b.cfg.Port = port; return b }
func (b *Builder) WithTLS(on bool) *Builder      { b.cfg.TLS = on; return b }
func (b *Builder) Build() Config                 { return b.cfg }
```

`internal/flags/flags.go`:

```go
package flags

// Flags holds operational switches read at startup.
//
// payments.killswitch is a permanent kill switch: it stays false in normal
// operation and is flipped by on-call during an incident (see docs/runbook.md).
var Flags = map[string]bool{
	"payments.killswitch": false,
}

func IsEnabled(name string) bool {
	return Flags[name]
}
```

`internal/httpc/httpc.go` (line 9 credential, line 11 deprecation, line 13 TLS verification off, line 14 `http.Get(` with no timeout):

```go
package httpc

import (
	"crypto/tls"
	"io"
	"net/http"
)

const apiToken = "tok_live_9f8e7d6c5b4a3f2e1d0c"

// Deprecated: use FetchWithTimeout from httpc_safe.go.
func Fetch(url string) string {
	http.DefaultTransport.(*http.Transport).TLSClientConfig = &tls.Config{InsecureSkipVerify: true}
	resp, err := http.Get(url)
	if err != nil {
		return ""
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	return string(body)
}
```

`internal/httpc/httpc_safe.go`:

```go
package httpc

import (
	"net/http"
	"time"
)

var client = &http.Client{Timeout: 5 * time.Second}

func FetchWithTimeout(url string) (int, error) {
	resp, err := client.Get(url)
	if err != nil {
		return 0, err
	}
	defer resp.Body.Close()
	return resp.StatusCode, nil
}
```

`internal/crypto/hash.go` (line 9 weak hash):

```go
package crypto

import (
	"crypto/md5"
	"encoding/hex"
)

func Fingerprint(id string) string {
	sum := md5.Sum([]byte(id))
	return hex.EncodeToString(sum[:])
}
```

`internal/shell/run.go` (line 7 shell-out with a gosec suppression):

```go
package shell

import "os/exec"

// Run executes a shell snippet; callers pass trusted input only.
func Run(snippet string) ([]byte, error) {
	return exec.Command("sh", "-c", snippet).CombinedOutput() //nolint:gosec
}
```

- [ ] **Step 9: Write `mixed-decoys/history.yaml` and `mixed-decoys/planted.json`**

Create `skills/tech-debt-scan/tests/fixtures/corpus/mixed-decoys/history.yaml`:

```yaml
commits:
  - author: "Hal Finney <hal@example.com>"
    date: "2024-11-03T09:00:00+00:00"
    subject: "feat: initial service"
    files:
      README.md: "@final"
      go.mod: "@final"
      go.sum: |
        github.com/example/dep v1.1.0 h1:abc=
      Dockerfile: "@final"
      docker-compose.yml: |
        services:
          db:
            image: postgres:latest
          cache:
            image: redis:7.2
      docker-compose.dev.yml: "@final"
      k8s/deployment.yaml: "@final"
      k8s/service.yaml: "@final"
      .github/workflows/ci.yml: "@final"
      docs/runbook.md: |
        # Runbook
      cmd/app/main.go: "@final"
      internal/lookup/lookup.go: "@final"
      internal/dispatch/dispatch.go: "@final"
      internal/httpc/httpc.go: "@final"
      internal/httpc/httpc_safe.go: "@final"
      internal/crypto/hash.go: "@final"
      internal/shell/run.go: "@final"
      internal/store/store_test.go: "@final"
      internal/flags/flags.go: |
        package flags

        var Flags = map[string]bool{
        	"payments.killswitch": false,
        }

        func IsEnabled(name string) bool {
        	return Flags[name]
        }
      internal/build/builder.go: |
        package build

        type Config struct {
        	Name string
        	Port int
        }

        type Builder struct {
        	cfg Config
        }

        func NewConfig() *Builder { return &Builder{} }

        func (b *Builder) WithName(name string) *Builder { b.cfg.Name = name; return b }
        func (b *Builder) WithPort(port int) *Builder    { b.cfg.Port = port; return b }
        func (b *Builder) Build() Config                 { return b.cfg }
      internal/store/store.go: |
        package store

        import (
        	"encoding/json"
        	"fmt"
        	"os"

        	"example.com/app/internal/lookup"
        )

        type Store struct {
        	path string
        }

        func Open(name string) (*Store, error) {
        	path := lookup.PathFor(name)
        	if _, err := os.Stat(path); err != nil {
        		return nil, err
        	}
        	return &Store{path: path}, nil
        }

        func (s *Store) Load(key string) map[string]string {
        	raw, err := os.ReadFile(s.path)
        	if err != nil {
        		return nil
        	}
        	out := map[string]string{}
        	if err := json.Unmarshal(raw, &out); err != nil {
        		fmt.Println("store: unmarshal failed")
        	}
        	return out
        }

        func (s *Store) Close() {}
  - author: "Ivy Lee <ivy@example.com>"
    date: "2025-03-14T09:00:00+00:00"
    subject: "fix: store lookup query"
    files:
      internal/store/store.go: "@final"
  - author: "Hal Finney <hal@example.com>"
    date: "2025-07-22T09:00:00+00:00"
    subject: "docs: document the payments kill switch"
    files:
      internal/flags/flags.go: "@final"
      docs/runbook.md: "@final"
    tag: v0.1.0
  - author: "Ivy Lee <ivy@example.com>"
    date: "2025-12-01T09:00:00+00:00"
    subject: "chore: pin compose images"
    files:
      docker-compose.yml: "@final"
  - author: "Hal Finney <hal@example.com>"
    date: "2026-03-09T09:00:00+00:00"
    subject: "chore: staging compose overrides"
    branch: staging
    files:
      docker-compose.dev.yml: |
        services:
          db:
            image: postgres:latest
          mail:
            image: mailhog/mailhog:latest
          worker:
            image: example/worker:latest
  - author: "Ivy Lee <ivy@example.com>"
    date: "2026-04-20T09:00:00+00:00"
    subject: "feat: builder TLS option"
    branch: main
    files:
      internal/build/builder.go: "@final"
    tag: v0.2.0
  - author: "renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>"
    date: "2026-06-14T09:00:00+00:00"
    subject: "chore(deps): update go.sum"
    files:
      go.sum: "@final"
```

Note the tab characters inside the Go block scalars: YAML block scalars keep tabs that appear after the block's indentation, so the file content has real tabs. Save `history.yaml` with tabs preserved (do not let an editor convert them); Step 10's tree comparison catches any drift.

Create `skills/tech-debt-scan/tests/fixtures/corpus/mixed-decoys/planted.json`:

```json
{
  "planted": [
    {"id": "p1", "family": "error-masking", "type_id": "TD-13", "path": "internal/store/store.go", "lines": [27, 29], "expect_tier": "A"},
    {"id": "p2", "family": "error-masking", "type_id": "TD-13", "path": "internal/store/store.go", "lines": [31, 33], "expect_tier": "B"},
    {"id": "p3", "family": "security", "type_id": "TD-03", "path": "internal/store/store.go", "lines": [38, 38], "expect_tier": "B"},
    {"id": "p4", "family": "security", "type_id": "TD-03", "path": "internal/httpc/httpc.go", "lines": [9, 9], "expect_tier": "B"},
    {"id": "p5", "family": "security", "type_id": "TD-03", "path": "internal/httpc/httpc.go", "lines": [13, 13], "expect_tier": "B"},
    {"id": "p6", "family": "half-finished", "type_id": "TD-34", "path": "internal/httpc/httpc.go", "lines": [14, 14], "expect_tier": "B"},
    {"id": "p7", "family": "dead-code", "type_id": "TD-17", "path": "internal/httpc/httpc.go", "lines": [11, 12], "expect_tier": "B"},
    {"id": "p8", "family": "security", "type_id": "TD-03", "path": "internal/crypto/hash.go", "lines": [9, 9], "expect_tier": "B"},
    {"id": "p9", "family": "security", "type_id": "TD-03", "path": "internal/shell/run.go", "lines": [7, 7], "expect_tier": "B"},
    {"id": "p10", "family": "half-finished", "type_id": "TD-28", "path": "internal/dispatch/dispatch.go", "lines": [30, 32], "expect_tier": "B"},
    {"id": "p11", "family": "dead-code", "type_id": "TD-09", "path": "internal/dispatch/dispatch.go", "lines": [30, 32], "expect_tier": "C"},
    {"id": "p12", "family": "pipeline-infra", "type_id": "TD-19", "path": "Dockerfile", "lines": [8, 8], "expect_tier": "A"},
    {"id": "p13", "family": "pipeline-infra", "type_id": "TD-19", "path": "docker-compose.dev.yml", "lines": [3, 5], "expect_tier": "A"},
    {"id": "p14", "family": "pipeline-infra", "type_id": "TD-19", "path": "k8s/deployment.yaml", "lines": [8, 12], "expect_tier": "A"},
    {"id": "p15", "family": "pipeline-infra", "type_id": "TD-14", "path": ".github/workflows/ci.yml", "lines": [6, 20], "expect_tier": "A"},
    {"id": "p16", "family": "test-quality", "type_id": "TD-12", "path": "internal/store/store_test.go", "lines": [15, 15], "expect_tier": "B"},
    {"id": "p17", "family": "test-quality", "type_id": "TD-18", "path": "internal/store/store_test.go", "lines": [14, 17], "expect_tier": "B"},
    {"id": "p18", "family": "pipeline-infra", "type_id": "TD-27", "path": null, "lines": [0, 0], "expect_tier": "A"}
  ],
  "decoys": [
    {"id": "d1", "family": "complex-units", "path": "internal/lookup/lookup.go", "why": "300-line lookup table: large but cohesive data, not branching"},
    {"id": "d2", "family": "dead-code", "path": "cmd/app/main.go", "why": "entry point with no importer; main is a stoplist name"},
    {"id": "d3", "family": "dead-code", "path": "internal/dispatch/dispatch.go", "lines": [7, 12], "why": "handlers reached only through a string-dispatch map"},
    {"id": "d4", "family": "god-classes", "path": "internal/build/builder.go", "why": "fluent builder: method chains are the idiom, not inappropriate intimacy"},
    {"id": "d5", "family": "error-masking", "path": "cmd/app/main.go", "why": "main logs the error and exits non-zero: a process boundary"},
    {"id": "d6", "family": "dead-code", "path": "internal/flags/flags.go", "why": "documented kill switch (docs/runbook.md), permanently false by design"},
    {"id": "d7", "family": "pipeline-infra", "path": "docker-compose.yml", "why": "images pinned to tags"},
    {"id": "d8", "family": "pipeline-infra", "path": "k8s/service.yaml", "why": "Service manifest has no containers; resource and privilege rules do not apply"},
    {"id": "d9", "family": "half-finished", "path": "internal/httpc/httpc_safe.go", "why": "client carries a Timeout"},
    {"id": "d10", "family": "error-masking", "path": "internal/store/store.go", "lines": [19, 21], "why": "return nil, err propagates the error"},
    {"id": "d11", "family": "ownership", "path": "internal/store/store.go", "why": "two human authors in the repository: the ownership group is suppressed"}
  ]
}
```

- [ ] **Step 10: Run the corpus tests to verify they pass**

Run: `pytest skills/tech-debt-scan/tests/test_corpus.py -v`
Expected: 9 passed (three tests times three fixtures). If `test_replayed_tree_equals_files_dir` fails for one path, the literal in `history.yaml` for that path's last touch differs from `files/`; make the last touch `"@final"` or fix the file. If `test_planted_paths_and_lines_exist` fails, the file is shorter than the planted line range; fix the range.

- [ ] **Step 11: Lint, run everything, commit**

Run: `ruff check . && mypy && pytest -q`
Expected: `All checks passed!` (the corpus is excluded), mypy unchanged, every test passing.

```bash
git add pyproject.toml skills/tech-debt-scan/tests/conftest.py skills/tech-debt-scan/tests/test_corpus.py skills/tech-debt-scan/tests/fixtures/corpus
git commit -m "test(tech-debt-scan): add the three-fixture corpus with replayable histories and planted.json"
```

---

### Task 5: inventory artefact classes, path classes and the conditional ignore

**Files:**
- Modify: `skills/tech-debt-scan/scripts/inventory.py` (`:22-31` imports, `:33-54` after `EXT_TO_LANG`, `:56-73` `DEFAULT_IGNORE`, `:89-101` `FileEntry` and `_is_ignored`, `:104-119` `_line_metrics`, `:189-247` `walk_inventory`; module docstring)
- Create: `skills/tech-debt-scan/tests/test_inventory_v2.py`

**Interfaces:**
- Consumes: `DEFAULTS`, `CONFIG_FILENAME` from `config.py` (Task 1); the corpus fixtures `service_py_repo`, `web_ts_repo` (Task 4).
- Produces (used by Tasks 6 to 11):
  - `LANG_COMMENT: dict[str, tuple[tuple[str, ...], tuple[tuple[str, str], ...]]]` (line markers, block pairs per language) and `DEFAULT_COMMENT` for non-code artefacts
  - `CONDITIONAL_IGNORE: tuple[str, ...] = ("bin", "build")`, `MANIFEST_NAMES: tuple[str, ...]`
  - `PATH_CLASS_GLOBS: dict[str, tuple[str, ...]]`, `PATH_CLASS_ORDER: tuple[str, ...]`
  - `def _classify_path(rel: str, extra: dict[str, list[str]] | None = None) -> str` returning `tests|generated|vendored|docs|source`
  - `ARTEFACT_CLASSES: tuple[tuple[str, tuple[str, ...]], ...]` (ordered), `def _artefact_class(path: Path, rel: str) -> str | None`
  - `def _walk_artefacts(root: Path, candidates: list[tuple[Path, str]], churn_map: dict[str, int]) -> dict[str, list[dict[str, Any]]]` (every class key present, possibly empty)
  - `def _line_metrics(handle: Iterable[str]) -> tuple[int, int, int, int, int]` = `(loc, indent_total, max_indent, deep_indent_lines, longest_indented_run)` with `DEEP_INDENT_UNITS = 3` and `RUN_INDENT_UNITS = 2`
  - `FileEntry` with every spec 4.2 field in spec order; the v2 fields default to their "not computed" value (`None`, `0`, `[]`, `"import-lines"`) and later tasks fill them
  - `walk_inventory(root, ignore=DEFAULT_IGNORE, churn_months=DEFAULT_CHURN_MONTHS, config=None) -> dict[str, Any]` whose result gains `schema_version: 2` and `artefacts`

**Spec:** 4.2 (artefact class table, `DEFAULT_IGNORE` change, `.tech-debt.yaml` exclusion, path classes and config extension, `files`/`total_files`/`languages` keep their v1 meaning), 0(d) (the extension map supplies comment syntax). The spec names `deep_indent_lines` and `longest_indented_run` (2.3, 4.2) without thresholds; this task fixes them as `DEEP_INDENT_UNITS = 3` (a line at indent unit 3 or deeper) and `RUN_INDENT_UNITS = 2` (longest run of consecutive non-blank lines at unit 2 or deeper), named constants so a later calibration is one edit.

**Confidence:** 92% (pure walk and glob logic; the v1 count pins are protected because artefacts never enter `files`, and `bin`/`build` stay ignored unless they hold a manifest, which no v1 fixture does).

- [ ] **Step 1: Write the failing tests**

Create `skills/tech-debt-scan/tests/test_inventory_v2.py`:

```python
"""inventory.py v2: classes, git pass, coupling, graph, band, mapping, docs (spec 4.2)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from config import load_config
from inventory import _classify_path, _line_metrics, walk_inventory

FIXTURES = Path(__file__).parent / "fixtures"


# --- Task 5: path classes, artefact classes, conditional ignore -----------------


def test_v1_fixture_result_gains_schema_version_and_artefacts() -> None:
    result = walk_inventory(FIXTURES / "python-repo")
    assert result["schema_version"] == 2
    assert result["total_files"] == 3
    assert isinstance(result["artefacts"], dict)
    assert set(result["artefacts"]) == {
        "manifest", "lockfile", "runtime_version", "ci", "container", "iac", "sql",
        "notebook", "model_binary", "governance", "build", "config",
    }


@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        ("src/app.py", "source"),
        ("setup.py", "source"),
        ("tests/test_app.py", "tests"),
        ("pkg/test/helper.py", "tests"),
        ("spec/thing_spec.rb", "tests"),
        ("src/__tests__/cart.test.ts", "tests"),
        ("src/api.spec.ts", "tests"),
        ("lib/store_test.go", "tests"),
        ("Domain/OrderTests.cs", "tests"),
        ("Models/Order.g.cs", "generated"),
        ("Forms/Main.designer.cs", "generated"),
        ("Forms/Main.Designer.cs", "generated"),
        ("proto/order_pb2.py", "generated"),
        ("proto/order.pb.go", "generated"),
        ("dist/app.min.js", "generated"),
        ("src/generated/types.ts", "generated"),
        ("api.generated.ts", "generated"),
        ("vendor/lib.js", "vendored"),
        ("src/third_party/x.c", "vendored"),
        ("extern/y.h", "vendored"),
        ("README.md", "docs"),
        ("guide.rst", "docs"),
        ("docs/adr/0001.md", "docs"),
        ("docs/notes.txt", "docs"),
    ],
)
def test_classify_path_table(rel: str, expected: str) -> None:
    assert _classify_path(rel) == expected


def test_classify_path_precedence_vendored_beats_tests() -> None:
    assert _classify_path("vendor/lib/tests/test_x.py") == "vendored"
    assert _classify_path("src/generated/foo.test.ts") == "generated"


def test_classify_path_config_extension() -> None:
    assert _classify_path("qa/check.py") == "source"
    assert _classify_path("qa/check.py", {"tests": ["qa/*"]}) == "tests"


def test_service_py_path_classes(service_py_repo: Path) -> None:
    result = walk_inventory(service_py_repo)
    classes = {entry["path"]: entry["path_class"] for entry in result["files"]}
    assert classes["src/pay/refund.py"] == "source"
    assert classes["setup.py"] == "source"
    assert classes["tests/test_refund.py"] == "tests"
    assert classes["tests/conftest.py"] == "tests"
    assert classes["tests/fixtures/seed.py"] == "tests"
    assert classes["README.md"] == "docs"
    assert classes["docs/adr/0001-ledger.md"] == "docs"
    assert classes["docs/übersicht.md"] == "docs"
    assert result["total_files"] == 16
    assert {e["language"] for e in result["files"]} == {"python", "markdown"}


def test_web_ts_path_classes(web_ts_repo: Path) -> None:
    result = walk_inventory(web_ts_repo)
    classes = {entry["path"]: entry["path_class"] for entry in result["files"]}
    assert classes["src/cart/cart.ts"] == "source"
    assert classes["src/__tests__/cart.test.ts"] == "tests"
    assert classes["src/__tests__/pricing.spec.ts"] == "tests"
    assert classes["src/generated/api-types.ts"] == "generated"
    assert classes["vendor/tiny-emitter.js"] == "vendored"
    assert classes["docs/architecture.md"] == "docs"
    assert result["total_files"] == 16


def test_service_py_artefact_classes(service_py_repo: Path) -> None:
    artefacts = walk_inventory(service_py_repo)["artefacts"]
    paths = {cls: sorted(e["path"] for e in entries) for cls, entries in artefacts.items()}
    assert paths["manifest"] == ["pyproject.toml", "requirements.txt"]
    assert paths["ci"] == [".github/workflows/ci.yml", ".github/workflows/release.yml"]
    assert paths["container"] == ["Dockerfile"]
    assert paths["lockfile"] == []
    entry = next(e for e in artefacts["manifest"] if e["path"] == "pyproject.toml")
    assert set(entry) >= {"path", "loc", "churn", "last_touched", "size_bytes"}
    assert entry["loc"] == 8
    assert entry["size_bytes"] > 0


def test_artefact_classes_synthetic(tmp_path: Path) -> None:
    files = {
        "package.json": '{"name": "x"}\n',
        "package-lock.json": "{}\n",
        ".nvmrc": "20\n",
        ".gitlab-ci.yml": "stages: [test]\n",
        "Makefile": "all:\n\techo hi\n",
        "scripts/deploy.sh": "#!/bin/sh\necho deploy\n",
        "Dockerfile.dev": "FROM alpine\n",
        "docker-compose.yml": "services: {}\n",
        "infra/main.tf": 'provider "aws" {}\n',
        "k8s/dep.yaml": "apiVersion: apps/v1\nkind: Deployment\n",
        "db/migrate/001_init.sql": "create table t (id int);\n",
        "nb/explore.ipynb": json.dumps(
            {
                "cells": [
                    {"cell_type": "markdown", "source": ["# hi"]},
                    {"cell_type": "code", "execution_count": 1, "source": ["x = 1"]},
                    {"cell_type": "code", "execution_count": 2, "source": ["x"]},
                ]
            }
        ),
        "settings.ini": "[main]\nkey = 1\n",
        "CODEOWNERS": "* @team\n",
        ".github/dependabot.yml": "version: 2\n",
        ".tech-debt.yaml": "churn_months: 6\n",
        "bin/tool.dll": "binary",
        "app.py": "print(1)\n",
    }
    for rel, content in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    (tmp_path / "model.pkl").write_bytes(b"\x80\x04binary")
    artefacts = walk_inventory(tmp_path)["artefacts"]
    paths = {cls: sorted(e["path"] for e in entries) for cls, entries in artefacts.items()}
    assert paths["manifest"] == ["package.json"]
    assert paths["lockfile"] == ["package-lock.json"]
    assert paths["runtime_version"] == [".nvmrc"]
    assert paths["ci"] == [".gitlab-ci.yml"]
    assert paths["build"] == ["Makefile", "scripts/deploy.sh"]
    assert paths["container"] == ["Dockerfile.dev", "docker-compose.yml"]
    assert paths["iac"] == ["infra/main.tf", "k8s/dep.yaml"]
    assert paths["sql"] == ["db/migrate/001_init.sql"]
    assert paths["notebook"] == ["nb/explore.ipynb"]
    assert paths["model_binary"] == ["model.pkl"]
    assert paths["config"] == ["settings.ini"]
    assert paths["governance"] == [".github/dependabot.yml", "CODEOWNERS"]
    everything = {p for entries in artefacts.values() for p in (e["path"] for e in entries)}
    assert ".tech-debt.yaml" not in everything
    assert "bin/tool.dll" not in everything
    notebook = artefacts["notebook"][0]
    assert notebook["cells"] == 3
    assert notebook["monotonic_execution"] is True
    model = artefacts["model_binary"][0]
    assert model["lfs_pointer"] is False
    assert model["loc"] == 0


def test_bin_and_build_walked_only_with_a_manifest(tmp_path: Path) -> None:
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "package.json").write_text('{"name": "cli"}\n', encoding="utf-8")
    (tmp_path / "bin" / "cli.js").write_text("console.log(1);\n", encoding="utf-8")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "out.js").write_text("var a = 1;\n", encoding="utf-8")
    result = walk_inventory(tmp_path)
    paths = {e["path"] for e in result["files"]}
    assert "bin/cli.js" in paths
    assert "build/out.js" not in paths
    assert [e["path"] for e in result["artefacts"]["manifest"]] == ["bin/package.json"]


def test_config_ignore_names_and_globs(tmp_path: Path) -> None:
    for rel in ("legacy_v1/a.py", "tmp/b.py", "src/c.py"):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x = 1\n", encoding="utf-8")
    (tmp_path / ".tech-debt.yaml").write_text('ignore: ["legacy_*", "tmp"]\n', encoding="utf-8")
    result = walk_inventory(tmp_path, config=load_config(tmp_path))
    assert {e["path"] for e in result["files"]} == {"src/c.py"}


def test_config_extends_path_classes(tmp_path: Path) -> None:
    (tmp_path / "qa").mkdir()
    (tmp_path / "qa" / "check.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / ".tech-debt.yaml").write_text(
        "path_classes:\n  tests: ['qa/*']\n", encoding="utf-8"
    )
    result = walk_inventory(tmp_path, config=load_config(tmp_path))
    assert result["files"][0]["path_class"] == "tests"


def test_line_metrics_deep_lines_and_longest_run() -> None:
    text = (
        "def f(a, b, c):\n"
        "    if a:\n"
        "        if b:\n"
        "            if c:\n"
        "                return 1\n"
        "\n"
        "        return 2\n"
        "    return 0\n"
    )
    loc, total, max_indent, deep, longest = _line_metrics(text.splitlines(keepends=True))
    assert (loc, total, max_indent) == (8, 13, 4)
    assert deep == 2  # the two lines at unit 3 and unit 4
    assert longest == 4  # units 2, 3, 4 and (after the blank) 2 again


def test_file_entries_carry_every_v2_key(service_py_repo: Path) -> None:
    entry = walk_inventory(service_py_repo)["files"][0]
    assert list(entry) == [
        "path", "ext", "loc", "mtime", "complexity", "max_indent", "churn",
        "language", "path_class", "hotspot_score", "deep_indent_lines", "longest_indented_run",
        "inline_disables", "last_touched", "authors", "top_author", "top_author_share",
        "top_author_line_share", "bugfix_share", "migration_commits", "flaky_commits",
        "untested_change_share", "mapped_tests", "fan_in_approx", "fan_out_approx",
        "fan_in_mode", "coupling_degree",
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest skills/tech-debt-scan/tests/test_inventory_v2.py -v`
Expected: collection error `ImportError: cannot import name '_classify_path' from 'inventory'`.

- [ ] **Step 3: Extend `inventory.py`**

Apply these edits to `skills/tech-debt-scan/scripts/inventory.py`.

(a) Replace the import block (lines 22 to 31) with:

```python
from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, cast

from config import CONFIG_FILENAME, DEFAULTS
```

(`DEFAULTS` is the config module's default mapping; the `config` parameter of `walk_inventory` shadows only the module name inside that function, which is why the import binds `DEFAULTS` and `CONFIG_FILENAME` by name.)

(b) Insert after `EXT_TO_LANG` (after line 54):

```python
# Comment syntax per language: (line markers, block (open, close) pairs). The
# extension map is the only language-aware table in the skill (spec 0(d));
# patterns.py reads this to know which markers to strip and never branches on
# a language name. Unknown languages and non-code artefacts use DEFAULT_COMMENT.
_C_LIKE: tuple[tuple[str, ...], tuple[tuple[str, str], ...]] = (("//",), (("/*", "*/"),))
LANG_COMMENT: dict[str, tuple[tuple[str, ...], tuple[tuple[str, str], ...]]] = {
    "python": (("#",), ()),
    "ruby": (("#",), ()),
    "php": (("//", "#"), (("/*", "*/"),)),
    "markdown": ((), (("<!--", "-->"),)),
    "csharp": _C_LIKE,
    "java": _C_LIKE,
    "kotlin": _C_LIKE,
    "typescript": _C_LIKE,
    "javascript": _C_LIKE,
    "go": _C_LIKE,
    "rust": _C_LIKE,
    "swift": _C_LIKE,
    "cpp": _C_LIKE,
    "c": _C_LIKE,
}
DEFAULT_COMMENT: tuple[tuple[str, ...], tuple[tuple[str, str], ...]] = (
    ("#", "//", "--"),
    (("/*", "*/"), ("<!--", "-->")),
)

# Spec 4.2 manifest names; a `bin/` or `build/` directory holding one of these
# is a real package, so CONDITIONAL_IGNORE below does not apply to it.
MANIFEST_NAMES: tuple[str, ...] = (
    "package.json", "pyproject.toml", "requirements*.txt", "go.mod", "Cargo.toml",
    "Gemfile", "*.csproj", "pom.xml", "build.gradle*",
)

# Path classes (spec 4.2), checked in PATH_CLASS_ORDER; the first match wins and
# everything else is "source". Globs are matched with fnmatchcase against the
# forward-slash relative path and against the basename.
PATH_CLASS_GLOBS: dict[str, tuple[str, ...]] = {
    "vendored": (
        "vendor/*", "*/vendor/*", "third_party/*", "*/third_party/*", "extern/*", "*/extern/*",
    ),
    "generated": (
        "*.g.cs", "*.generated.*", "*_pb2.py", "*.pb.go", "*.min.js", "*.designer.cs",
        "*.Designer.cs", "generated/*", "*/generated/*",
    ),
    "tests": (
        "tests/*", "*/tests/*", "__tests__/*", "*/__tests__/*", "test/*", "*/test/*",
        "spec/*", "*/spec/*", "test_*", "*_test.*", "*.spec.*", "*.test.*", "*Tests.cs",
    ),
    "docs": ("*.md", "*.rst", "*.adoc", "docs/*", "*/docs/*"),
}
PATH_CLASS_ORDER: tuple[str, ...] = ("vendored", "generated", "tests", "docs")

# Artefact classes (spec 4.2 table), in match order. "config" is the catch-all
# for the remaining structured files, so it is last; a YAML file that reaches it
# and contains `apiVersion:` and `kind:` lines is "iac" instead.
ARTEFACT_CLASSES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("manifest", MANIFEST_NAMES),
    ("lockfile", (
        "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock",
        "go.sum", "Cargo.lock", "Gemfile.lock", "packages.lock.json",
    )),
    ("runtime_version", (
        ".python-version", ".nvmrc", ".tool-versions", ".ruby-version", "global.json",
        "rust-toolchain*",
    )),
    ("ci", (
        ".github/workflows/*.yml", ".github/workflows/*.yaml", ".gitlab-ci.yml",
        "azure-pipelines.yml", ".circleci/config.yml", "Jenkinsfile",
    )),
    ("container", (
        "Dockerfile*", "*.dockerfile", "docker-compose*.yml", "docker-compose*.yaml",
        "compose*.yml", "compose*.yaml", ".devcontainer/*",
    )),
    ("iac", ("*.tf", "*.tfvars", "*.hcl", "*.bicep", "Chart.yaml")),
    ("sql", ("*.sql", "migrations/*", "alembic/versions/*", "db/migrate/*", "*.prisma")),
    ("notebook", ("*.ipynb",)),
    ("model_binary", ("*.pkl", "*.pt", "*.h5", "*.onnx", "*.safetensors", "*.joblib")),
    ("governance", (
        "CODEOWNERS", "SECURITY.md", "CONTRIBUTING.md", "PULL_REQUEST_TEMPLATE*",
        "dependabot.yml", "renovate.json", "docs/adr/*",
    )),
    ("build", ("Makefile", "justfile", "Taskfile.yml", "*.sh", "*.ps1")),
    ("config", ("*.yml", "*.yaml", "*.json", "*.toml", "*.ini", "*.cfg", ".env*")),
)
_K8S_API_RE = re.compile(r"^apiVersion:", re.MULTILINE)
_K8S_KIND_RE = re.compile(r"^kind:", re.MULTILINE)
_LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/"
```

(c) Replace `DEFAULT_IGNORE` (lines 56 to 73) with:

```python
DEFAULT_IGNORE: tuple[str, ...] = (
    "node_modules",
    "obj",
    "target",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    ".git",
    ".idea",
    ".vscode",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tech-debt",
)

# Skipped unless the directory itself holds a manifest (spec 4.2): a `bin/`
# that is a CLI package or a `build/` that is a Gradle module is real source.
CONDITIONAL_IGNORE: tuple[str, ...] = ("bin", "build")

# Indent thresholds behind the complex-units leads (spec 2.3, 4.2). The spec
# names the fields; these values are the calibration point.
DEEP_INDENT_UNITS = 3
RUN_INDENT_UNITS = 2
```

(d) Replace `FileEntry` and `_is_ignored` (lines 89 to 101) with:

```python
@dataclass
class FileEntry:
    """One `files[]` entry, in spec 4.2 key order; v2 fields start unset."""

    path: str  # relative to root, forward-slash separated
    ext: str
    loc: int
    mtime: float
    complexity: int  # total logical indent units (indentation complexity proxy)
    max_indent: int  # deepest logical indent level seen
    churn: int  # commits touching the file inside the churn window (0 if no git)
    language: str = ""
    path_class: str = "source"
    hotspot_score: float = 0.0
    deep_indent_lines: int = 0
    longest_indented_run: int = 0
    inline_disables: int = 0  # emitted 0 here; patterns.py fills it in place
    last_touched: str | None = None
    authors: int | None = None
    top_author: str | None = None  # email of the top author (rules.py former-contributor)
    top_author_share: float | None = None
    top_author_line_share: float | None = None
    bugfix_share: float = 0.0
    migration_commits: int = 0
    flaky_commits: int = 0
    untested_change_share: float | None = None
    mapped_tests: list[str] = field(default_factory=list)
    fan_in_approx: int | None = None
    fan_out_approx: int | None = None
    fan_in_mode: str = "import-lines"
    coupling_degree: int = 0


def _classify_path(rel: str, extra: dict[str, list[str]] | None = None) -> str:
    """Return the path class of a forward-slash relative path (spec 4.2)."""
    name = rel.rsplit("/", 1)[-1]
    for cls in PATH_CLASS_ORDER:
        globs = [*PATH_CLASS_GLOBS[cls], *((extra or {}).get(cls) or [])]
        for glob in globs:
            if fnmatchcase(rel, glob) or fnmatchcase(name, glob):
                return cls
    return "source"


def _has_manifest(directory: Path) -> bool:
    try:
        names = [child.name for child in directory.iterdir() if child.is_file()]
    except OSError:
        return False
    return any(fnmatchcase(n, pattern) for n in names for pattern in MANIFEST_NAMES)


def _ignore_sets(
    ignore: tuple[str, ...], config: dict[str, Any]
) -> tuple[frozenset[str], tuple[str, ...]]:
    """Split the ignore list into plain directory names and glob patterns."""
    names = set(ignore)
    globs: list[str] = []
    for item in config.get("ignore") or []:
        text = str(item)
        if any(ch in text for ch in "*?["):
            globs.append(text)
        else:
            names.add(text)
    return frozenset(names), tuple(globs)


def _is_ignored(
    root: Path,
    parts: tuple[str, ...],
    rel: str,
    names: frozenset[str],
    globs: tuple[str, ...],
    manifest_dirs: dict[Path, bool],
) -> bool:
    for index, part in enumerate(parts[:-1]):
        if part in names:
            return True
        if part in CONDITIONAL_IGNORE:
            directory = root.joinpath(*parts[: index + 1])
            if directory not in manifest_dirs:
                manifest_dirs[directory] = _has_manifest(directory)
            if not manifest_dirs[directory]:
                return True
    return any(
        fnmatchcase(rel, glob) or any(fnmatchcase(part, glob) for part in parts)
        for glob in globs
    )


def _iter_files(
    root: Path, names: frozenset[str], globs: tuple[str, ...]
) -> Iterator[tuple[Path, str]]:
    """Yield (path, forward-slash relative path) for every regular file to consider."""
    manifest_dirs: dict[Path, bool] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        rel = path.relative_to(root)
        rel_str = rel.as_posix()
        if rel_str == CONFIG_FILENAME:
            continue
        if _is_ignored(root, rel.parts, rel_str, names, globs, manifest_dirs):
            continue
        yield path, rel_str
```

(e) Replace `_line_metrics` (lines 104 to 119) with:

```python
def _line_metrics(handle: Iterable[str]) -> tuple[int, int, int, int, int]:
    """Return (loc, indent_total, max_indent, deep_indent_lines, longest_indented_run)."""
    loc = 0
    indent_total = 0
    max_indent = 0
    deep_lines = 0
    longest_run = 0
    run = 0
    for line in handle:
        loc += 1
        stripped = line.lstrip(" \t")
        if not stripped or stripped in ("\n", "\r\n"):
            continue  # blank lines carry no complexity signal and do not break a run
        ws = line[: len(line) - len(stripped)]
        units = (ws.count("\t") * _INDENT_SPACES + ws.count(" ")) // _INDENT_SPACES
        indent_total += units
        max_indent = max(max_indent, units)
        if units >= DEEP_INDENT_UNITS:
            deep_lines += 1
        if units >= RUN_INDENT_UNITS:
            run += 1
            longest_run = max(longest_run, run)
        else:
            run = 0
    return loc, indent_total, max_indent, deep_lines, longest_run
```

(f) Insert before `walk_inventory` (after `_build_hotspots`):

```python
def _match_artefact(rel: str, name: str, pattern: str) -> bool:
    if "/" in pattern:
        return fnmatchcase(rel, pattern) or fnmatchcase(rel, "*/" + pattern)
    return fnmatchcase(name, pattern)


def _looks_like_kubernetes(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            head = handle.read(65536).decode("utf-8", errors="ignore")
    except OSError:
        return False
    return bool(_K8S_API_RE.search(head) and _K8S_KIND_RE.search(head))


def _artefact_class(path: Path, rel: str) -> str | None:
    """Return the artefact class of a non-code file, or None when it is neither."""
    name = rel.rsplit("/", 1)[-1]
    is_yaml = name.lower().endswith((".yml", ".yaml"))
    for cls, patterns in ARTEFACT_CLASSES:
        if cls == "config" and is_yaml and _looks_like_kubernetes(path):
            return "iac"
        for pattern in patterns:
            if _match_artefact(rel, name, pattern):
                return cls
    return None


def _notebook_facts(text: str) -> tuple[int, bool | None]:
    """Return (cell count, execution counts strictly increasing or None)."""
    try:
        raw = json.loads(text)
    except ValueError:
        return 0, None
    cells = raw.get("cells") if isinstance(raw, dict) else None
    if not isinstance(cells, list):
        return 0, None
    counts = [
        c.get("execution_count")
        for c in cells
        if isinstance(c, dict) and c.get("cell_type") == "code"
    ]
    numbers = [n for n in counts if isinstance(n, int)]
    if not numbers:
        return len(cells), None
    monotonic = all(a < b for a, b in zip(numbers, numbers[1:], strict=False))
    return len(cells), monotonic


def _artefact_entry(path: Path, rel: str, cls: str, churn: int) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "path": rel,
        "loc": 0,
        "churn": churn,
        "last_touched": None,
        "size_bytes": path.stat().st_size,
    }
    if cls == "model_binary":  # size and LFS pointer only; never opened further
        try:
            with path.open("rb") as handle:
                entry["lfs_pointer"] = handle.read(64).startswith(_LFS_POINTER_PREFIX)
        except OSError:
            entry["lfs_pointer"] = False
        return entry
    try:
        text = path.read_bytes().decode("utf-8", errors="ignore")
    except OSError:
        return entry
    entry["loc"] = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    if cls == "notebook":
        entry["cells"], entry["monotonic_execution"] = _notebook_facts(text)
    return entry


def _walk_artefacts(
    root: Path, candidates: list[tuple[Path, str]], churn_map: dict[str, int]
) -> dict[str, list[dict[str, Any]]]:
    """Classify the files the extension map skipped (spec 4.2 artefact classes)."""
    out: dict[str, list[dict[str, Any]]] = {cls: [] for cls, _ in ARTEFACT_CLASSES}
    for path, rel in candidates:
        cls = _artefact_class(path, rel)
        if cls is None:
            continue
        out[cls].append(_artefact_entry(path, rel, cls, churn_map.get(rel, 0)))
    return out
```

(g) Replace `walk_inventory` (lines 189 to 247) with:

```python
def walk_inventory(
    root: Path,
    ignore: tuple[str, ...] = DEFAULT_IGNORE,
    churn_months: int = DEFAULT_CHURN_MONTHS,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    if not root.exists():
        raise InventoryError(f"path not found: {root}")
    if not root.is_dir():
        raise InventoryError(f"path is not a directory: {root}")
    cfg = config if config is not None else copy.deepcopy(DEFAULTS)
    names, globs = _ignore_sets(ignore, cfg)
    extra_classes: dict[str, list[str]] = cfg.get("path_classes") or {}

    churn = _git_churn(root, churn_months)
    git_available = churn is not None
    churn_map = churn or {}

    entries: list[FileEntry] = []
    languages: set[str] = set()
    artefact_candidates: list[tuple[Path, str]] = []

    for path, rel_str in _iter_files(root, names, globs):
        ext = path.suffix.lower()
        lang = EXT_TO_LANG.get(ext)
        if lang is None:
            artefact_candidates.append((path, rel_str))
            continue
        try:
            with path.open(encoding="utf-8", errors="ignore") as handle:
                loc, indent_total, max_indent, deep, longest = _line_metrics(handle)
        except OSError as exc:
            raise InventoryError(f"could not read {path}: {exc}") from exc
        entries.append(
            FileEntry(
                path=rel_str,
                ext=ext,
                loc=loc,
                mtime=path.stat().st_mtime,
                complexity=indent_total,
                max_indent=max_indent,
                churn=churn_map.get(rel_str, 0),
                language=lang,
                path_class=_classify_path(rel_str, extra_classes),
                deep_indent_lines=deep,
                longest_indented_run=longest,
            )
        )
        languages.add(lang)

    return {
        "schema_version": 2,
        "root": str(root),
        "total_files": len(entries),
        "total_loc": sum(e.loc for e in entries),
        "languages": sorted(languages),
        "git_available": git_available,
        "churn_window_months": churn_months,
        "hotspots": _build_hotspots(entries),
        "files": [asdict(e) for e in entries],
        "artefacts": _walk_artefacts(root, artefact_candidates, churn_map),
    }
```

(h) In `_main`, the `cast("list[dict[str, object]]", ...)` line keeps working; leave it.

(i) Add to the module docstring, after the churn paragraph:

```
v2 (spec 4.2) adds path classes on every entry (tests, generated, vendored,
docs, source), an ``artefacts`` block for the files the extension map skips
(manifests, lockfiles, CI, containers, IaC, SQL, notebooks, model binaries,
config, governance), and a conditional ignore: ``bin/`` and ``build/`` are
skipped unless they hold a manifest. ``.tech-debt.yaml`` at the root is never
an artefact. ``LANG_COMMENT`` is the comment-syntax half of the extension map
that ``patterns.py`` reads; nothing else in the skill is language-aware.
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest skills/tech-debt-scan/tests/test_inventory_v2.py skills/tech-debt-scan/tests/test_inventory.py skills/tech-debt-scan/tests/test_e2e.py -v`
Expected: all pass, including the untouched v1 pins (`test_python_repo_inventory` 3 files, `test_csharp_repo_inventory` 2 with `/bin/` and `/obj/` absent, `test_react_repo_inventory` 4, `test_inventory_carries_hotspot_summary_keys` key set, `test_non_git_dir_has_zero_churn`).

- [ ] **Step 5: Lint and type-check**

Run: `ruff check . && mypy`
Expected: `All checks passed!`, `Success: no issues found`.

- [ ] **Step 6: Commit**

```bash
git add skills/tech-debt-scan/scripts/inventory.py skills/tech-debt-scan/tests/test_inventory_v2.py
git commit -m "feat(tech-debt-scan): inventory path classes, artefact classes and conditional bin/build ignore"
```

---

### Task 6: the git pass (`git_history.py`) wired into the inventory

**Files:**
- Create: `skills/tech-debt-scan/scripts/git_history.py`
- Modify: `skills/tech-debt-scan/scripts/inventory.py` (imports; delete `_git_churn`; `_artefact_entry` and `_walk_artefacts` take histories; `walk_inventory` joins the git pass; module docstring)
- Modify: `skills/tech-debt-scan/tests/test_inventory_v2.py` (append the Task 6 section)

**Interfaces:**
- Consumes: `_classify_path`, `FileEntry`, `_walk_artefacts`, `walk_inventory` from Task 5; `DEFAULTS` from Task 1; `service_py_repo` and `replay_history` from Tasks 3 and 4.
- Produces (`git_history.py`, used by Tasks 7, 9, 10 and 11):
  - `GIT_TIMEOUT: int = 120`, `LOG_FORMAT: str = "%x1e%H%x09%aN%x09%aE%x09%aI%x09%s"`
  - `BUGFIX_RE`, `MIGRATION_RE`, `FLAKY_RE: re.Pattern[str]`
  - `@dataclass(slots=True) class Commit(sha: str, author_name: str, author_email: str, date: str, subject: str, files: list[str])`
  - `@dataclass(slots=True) class FileHistory(churn: int = 0, last_touched: str | None = None, authors: int = 0, top_author: str | None = None, top_author_share: float | None = None, bugfix_share: float = 0.0, migration_commits: int = 0, flaky_commits: int = 0, untested_change_share: float | None = None)`
  - `def run_git(root: Path, args: Sequence[str]) -> str | None` (list argv, UTF-8 with replacement, 120 s timeout, `None` on any failure)
  - `def parse_log(stdout: str) -> list[Commit]`
  - `def git_log_pass(root: Path, months: int) -> list[Commit] | None` (newest first, as git emits them)
  - `def is_bot(name: str, bot_authors: Sequence[str]) -> bool` (case-insensitive substring match)
  - `def derive_file_history(commits: Sequence[Commit], present: set[str], *, is_test: Callable[[str], bool], bot_authors: Sequence[str], bulk_threshold: int) -> tuple[dict[str, FileHistory], int]` returning one `FileHistory` per path in `present` and the number of bulk commits excluded
  - `def repo_authors(commits: Sequence[Commit], bot_authors: Sequence[str], bulk_threshold: int) -> list[dict[str, Any]]` (`[{"email", "name", "commits", "last_active"}]`, humans only, most commits first then email)
  - `def parse_branch_refs(stdout: str) -> list[dict[str, Any]]` and `def list_branches(root: Path) -> list[dict[str, Any]] | None` (`[{"name", "ref", "last_commit", "merged": bool | None}]`; symrefs such as `origin/HEAD` skipped; `merged` is `None` when `git merge-base --is-ancestor` exits 128)
  - `def list_tags(root: Path) -> list[dict[str, Any]] | None` (`[{"name", "date"}]` in creator-date order)
  - `def mailmap_present(root: Path) -> bool`
  - `def blame_top_share(root: Path, rel: str, bot_authors: Sequence[str]) -> tuple[float | None, str | None]` (share of lines by the top human author and that author's email; defined here, wired into the inventory by Task 9 once the hotspot band exists)
  - `inventory.py` gains a top-level `git` block, `signal_sources`, and fills the per-file history fields and artefact `churn`/`last_touched`.

**Spec:** 4.2 "One git pass" (exact command, UTF-8 with replacement, `maxsplit=4`, authors keyed by email, `bot_authors`, HEAD join, per-file fields, repo-wide block, branches with `%(symref)` and exit-128 null, tags, blame cap), 3.3 (timeouts and null results), "No git" paragraph. Verified on this machine: the log output is one `\x1e`-prefixed record per commit, header then a blank line then file names; `%aI` renders `+00:00` as `Z`; `for-each-ref` prints an empty `%(symref)` column for ordinary refs; `merge-base --is-ancestor` exits 1 for an unmerged branch and 128 for an unknown object; `blame --line-porcelain` carries `author ` and `author-mail <...>` lines per source line.

**Decision (spec 4.2 leaves it open):** commits touching more than `bulk_threshold` files are excluded from churn, authorship and coupling alike and counted in `git.bulk_commits_excluded`; `commits_in_window` counts every commit in the window, bots and bulk included. Git emits commits newest first, so `last_touched` and `last_active` are the first date seen per file or author, which avoids comparing ISO strings across time-zone offsets.

**Confidence:** 92% (every git call was run on this machine; the residual risk is the corpus counts, which Task 4's table pins).

- [ ] **Step 1: Write the failing tests**

Append to `skills/tech-debt-scan/tests/test_inventory_v2.py`:

```python
# --- Task 6: git pass ------------------------------------------------------------


def test_git_pass_per_file_history_fields(service_py_repo: Path) -> None:
    result = walk_inventory(service_py_repo, churn_months=240)
    assert result["git_available"] is True
    files = {e["path"]: e for e in result["files"]}
    refund = files["src/pay/refund.py"]
    assert refund["churn"] == 7
    assert refund["authors"] == 1
    assert refund["top_author"] == "ada@example.com"
    assert refund["top_author_share"] == 1.0
    assert refund["bugfix_share"] == pytest.approx(2 / 7, abs=0.001)
    assert refund["untested_change_share"] == pytest.approx(4 / 7, abs=0.001)
    assert refund["last_touched"].startswith("2026-06-22")
    ledger = files["src/pay/ledger.py"]
    assert ledger["churn"] == 7
    assert ledger["authors"] == 3
    assert ledger["top_author"] == "ada@example.com"
    assert ledger["top_author_share"] == pytest.approx(5 / 7, abs=0.001)
    gateway = files["src/pay/gateway.py"]
    assert gateway["churn"] == 2
    assert gateway["authors"] == 1
    assert gateway["migration_commits"] == 1
    assert gateway["mapped_tests"] == []
    assert files["tests/test_ledger.py"]["flaky_commits"] == 1
    assert files["src/pay/legacy_export.py"]["churn"] == 1


def test_git_pass_authors_keyed_by_email_and_bots_dropped(service_py_repo: Path) -> None:
    result = walk_inventory(service_py_repo, churn_months=240)
    git = result["git"]
    assert [a["email"] for a in git["authors"]] == [
        "ada@example.com", "linus@example.com", "grace@example.com",
    ]
    assert [a["commits"] for a in git["authors"]] == [7, 5, 3]
    assert git["authors"][0]["name"] == "Ada Lovelace"
    assert git["authors"][0]["last_active"].startswith("2026-06-22")
    assert git["commits_in_window"] == 16
    assert git["bulk_commits_excluded"] == 0
    assert git["mailmap_present"] is False
    req = next(e for e in result["artefacts"]["manifest"] if e["path"] == "requirements.txt")
    assert req["churn"] == 2  # the bot commit still counts as churn
    assert req["last_touched"].startswith("2026-01-15")
    assert "git" in result["signal_sources"]


def test_git_pass_head_join_drops_deleted_file(service_py_repo: Path) -> None:
    result = walk_inventory(service_py_repo, churn_months=240)
    assert "src/pay/old_helper.py" not in {e["path"] for e in result["files"]}
    assert result["git"]["commits_in_window"] == 16  # the deletion commit is still counted


def test_git_pass_non_ascii_path(service_py_repo: Path) -> None:
    files = {e["path"]: e for e in walk_inventory(service_py_repo, churn_months=240)["files"]}
    assert files["docs/übersicht.md"]["churn"] == 1
    assert files["docs/übersicht.md"]["last_touched"].startswith("2024-10-05")


def test_git_pass_window_excludes_old_commits(service_py_repo: Path) -> None:
    result = walk_inventory(service_py_repo, churn_months=1)
    assert result["git_available"] is True
    assert all(e["churn"] == 0 for e in result["files"])
    assert result["git"]["commits_in_window"] == 0
    assert result["hotspots"] == []


def test_branches_and_tags(service_py_repo: Path) -> None:
    git = walk_inventory(service_py_repo, churn_months=240)["git"]
    branches = {b["name"]: b for b in git["branches"]}
    hotfix = branches["hotfix/ledger-rounding"]
    assert hotfix["merged"] is False
    assert hotfix["ref"] == "refs/heads/hotfix/ledger-rounding"
    assert hotfix["last_commit"].startswith("2026-04-10")
    assert branches["main"]["merged"] is True
    assert [t["name"] for t in git["tags"]] == ["v0.1.0", "v0.2.0"]
    assert git["tags"][0]["date"].startswith("2024-10-05")
    assert git["tags"][1]["date"].startswith("2026-02-20")


def test_parse_branch_refs_skips_symref() -> None:
    from git_history import parse_branch_refs

    stdout = (
        "refs/heads/main\tmain\t\t2026-01-01T09:00:00Z\taaa\n"
        "refs/remotes/origin/HEAD\torigin/HEAD\trefs/remotes/origin/main"
        "\t2026-01-01T09:00:00Z\taaa\n"
        "refs/remotes/origin/main\torigin/main\t\t2026-01-01T09:00:00Z\taaa\n"
    )
    refs = parse_branch_refs(stdout)
    assert [r["name"] for r in refs] == ["main", "origin/main"]
    assert refs[1]["ref"] == "refs/remotes/origin/main"
    assert refs[0]["sha"] == "aaa"


def test_parse_log_tab_in_subject_and_non_ascii_path() -> None:
    from git_history import parse_log

    stdout = (
        "\x1eabc\tAda\tada@example.com\t2024-09-10T10:00:00Z\tfeat: a\tb\n"
        "\nsrc/app.py\nsrc/naïve.py\n"
        "\x1edef\tGrace\tgrace@example.com\t2025-03-01T09:00:00Z\tfix: r\n\nsrc/app.py\n"
    )
    commits = parse_log(stdout)
    assert [c.sha for c in commits] == ["abc", "def"]
    assert commits[0].subject == "feat: a\tb"
    assert commits[0].files == ["src/app.py", "src/naïve.py"]
    assert commits[1].author_email == "grace@example.com"


def test_is_bot_matches_default_list() -> None:
    from config import DEFAULTS
    from git_history import is_bot

    bots = DEFAULTS["bot_authors"]
    assert is_bot("dependabot[bot]", bots)
    assert is_bot("github-actions", bots)
    assert is_bot("Claude", bots)
    assert not is_bot("Ada Lovelace", bots)


def test_bulk_commits_excluded_from_churn(tmp_path: Path) -> None:
    from make_history import replay_history

    files_root = tmp_path / "files"
    files_root.mkdir()
    bulk = "\n".join(f"      f{i}.py: 'x = {i}'" for i in range(60))
    history = tmp_path / "history.yaml"
    history.write_text(
        "commits:\n"
        "  - author: 'Bulk Bob <bob@example.com>'\n"
        "    date: '2026-01-01T09:00:00+00:00'\n"
        "    subject: 'chore: reformat everything'\n"
        f"    files:\n{bulk}\n"
        "  - author: 'Ada Lovelace <ada@example.com>'\n"
        "    date: '2026-02-01T09:00:00+00:00'\n"
        "    subject: 'feat: touch one'\n"
        "    files:\n      f0.py: 'x = 100'\n",
        encoding="utf-8",
    )
    for i in range(60):
        (files_root / f"f{i}.py").write_text(f"x = {i}" if i else "x = 100", encoding="utf-8")
    repo = replay_history(history, files_root, tmp_path / "repo")
    result = walk_inventory(repo, churn_months=240)
    files = {e["path"]: e for e in result["files"]}
    assert files["f0.py"]["churn"] == 1
    assert files["f1.py"]["churn"] == 0
    assert result["git"]["bulk_commits_excluded"] == 1
    assert result["git"]["commits_in_window"] == 2
    assert [a["email"] for a in result["git"]["authors"]] == ["ada@example.com"]


def test_no_git_shape(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    result = walk_inventory(tmp_path)
    assert result["git_available"] is False
    entry = result["files"][0]
    assert entry["churn"] == 0
    assert entry["last_touched"] is None
    assert entry["authors"] is None
    assert entry["top_author_share"] is None
    assert entry["top_author_line_share"] is None
    assert entry["untested_change_share"] is None
    assert result["hotspots"] == []
    assert result["git"] == {
        "authors": [], "branches": [], "tags": [], "commits_in_window": 0,
        "bulk_commits_excluded": 0, "mailmap_present": False,
    }
    assert result["signal_sources"] == {}


def test_blame_top_share_on_corpus(service_py_repo: Path) -> None:
    from config import DEFAULTS
    from git_history import blame_top_share

    share, email = blame_top_share(service_py_repo, "src/pay/refund.py", DEFAULTS["bot_authors"])
    assert share == 1.0
    assert email == "ada@example.com"
    share, _ = blame_top_share(service_py_repo, "src/pay/ledger.py", DEFAULTS["bot_authors"])
    assert share is not None and share < 1.0
    assert blame_top_share(service_py_repo, "does/not/exist.py", []) == (None, None)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest skills/tech-debt-scan/tests/test_inventory_v2.py -k "git_pass or branches or parse or is_bot or bulk or no_git or blame" -v`
Expected: `test_git_pass_per_file_history_fields` FAILS with `AssertionError: assert None == 1` at `refund["authors"] == 1` (the v1 churn map fills `churn` but every history field is still its default), `test_git_pass_authors_keyed_by_email_and_bots_dropped` FAILS with `KeyError: 'git'`, `test_no_git_shape` FAILS with `KeyError: 'git'`, and the four tests that import from `git_history` FAIL with `ModuleNotFoundError: No module named 'git_history'`.

- [ ] **Step 3: Write `git_history.py`**

Create `skills/tech-debt-scan/scripts/git_history.py`:

```python
"""One pass over git history for inventory.py (spec 4.2).

``git_log_pass`` runs a single ``git log --name-only`` with a record separator
format and returns every commit in the churn window, newest first, with its
author name and email, ISO date, subject and touched paths (root-relative,
forward-slash). ``derive_file_history`` folds those commits into per-file
facts for the paths present at HEAD, so a file deleted in history never
becomes a lead. ``repo_authors``, ``list_branches``, ``list_tags``,
``mailmap_present`` and ``blame_top_share`` give the repo-wide ``git`` block
and the hotspot-band line share.

Failure posture (spec 3.3): every git call is a list argv with a 120-second
timeout; a missing binary, a non-repository, a timeout or a non-zero exit
returns ``None`` and the caller emits the no-git shape. Output is decoded as
UTF-8 with replacement (``core.quotePath=false`` keeps non-ASCII paths raw).

Authors are keyed by email; names matching ``bot_authors`` (case-insensitive
substring) are dropped from authorship counts. Commits touching more than the
coupling ``bulk_threshold`` are excluded from churn, authorship and coupling
and counted in ``bulk_commits_excluded``; ``commits_in_window`` counts every
commit. Git emits newest first, so the first date seen per file or author is
its last touch.
"""
from __future__ import annotations

import re
import subprocess
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GIT_TIMEOUT = 120
LOG_FORMAT = "%x1e%H%x09%aN%x09%aE%x09%aI%x09%s"
REF_FORMAT = (
    "%(refname)%09%(refname:short)%09%(symref)%09%(committerdate:iso-strict)%09%(objectname)"
)
TAG_FORMAT = "%(refname:short)%09%(creatordate:iso-strict)"

BUGFIX_RE = re.compile(r"fix|bug|hotfix|regress", re.IGNORECASE)
MIGRATION_RE = re.compile(r"migrat|legacy|deprecat|port(ed|ing)|codemod|upgrade", re.IGNORECASE)
FLAKY_RE = re.compile(r"flak", re.IGNORECASE)


@dataclass(slots=True)
class Commit:
    sha: str
    author_name: str
    author_email: str
    date: str
    subject: str
    files: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FileHistory:
    churn: int = 0
    last_touched: str | None = None
    authors: int = 0
    top_author: str | None = None
    top_author_share: float | None = None
    bugfix_share: float = 0.0
    migration_commits: int = 0
    flaky_commits: int = 0
    untested_change_share: float | None = None


def run_git(root: Path, args: Sequence[str]) -> str | None:
    """Run ``git -C root <args>``; return stdout, or None on any failure."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def parse_log(stdout: str) -> list[Commit]:
    """Parse the LOG_FORMAT output: one 0x1e record per commit."""
    commits: list[Commit] = []
    for chunk in stdout.split("\x1e"):
        if not chunk.strip():
            continue
        header, _, body = chunk.partition("\n")
        parts = header.split("\t", 4)  # subjects may contain tabs
        if len(parts) < 5:
            continue
        sha, name, email, date, subject = parts
        files = [line.strip() for line in body.splitlines() if line.strip()]
        commits.append(Commit(sha, name, email, date, subject, files))
    return commits


def git_log_pass(root: Path, months: int) -> list[Commit] | None:
    """Every commit in the window touching ``root``, newest first; None without git."""
    stdout = run_git(
        root,
        [
            "-c", "core.quotePath=false", "log", f"--since={months} months ago",
            "--name-only", "--relative", f"--format={LOG_FORMAT}", "--", ".",
        ],
    )
    if stdout is None:
        return None
    return parse_log(stdout)


def is_bot(name: str, bot_authors: Sequence[str]) -> bool:
    lowered = name.lower()
    return any(str(bot).lower() in lowered for bot in bot_authors)


def _share(part: int, whole: int) -> float | None:
    return round(part / whole, 3) if whole else None


def derive_file_history(
    commits: Sequence[Commit],
    present: set[str],
    *,
    is_test: Callable[[str], bool],
    bot_authors: Sequence[str],
    bulk_threshold: int,
) -> tuple[dict[str, FileHistory], int]:
    """Per-file history for the paths present at HEAD; also the bulk commit count."""
    histories: dict[str, FileHistory] = {path: FileHistory() for path in present}
    authors: dict[str, Counter[str]] = {path: Counter() for path in present}
    bugfix: Counter[str] = Counter()
    untested: Counter[str] = Counter()
    bulk_excluded = 0
    for commit in commits:
        if len(commit.files) > bulk_threshold:
            bulk_excluded += 1
            continue
        human = not is_bot(commit.author_name, bot_authors)
        has_test = any(is_test(path) for path in commit.files)
        is_fix = BUGFIX_RE.search(commit.subject) is not None
        is_migration = MIGRATION_RE.search(commit.subject) is not None
        is_flaky = FLAKY_RE.search(commit.subject) is not None
        for path in commit.files:
            history = histories.get(path)
            if history is None:
                continue  # deleted before HEAD: never a lead
            history.churn += 1
            if history.last_touched is None:
                history.last_touched = commit.date
            if human:
                authors[path][commit.author_email] += 1
            if is_fix:
                bugfix[path] += 1
            if is_migration:
                history.migration_commits += 1
            if is_flaky:
                history.flaky_commits += 1
            if not has_test:
                untested[path] += 1
    for path, history in histories.items():
        counter = authors[path]
        history.authors = len(counter)
        if counter:
            email, count = counter.most_common(1)[0]
            history.top_author = email
            history.top_author_share = _share(count, sum(counter.values()))
        history.bugfix_share = _share(bugfix[path], history.churn) or 0.0
        history.untested_change_share = _share(untested[path], history.churn)
    return histories, bulk_excluded


def repo_authors(
    commits: Sequence[Commit], bot_authors: Sequence[str], bulk_threshold: int
) -> list[dict[str, Any]]:
    """Human authors with commit counts and last active date, most commits first."""
    counts: Counter[str] = Counter()
    names: dict[str, str] = {}
    last_active: dict[str, str] = {}
    for commit in commits:
        if len(commit.files) > bulk_threshold or is_bot(commit.author_name, bot_authors):
            continue
        counts[commit.author_email] += 1
        names.setdefault(commit.author_email, commit.author_name)
        last_active.setdefault(commit.author_email, commit.date)
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [
        {"email": email, "name": names[email], "commits": count, "last_active": last_active[email]}
        for email, count in ordered
    ]


def parse_branch_refs(stdout: str) -> list[dict[str, Any]]:
    """Parse REF_FORMAT lines, skipping symbolic refs such as origin/HEAD."""
    refs: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 5:
            continue
        refname, short, symref, date, sha = parts
        if symref:
            continue
        refs.append({"name": short, "ref": refname, "last_commit": date, "sha": sha})
    return refs


def _is_ancestor(root: Path, sha: str) -> bool | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "merge-base", "--is-ancestor", sha, "HEAD"],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    return None  # 128: unknown object or no HEAD


def list_branches(root: Path) -> list[dict[str, Any]] | None:
    stdout = run_git(root, ["for-each-ref", f"--format={REF_FORMAT}", "refs/heads", "refs/remotes"])
    if stdout is None:
        return None
    branches: list[dict[str, Any]] = []
    for ref in parse_branch_refs(stdout):
        sha = str(ref.pop("sha"))
        ref["merged"] = _is_ancestor(root, sha)
        branches.append(ref)
    return branches


def list_tags(root: Path) -> list[dict[str, Any]] | None:
    stdout = run_git(root, ["tag", "--sort=creatordate", f"--format={TAG_FORMAT}"])
    if stdout is None:
        return None
    tags: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        name, _, date = line.partition("\t")
        if name:
            tags.append({"name": name, "date": date})
    return tags


def mailmap_present(root: Path) -> bool:
    top = run_git(root, ["rev-parse", "--show-toplevel"])
    if top is None:
        return False
    return (Path(top.strip()) / ".mailmap").is_file()


def blame_top_share(
    root: Path, rel: str, bot_authors: Sequence[str]
) -> tuple[float | None, str | None]:
    """(share of lines by the top human author, that author's email) via blame -w."""
    stdout = run_git(
        root, ["-c", "core.quotePath=false", "blame", "-w", "--line-porcelain", "--", rel]
    )
    if stdout is None:
        return None, None
    counter: Counter[str] = Counter()
    name = ""
    for line in stdout.splitlines():
        if line.startswith("author "):
            name = line[7:]
        elif line.startswith("author-mail ") and not is_bot(name, bot_authors):
            counter[line[12:].strip().strip("<>")] += 1
    if not counter:
        return None, None
    email, count = counter.most_common(1)[0]
    return round(count / sum(counter.values()), 3), email
```

- [ ] **Step 4: Wire the pass into `inventory.py`**

(a) Add to the import block:

```python
from git_history import (
    FileHistory,
    derive_file_history,
    git_log_pass,
    list_branches,
    list_tags,
    mailmap_present,
    repo_authors,
)
```

and `from datetime import UTC, datetime` (used for `signal_sources`).

(b) Delete `_git_churn` entirely (v1 lines 122 to 160).

(c) Change `_artefact_entry` and `_walk_artefacts` to take histories:

```python
def _artefact_entry(path: Path, rel: str, cls: str, history: FileHistory | None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "path": rel,
        "loc": 0,
        "churn": history.churn if history else 0,
        "last_touched": history.last_touched if history else None,
        "size_bytes": path.stat().st_size,
    }
```

(the rest of the function is unchanged) and

```python
def _walk_artefacts(
    root: Path, candidates: list[tuple[Path, str]], histories: dict[str, FileHistory]
) -> dict[str, list[dict[str, Any]]]:
    """Classify the files the extension map skipped (spec 4.2 artefact classes)."""
    out: dict[str, list[dict[str, Any]]] = {cls: [] for cls, _ in ARTEFACT_CLASSES}
    for path, rel in candidates:
        cls = _artefact_class(path, rel)
        if cls is None:
            continue
        out[cls].append(_artefact_entry(path, rel, cls, histories.get(rel)))
    return out
```

(d) Add these helpers before `walk_inventory`:

```python
_EMPTY_GIT_BLOCK: dict[str, Any] = {
    "authors": [],
    "branches": [],
    "tags": [],
    "commits_in_window": 0,
    "bulk_commits_excluded": 0,
    "mailmap_present": False,
}


def _apply_history(entry: FileEntry, history: FileHistory) -> None:
    entry.churn = history.churn
    entry.last_touched = history.last_touched
    entry.authors = history.authors
    entry.top_author = history.top_author
    entry.top_author_share = history.top_author_share
    entry.bugfix_share = history.bugfix_share
    entry.migration_commits = history.migration_commits
    entry.flaky_commits = history.flaky_commits
    entry.untested_change_share = history.untested_change_share


def _git_block(
    root: Path, commits: list[Commit] | None, bulk_excluded: int, cfg: dict[str, Any]
) -> dict[str, Any]:
    if commits is None:
        return dict(_EMPTY_GIT_BLOCK)
    bots = [str(b) for b in cfg["bot_authors"]]
    return {
        "authors": repo_authors(commits, bots, int(cfg["coupling"]["bulk_threshold"])),
        "branches": list_branches(root) or [],
        "tags": list_tags(root) or [],
        "commits_in_window": len(commits),
        "bulk_commits_excluded": bulk_excluded,
        "mailmap_present": mailmap_present(root),
    }
```

and add `Commit` to the `git_history` import list.

(e) Replace the body of `walk_inventory` from the `churn = _git_churn(...)` line to the end with:

```python
    entries: list[FileEntry] = []
    languages: set[str] = set()
    artefact_candidates: list[tuple[Path, str]] = []

    for path, rel_str in _iter_files(root, names, globs):
        ext = path.suffix.lower()
        lang = EXT_TO_LANG.get(ext)
        if lang is None:
            artefact_candidates.append((path, rel_str))
            continue
        try:
            with path.open(encoding="utf-8", errors="ignore") as handle:
                loc, indent_total, max_indent, deep, longest = _line_metrics(handle)
        except OSError as exc:
            raise InventoryError(f"could not read {path}: {exc}") from exc
        entries.append(
            FileEntry(
                path=rel_str,
                ext=ext,
                loc=loc,
                mtime=path.stat().st_mtime,
                complexity=indent_total,
                max_indent=max_indent,
                churn=0,
                language=lang,
                path_class=_classify_path(rel_str, extra_classes),
                deep_indent_lines=deep,
                longest_indented_run=longest,
            )
        )
        languages.add(lang)

    commits = git_log_pass(root, churn_months)
    git_available = commits is not None
    present = {e.path for e in entries} | {rel for _, rel in artefact_candidates}
    histories, bulk_excluded = derive_file_history(
        commits or [],
        present,
        is_test=lambda rel: _classify_path(rel, extra_classes) == "tests",
        bot_authors=[str(b) for b in cfg["bot_authors"]],
        bulk_threshold=int(cfg["coupling"]["bulk_threshold"]),
    )
    if git_available:
        for entry in entries:
            _apply_history(entry, histories[entry.path])
    artefacts = _walk_artefacts(root, artefact_candidates, histories if git_available else {})
    signal_sources: dict[str, str] = {}
    if git_available:
        signal_sources["git"] = datetime.now(UTC).isoformat(timespec="seconds")

    return {
        "schema_version": 2,
        "root": str(root),
        "total_files": len(entries),
        "total_loc": sum(e.loc for e in entries),
        "languages": sorted(languages),
        "git_available": git_available,
        "churn_window_months": churn_months,
        "hotspots": _build_hotspots(entries),
        "files": [asdict(e) for e in entries],
        "artefacts": artefacts,
        "git": _git_block(root, commits, bulk_excluded, cfg),
        "signal_sources": signal_sources,
    }
```

`subprocess` is no longer imported by `inventory.py` once `_git_churn` is gone; remove that import so ruff F401 stays clean.

(f) Replace the churn paragraph of the module docstring with:

```
  - ``churn`` and the history fields (``last_touched``, ``authors``,
    ``top_author``, ``top_author_share``, ``bugfix_share``,
    ``migration_commits``, ``flaky_commits``, ``untested_change_share``)
    come from one ``git log`` pass in ``git_history.py`` over the churn window
    (default 12 months), joined against the files present at HEAD. Without
    git ``churn`` is 0 and the history fields are null (``git_available``
    records which). The top-level ``git`` block carries authors, branches,
    tags and the window counts; ``signal_sources.git`` is the pass timestamp.
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest skills/tech-debt-scan/tests/test_inventory_v2.py skills/tech-debt-scan/tests/test_inventory.py -v`
Expected: all pass, including v1's `test_non_git_dir_has_zero_churn` and `test_inventory_carries_hotspot_summary_keys`.

- [ ] **Step 6: Lint and type-check**

Run: `ruff check . && mypy`
Expected: `All checks passed!`, `Success: no issues found`.

- [ ] **Step 7: Commit**

```bash
git add skills/tech-debt-scan/scripts/git_history.py skills/tech-debt-scan/scripts/inventory.py skills/tech-debt-scan/tests/test_inventory_v2.py
git commit -m "feat(tech-debt-scan): single git pass with authors, branches, tags and HEAD join"
```

---

### Task 7: change coupling and `coupling.json`

**Files:**
- Modify: `skills/tech-debt-scan/scripts/git_history.py` (append `change_coupling`)
- Modify: `skills/tech-debt-scan/scripts/inventory.py` (`walk_inventory` becomes `build_all` returning both documents plus a wrapper)
- Modify: `skills/tech-debt-scan/tests/test_inventory_v2.py` (append the Task 7 section)

**Interfaces:**
- Consumes: `Commit`, `git_log_pass`, `derive_file_history` (Task 6); `FileEntry`, `_classify_path` (Task 5); `deep_merge`, `DEFAULTS` (Task 1).
- Produces:
  - `git_history.change_coupling(commits: Sequence[Commit], present_source: set[str], *, min_shared: int, min_ratio: float, bulk_threshold: int) -> tuple[list[dict[str, Any]], dict[str, int]]` returning `(pairs, degree)`; pairs are `{"a", "b", "shared_commits", "ratio", "cross_directory"}` with `a < b`, ordered by shared commits descending, ratio descending, then names
  - `inventory.build_all(root: Path, *, ignore: tuple[str, ...] = DEFAULT_IGNORE, churn_months: int | None = None, config: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]` returning `(inventory, coupling)`; `churn_months=None` reads `config["churn_months"]`
  - `inventory.walk_inventory(...)` unchanged in signature, now `build_all(...)[0]`
  - the coupling document with keys `schema_version`, `min_shared`, `min_ratio`, `bulk_threshold`, `fan_in_mode`, `pairs`, `degree`, `cycles`, `directories`, `unstable_edges` (the last three are empty lists until Task 8)
  - every `files[]` entry's `coupling_degree` filled

**Spec:** 4.2 "Change coupling" (bulk exclusion, source-class only, `shared_commits >= 3`, `ratio = shared / mean(commits_a, commits_b) >= 0.30`, per-file `coupling_degree`), `coupling.json` shape.

**Confidence:** 95% (counting logic over the verified log pass; the corpus pair counts are pinned in Task 4).

- [ ] **Step 1: Write the failing tests**

Append to `skills/tech-debt-scan/tests/test_inventory_v2.py`:

```python
# --- Task 7: change coupling -----------------------------------------------------


def test_coupling_pairs_on_service_py(service_py_repo: Path) -> None:
    from inventory import build_all

    inventory, coupling = build_all(service_py_repo, churn_months=240)
    pairs = {(p["a"], p["b"]): p for p in coupling["pairs"]}
    key = ("src/pay/ledger.py", "src/pay/refund.py")
    assert key in pairs
    assert pairs[key]["shared_commits"] == 5
    assert pairs[key]["ratio"] == pytest.approx(5 / 7, abs=0.001)
    assert pairs[key]["cross_directory"] is False
    assert ("src/pay/ledger.py", "src/pay/models.py") not in pairs  # shared 2 < min_shared 3
    assert not any("tests/" in p["a"] or "tests/" in p["b"] for p in coupling["pairs"])
    assert coupling["degree"] == {"src/pay/ledger.py": 1, "src/pay/refund.py": 1}
    files = {e["path"]: e for e in inventory["files"]}
    assert files["src/pay/refund.py"]["coupling_degree"] == 1
    assert files["src/pay/gateway.py"]["coupling_degree"] == 0
    assert coupling["schema_version"] == 2
    assert (coupling["min_shared"], coupling["min_ratio"], coupling["bulk_threshold"]) == (
        3, 0.3, 50,
    )
    assert coupling["fan_in_mode"] == "auto"
    assert list(coupling) == [
        "schema_version", "min_shared", "min_ratio", "bulk_threshold", "fan_in_mode",
        "pairs", "degree", "cycles", "directories", "unstable_edges",
    ]


def test_coupling_pair_on_web_ts(web_ts_repo: Path) -> None:
    from inventory import build_all

    _, coupling = build_all(web_ts_repo, churn_months=240)
    pairs = {(p["a"], p["b"]): p for p in coupling["pairs"]}
    key = ("src/api/client-admin.ts", "src/api/client.ts")
    assert pairs[key]["shared_commits"] == 4
    assert pairs[key]["ratio"] == pytest.approx(4 / 4.5, abs=0.001)
    assert len(coupling["pairs"]) == 1


def test_coupling_thresholds_come_from_config(service_py_repo: Path) -> None:
    from config import DEFAULTS, deep_merge
    from inventory import build_all

    cfg = deep_merge(DEFAULTS, {"coupling": {"min_shared": 6}})
    _, coupling = build_all(service_py_repo, churn_months=240, config=cfg)
    assert coupling["pairs"] == []
    assert coupling["degree"] == {}
    assert coupling["min_shared"] == 6


def test_change_coupling_unit_ratio_bulk_and_cross_directory() -> None:
    from git_history import Commit, change_coupling

    def commit(sha: str, files: list[str]) -> Commit:
        return Commit(sha, "A", "a@example.com", "2026-01-01T00:00:00Z", "s", files)

    commits = [
        commit("1", ["x/a.py", "y/b.py"]),
        commit("2", ["x/a.py", "y/b.py"]),
        commit("3", ["x/a.py", "y/b.py", "x/c.py"]),
        commit("4", ["x/a.py", "x/c.py"]),
        commit("5", ["x/a.py", "x/c.py"]),
        *[commit(str(n), ["x/c.py"]) for n in range(10, 30)],
        commit("bulk", ["x/a.py", "y/b.py", "x/d.py"]),
    ]
    present = {"x/a.py", "y/b.py", "x/c.py", "x/d.py"}
    pairs, degree = change_coupling(
        commits, present, min_shared=3, min_ratio=0.30, bulk_threshold=2
    )
    assert [(p["a"], p["b"]) for p in pairs] == [("x/a.py", "y/b.py")]
    assert pairs[0]["shared_commits"] == 3
    assert pairs[0]["ratio"] == pytest.approx(3 / 4, abs=0.001)  # a 5 commits, b 3
    assert pairs[0]["cross_directory"] is True
    # a and c share 3 commits but c has 23, so ratio 3 / 14 is below 0.30
    assert degree == {"x/a.py": 1, "y/b.py": 1}


def test_coupling_empty_without_git(tmp_path: Path) -> None:
    from inventory import build_all

    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    inventory, coupling = build_all(tmp_path)
    assert inventory["git_available"] is False
    assert coupling["pairs"] == []
    assert coupling["degree"] == {}
    assert coupling["cycles"] == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest skills/tech-debt-scan/tests/test_inventory_v2.py -k coupling -v`
Expected: four tests FAIL with `ImportError: cannot import name 'build_all' from 'inventory'`; `test_change_coupling_unit_ratio_bulk_and_cross_directory` FAILS with `ImportError: cannot import name 'change_coupling' from 'git_history'`.

- [ ] **Step 3: Add `change_coupling` to `git_history.py`**

Append to `skills/tech-debt-scan/scripts/git_history.py`:

```python
def _dirname(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else ""


def change_coupling(
    commits: Sequence[Commit],
    present_source: set[str],
    *,
    min_shared: int,
    min_ratio: float,
    bulk_threshold: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Co-change pairs of source-class files (spec 4.2) and per-file degree.

    Bulk commits (more than ``bulk_threshold`` files) are skipped. A pair is
    emitted when ``shared >= min_shared`` and
    ``shared / mean(commits_a, commits_b) >= min_ratio``.
    """
    per_file: Counter[str] = Counter()
    pair_counts: Counter[tuple[str, str]] = Counter()
    for commit in commits:
        if len(commit.files) > bulk_threshold:
            continue
        files = sorted({path for path in commit.files if path in present_source})
        for path in files:
            per_file[path] += 1
        for index, first in enumerate(files):
            for second in files[index + 1 :]:
                pair_counts[(first, second)] += 1
    pairs: list[dict[str, Any]] = []
    degree: dict[str, int] = {}
    for (first, second), shared in pair_counts.items():
        if shared < min_shared:
            continue
        mean = (per_file[first] + per_file[second]) / 2
        ratio = shared / mean if mean else 0.0
        if ratio < min_ratio:
            continue
        pairs.append(
            {
                "a": first,
                "b": second,
                "shared_commits": shared,
                "ratio": round(ratio, 3),
                "cross_directory": _dirname(first) != _dirname(second),
            }
        )
        degree[first] = degree.get(first, 0) + 1
        degree[second] = degree.get(second, 0) + 1
    pairs.sort(key=lambda p: (-int(p["shared_commits"]), -float(p["ratio"]), p["a"], p["b"]))
    return pairs, dict(sorted(degree.items()))
```

- [ ] **Step 4: Turn `walk_inventory` into `build_all` plus a wrapper**

In `skills/tech-debt-scan/scripts/inventory.py`:

(a) Add `change_coupling` to the `git_history` import list.

(b) Rename the current `walk_inventory` to `build_all` with this signature and keep its body, changing the three places noted:

```python
def build_all(
    root: Path,
    *,
    ignore: tuple[str, ...] = DEFAULT_IGNORE,
    churn_months: int | None = None,
    config: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Walk ``root`` once and mine git once; return (inventory, coupling) documents."""
    root = root.resolve()
    if not root.exists():
        raise InventoryError(f"path not found: {root}")
    if not root.is_dir():
        raise InventoryError(f"path is not a directory: {root}")
    cfg = config if config is not None else copy.deepcopy(DEFAULTS)
    window = int(cfg["churn_months"]) if churn_months is None else churn_months
    names, globs = _ignore_sets(ignore, cfg)
    extra_classes: dict[str, list[str]] = cfg.get("path_classes") or {}
```

keep the walk loop and the git-pass lines that are already in the function body on disk (the `for path, rel_str in _iter_files(...)` loop, `commits = git_log_pass(...)`, `derive_file_history(...)`, `_apply_history(...)`, `_walk_artefacts(...)`, `signal_sources`) unchanged except for one line: replace `commits = git_log_pass(root, churn_months)` with `commits = git_log_pass(root, window)`. Then, after the `artefacts = ...` line, insert:

```python
    coupling_cfg = cfg["coupling"]
    present_source = {e.path for e in entries if e.path_class == "source"}
    pairs, degree = change_coupling(
        commits or [],
        present_source,
        min_shared=int(coupling_cfg["min_shared"]),
        min_ratio=float(coupling_cfg["min_ratio"]),
        bulk_threshold=int(coupling_cfg["bulk_threshold"]),
    )
    for entry in entries:
        entry.coupling_degree = degree.get(entry.path, 0)
```

and replace the final `return {...}` with:

```python
    inventory: dict[str, Any] = {
        "schema_version": 2,
        "root": str(root),
        "total_files": len(entries),
        "total_loc": sum(e.loc for e in entries),
        "languages": sorted(languages),
        "git_available": git_available,
        "churn_window_months": window,
        "hotspots": _build_hotspots(entries),
        "files": [asdict(e) for e in entries],
        "artefacts": artefacts,
        "git": _git_block(root, commits, bulk_excluded, cfg),
        "signal_sources": signal_sources,
    }
    coupling: dict[str, Any] = {
        "schema_version": 2,
        "min_shared": int(coupling_cfg["min_shared"]),
        "min_ratio": float(coupling_cfg["min_ratio"]),
        "bulk_threshold": int(coupling_cfg["bulk_threshold"]),
        "fan_in_mode": str(cfg["fan_in"]["mode"]),
        "pairs": pairs,
        "degree": degree,
        "cycles": [],
        "directories": [],
        "unstable_edges": [],
    }
    return inventory, coupling
```

(c) Add the compatibility wrapper directly after `build_all`:

```python
def walk_inventory(
    root: Path,
    ignore: tuple[str, ...] = DEFAULT_IGNORE,
    churn_months: int = DEFAULT_CHURN_MONTHS,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """v1 entry point: the inventory document only (see ``build_all``)."""
    inventory, _coupling = build_all(root, ignore=ignore, churn_months=churn_months, config=config)
    return inventory
```

(d) Add to the module docstring:

```
``coupling.json`` (spec 4.2) comes from the same pass: pairs of source-class
files co-committed at least ``coupling.min_shared`` times with
``shared / mean(commits_a, commits_b) >= coupling.min_ratio``, bulk commits
excluded, plus per-file ``coupling_degree``. ``build_all`` returns both
documents; ``walk_inventory`` keeps the v1 signature and returns the first.
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest skills/tech-debt-scan/tests/test_inventory_v2.py skills/tech-debt-scan/tests/test_inventory.py skills/tech-debt-scan/tests/test_e2e.py -v`
Expected: all pass.

- [ ] **Step 6: Lint and type-check**

Run: `ruff check . && mypy`
Expected: `All checks passed!`, `Success: no issues found`.

- [ ] **Step 7: Commit**

```bash
git add skills/tech-debt-scan/scripts/git_history.py skills/tech-debt-scan/scripts/inventory.py skills/tech-debt-scan/tests/test_inventory_v2.py
git commit -m "feat(tech-debt-scan): change coupling pairs, coupling degree and the coupling document"
```

---

### Task 8: the approximate reference graph (`reference_graph.py`)

**Files:**
- Create: `skills/tech-debt-scan/scripts/reference_graph.py`
- Modify: `skills/tech-debt-scan/scripts/inventory.py` (`build_all` keeps file text, builds the graph, fills `fan_in_approx`, `fan_out_approx`, `fan_in_mode`, and the coupling document's `cycles`, `directories`, `unstable_edges`)
- Modify: `skills/tech-debt-scan/tests/test_inventory_v2.py` (append the Task 8 section)

**Interfaces:**
- Consumes: `build_all`, `FileEntry` (Tasks 5 to 7); `DEFAULTS`, `deep_merge` (Task 1); the corpus fixtures (Task 4).
- Produces (`reference_graph.py`, used by Task 10's `patterns.py` for import lines and logical lines):
  - `IMPORT_LINE_RE`, `IMPORT_CALL_RE`, `TOKEN_RE: re.Pattern[str]`
  - `MAX_CONTINUATION: int = 200`
  - `@dataclass(slots=True) class GraphFile(path: str, language: str, path_class: str, text: str, loc: int = 0, churn: int = 0)`
  - `@dataclass(slots=True) class GraphResult(fan_in: dict[str, int | None], fan_out: dict[str, int], mode: dict[str, str], edges: list[tuple[str, str]], ambiguous: dict[str, str], cycles: list[dict[str, Any]], directories: list[dict[str, Any]], unstable_edges: list[dict[str, Any]])`
  - `def file_stem(path: str) -> str` (basename before the first dot, lower-cased)
  - `def numbered_logical_lines(lines: Sequence[str]) -> list[tuple[int, str]]` (continuation joining; each entry keeps its 1-based start line) and `def logical_lines(text: str) -> list[str]`
  - `def is_import_line(line: str) -> bool`, `def import_lines(text: str) -> list[str]`
  - `def identifier_tokens(text: str) -> set[str]`
  - `def tarjan_scc(adjacency: dict[str, set[str]]) -> list[list[str]]`
  - `def build_reference_graph(files: Sequence[GraphFile], fan_in_cfg: dict[str, Any]) -> GraphResult`
  - in `inventory.py`, `build_all` now reads each file's text once (`path.read_bytes().decode("utf-8", errors="ignore")`) and keeps it in a `texts: dict[str, str]` local that Task 9 also uses for docs.

**Spec:** 4.2 "Approximate fan-in" (tokenisation, `min_stem_length` 4, inverted stem index, import-line regex verbatim, continuation joining, `auto` mode with repository-wide anywhere fallback, mechanical ambiguity with the three config lists, ordinary-modules-only corroboration, `fan_out_approx`, directory aggregates with instability, `unstable_edges`) and "Cycles" (Tarjan SCCs of size 2 to 5 from the import-line graph only, capped leads, `source: "import-lines"`, `lead_only: true`).

**Decisions the spec leaves open, fixed here:** targets are source-class files; referrers are source-class and tests-class files (a module imported only by its test is not "fan-in 0"); a stem shorter than `min_stem_length` makes the file ambiguous with reason `short-stem`; the continuation rule joins while the buffer has an unclosed `(`, `[` or `{`, ends in `\` or ends in `,`, capped at `MAX_CONTINUATION` lines, so a Go `import (` block joins to its `)`; a target's `fan_in_mode` is `anywhere` when any counted edge into it came from an anywhere-mode referrer; directory aggregates and unstable edges count edges between source-class files only; `cycles` use import-lines edges only.

**Confidence:** 90% (the regex and stem rule were measured on Python only; the corpus hand counts below give the TypeScript and Go check, and every count is derived from the fixture imports listed in Task 4).

- [ ] **Step 1: Write the failing tests**

Append to `skills/tech-debt-scan/tests/test_inventory_v2.py`:

```python
# --- Task 8: reference graph ----------------------------------------------------


def test_fan_in_on_web_ts_matches_hand_count(web_ts_repo: Path) -> None:
    from inventory import build_all

    inventory, _ = build_all(web_ts_repo, churn_months=240)
    files = {e["path"]: e for e in inventory["files"]}
    expected = {
        "src/cart/cart.ts": 4,  # stock (type import), checkout, index, cart.test
        "src/cart/pricing.ts": 3,  # cart, checkout, pricing.spec
        "src/cart/stock.ts": 1,  # pricing
        "src/checkout/checkout.ts": 1,  # index
        "src/util/format-legacy.ts": 1,  # checkout: the deprecated helper still has a caller
        "src/util/format.ts": 1,  # format-legacy
        "src/flags.ts": 3,  # checkout, client, client-admin
        "src/api/client.ts": 0,
        "src/api/client-admin.ts": 0,
    }
    for path, fan_in in expected.items():
        assert files[path]["fan_in_approx"] == fan_in, path
        assert files[path]["fan_in_mode"] == "import-lines", path
    assert files["src/index.ts"]["fan_in_approx"] is None  # package and stoplist name
    assert files["src/index.ts"]["fan_out_approx"] == 2
    assert files["src/checkout/checkout.ts"]["fan_out_approx"] == 4
    assert files["src/__tests__/cart.test.ts"]["fan_in_approx"] is None
    assert files["src/__tests__/cart.test.ts"]["fan_out_approx"] is None
    assert files["vendor/tiny-emitter.js"]["fan_out_approx"] is None


def test_three_file_cycle_found_in_web_ts(web_ts_repo: Path) -> None:
    from inventory import build_all

    _, coupling = build_all(web_ts_repo, churn_months=240)
    assert coupling["cycles"] == [
        {
            "members": ["src/cart/cart.ts", "src/cart/pricing.ts", "src/cart/stock.ts"],
            "approximate": True,
            "source": "import-lines",
            "lead_only": True,
        }
    ]


def test_service_py_fan_in_ambiguity_and_no_cycle(service_py_repo: Path) -> None:
    from inventory import build_all

    inventory, coupling = build_all(service_py_repo, churn_months=240)
    assert coupling["cycles"] == []
    files = {e["path"]: e for e in inventory["files"]}
    # tests/test_refund.py imports the module; tests/conftest.py's `Refund` class import also
    # matches the stem, which is the documented imprecision of stem matching
    assert files["src/pay/refund.py"]["fan_in_approx"] == 2
    assert files["src/pay/ledger.py"]["fan_in_approx"] == 2  # refund, tests/test_ledger.py
    assert files["src/pay/gateway.py"]["fan_in_approx"] == 1  # refund
    assert files["src/pay/legacy_export.py"]["fan_in_approx"] == 0
    assert files["src/pay/refund.py"]["fan_out_approx"] == 2  # ledger, gateway
    for ambiguous in ("src/pay/__init__.py", "src/pay/models.py", "src/pay/utils.py", "setup.py"):
        assert files[ambiguous]["fan_in_approx"] is None, ambiguous


def test_go_import_block_continuation(mixed_decoys_repo: Path) -> None:
    from inventory import build_all

    inventory, coupling = build_all(mixed_decoys_repo, churn_months=240)
    files = {e["path"]: e for e in inventory["files"]}
    # lookup is referenced only inside store.go's multi-line `import (` block
    assert files["internal/lookup/lookup.go"]["fan_in_approx"] == 1
    assert files["internal/store/store.go"]["fan_in_approx"] == 1
    assert files["internal/dispatch/dispatch.go"]["fan_in_approx"] == 1
    assert files["internal/flags/flags.go"]["fan_in_approx"] == 1
    assert files["internal/httpc/httpc.go"]["fan_in_approx"] == 1
    assert files["internal/httpc/httpc_safe.go"]["fan_in_approx"] == 0
    # the package directory `build` is never mapped to builder.go (spec 4.2)
    assert files["internal/build/builder.go"]["fan_in_approx"] == 0
    assert files["cmd/app/main.go"]["fan_in_approx"] is None
    assert files["cmd/app/main.go"]["fan_out_approx"] == 4
    assert coupling["cycles"] == []


def test_shared_and_short_stems_are_ambiguous(tmp_path: Path) -> None:
    from inventory import build_all

    for rel, content in {
        "a/report.py": "x = 1\n",
        "b/report.py": "y = 2\n",
        "lib/db.py": "z = 3\n",
        "runner.py": "from a import report\nfrom lib import db\n",
    }.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    inventory, _ = build_all(tmp_path)
    files = {e["path"]: e for e in inventory["files"]}
    assert files["a/report.py"]["fan_in_approx"] is None
    assert files["b/report.py"]["fan_in_approx"] is None
    assert files["lib/db.py"]["fan_in_approx"] is None  # stem shorter than 4
    assert files["runner.py"]["fan_in_approx"] == 0
    assert files["runner.py"]["fan_out_approx"] == 0


def test_anywhere_fallback_is_labelled(tmp_path: Path) -> None:
    from config import DEFAULTS, deep_merge
    from inventory import build_all

    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "renderer.php").write_text(
        "<?php\nclass Renderer {\n    public function draw() {}\n}\n", encoding="utf-8"
    )
    (tmp_path / "webapp.php").write_text(
        "<?php\n$r = new Renderer();\n$r->draw();\n", encoding="utf-8"
    )
    inventory, coupling = build_all(tmp_path)
    files = {e["path"]: e for e in inventory["files"]}
    assert files["lib/renderer.php"]["fan_in_approx"] == 1
    assert files["lib/renderer.php"]["fan_in_mode"] == "anywhere"
    assert files["webapp.php"]["fan_in_approx"] == 0
    assert coupling["cycles"] == []
    strict = deep_merge(DEFAULTS, {"fan_in": {"mode": "import-lines"}})
    inventory, _ = build_all(tmp_path, config=strict)
    files = {e["path"]: e for e in inventory["files"]}
    assert files["lib/renderer.php"]["fan_in_approx"] == 0
    assert files["lib/renderer.php"]["fan_in_mode"] == "import-lines"


def test_directories_unstable_edges_and_scc_size_bounds(tmp_path: Path) -> None:
    from inventory import build_all

    for rel, content in {
        "app/alpha.py": "from core import engine\n",
        "app/bravo.py": "from core import engine\n",
        "app/charlie.py": "from core import engine\n",
        "core/engine.py": "from plugins import loader\n",
        "plugins/loader.py": "from app import alpha, bravo, charlie\n",
        "zeta/omega.py": "from core import engine\n",
    }.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    _, coupling = build_all(tmp_path)
    dirs = {d["path"]: d for d in coupling["directories"]}
    assert dirs["app"]["files"] == 3
    assert (dirs["app"]["fan_in"], dirs["app"]["fan_out"]) == (3, 3)
    assert dirs["app"]["instability"] == 0.5
    assert (dirs["core"]["fan_in"], dirs["core"]["fan_out"]) == (4, 1)
    assert dirs["core"]["instability"] == 0.2
    assert (dirs["plugins"]["fan_in"], dirs["plugins"]["fan_out"]) == (1, 3)
    assert dirs["plugins"]["instability"] == 0.75
    assert dirs["zeta"]["instability"] == 1.0
    assert coupling["unstable_edges"] == [
        {"from": "core", "to": "plugins", "from_instability": 0.2, "to_instability": 0.75}
    ]
    assert [c["members"] for c in coupling["cycles"]] == [
        ["app/alpha.py", "app/bravo.py", "app/charlie.py", "core/engine.py", "plugins/loader.py"]
    ]


def test_scc_larger_than_five_is_not_a_lead(tmp_path: Path) -> None:
    from inventory import build_all

    names = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot"]
    for index, name in enumerate(names):
        nxt = names[(index + 1) % len(names)]
        (tmp_path / f"{name}.py").write_text(f"import {nxt}\n", encoding="utf-8")
    _, coupling = build_all(tmp_path)
    assert coupling["cycles"] == []


def test_tarjan_scc_unit() -> None:
    from reference_graph import tarjan_scc

    adjacency = {"a": {"b"}, "b": {"c"}, "c": {"a"}, "d": {"a"}, "e": set()}
    components = tarjan_scc(adjacency)
    assert ["a", "b", "c"] in components
    assert ["d"] in components
    assert ["e"] in components
    assert len(components) == 3


def test_logical_lines_and_import_lines_unit() -> None:
    from reference_graph import import_lines, logical_lines

    go = 'package x\n\nimport (\n\t"fmt"\n\n\t"example.com/app/internal/store"\n)\n\nfunc f() {}\n'
    joined = logical_lines(go)
    assert any(line.startswith("import (") and "store" in line for line in joined)
    py = "from pay import (\n    ledger,\n    gateway,\n)\nx = call(a,\n    b)\n"
    assert import_lines(py) == ["from pay import ( ledger, gateway, )"]
    ts = 'const m = await import("./lazy");\nconst r = require("./req");\nlet x = 1;\n'
    assert len(import_lines(ts)) == 2
    assert import_lines("x = 1\ny = 2\n") == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest skills/tech-debt-scan/tests/test_inventory_v2.py -k "fan_in or cycle or ambigu or anywhere or directories or scc or tarjan or logical" -v`
Expected: `test_fan_in_on_web_ts_matches_hand_count` FAILS with `AssertionError: src/cart/cart.ts` (`fan_in_approx` is still `None`), `test_three_file_cycle_found_in_web_ts` FAILS with `AssertionError: assert [] == [{...}]`, `test_tarjan_scc_unit` and `test_logical_lines_and_import_lines_unit` FAIL with `ModuleNotFoundError: No module named 'reference_graph'`.

- [ ] **Step 3: Write `reference_graph.py`**

Create `skills/tech-debt-scan/scripts/reference_graph.py`:

```python
"""Approximate file reference graph by identifier stems (spec 4.2).

Each source file is a target whose stem is its basename before the first dot,
lower-cased. Every source and tests file is a referrer: its identifier tokens
(``TOKEN_RE``, which keeps hyphenated module names whole) are intersected with
an inverted stem index, one set operation per file.

Two modes. ``import-lines`` (the default) only looks at import-like logical
lines: a line matching ``IMPORT_LINE_RE`` or containing ``require(``,
``import(``, ``from "`` or ``from '``; lines are joined while a bracket is
open or the line ends in a backslash or a comma, so multi-line imports and
Go ``import (`` blocks count. ``anywhere`` matches tokens over the whole file
and is the labelled lower-confidence fallback; under ``mode: auto`` it applies
to every file of a language that matched no import-like line anywhere in the
repository, and the targets it reaches are marked ``fan_in_mode: anywhere``.

Ambiguity is mechanical: a target with a stem shorter than
``min_stem_length``, a stem shared by two or more targets, a package or index
name, a test-harness name, or a stoplist name gets ``fan_in_approx`` None.
Package files are never mapped to their directory name and the stoplist is
never extended with domain vocabulary.

Cycles are Tarjan SCCs of size 2 to 5 over import-lines edges only, emitted
as capped leads for the architecture scout, never as findings. Directory
aggregates and unstable edges use edges between source files.
"""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

IMPORT_LINE_RE = re.compile(
    r"^\s*(import|from|using|use|require|include|#include|load|open|extern crate|package|"
    r"require_relative|@import|@use)\b"
)
IMPORT_CALL_RE = re.compile(r"require\(|import\(|from \"|from '")
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
MAX_CONTINUATION = 200
MIN_CYCLE = 2
MAX_CYCLE = 5
_OPEN = "([{"
_CLOSE = ")]}"


@dataclass(slots=True)
class GraphFile:
    path: str
    language: str
    path_class: str
    text: str
    loc: int = 0
    churn: int = 0


@dataclass(slots=True)
class GraphResult:
    fan_in: dict[str, int | None] = field(default_factory=dict)
    fan_out: dict[str, int] = field(default_factory=dict)
    mode: dict[str, str] = field(default_factory=dict)
    edges: list[tuple[str, str]] = field(default_factory=list)
    ambiguous: dict[str, str] = field(default_factory=dict)
    cycles: list[dict[str, Any]] = field(default_factory=list)
    directories: list[dict[str, Any]] = field(default_factory=list)
    unstable_edges: list[dict[str, Any]] = field(default_factory=list)


def file_stem(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    return name.split(".", 1)[0].lower()


def _dirname(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else ""


def _unclosed(text: str) -> bool:
    depth = 0
    for char in text:
        if char in _OPEN:
            depth += 1
        elif char in _CLOSE:
            depth -= 1
    return depth > 0


def _continues(buffer: str) -> bool:
    stripped = buffer.rstrip()
    return bool(stripped) and (stripped.endswith(("\\", ",")) or _unclosed(stripped))


def numbered_logical_lines(lines: Sequence[str]) -> list[tuple[int, str]]:
    """(1-based start line, joined text): continuations joined by a single space."""
    out: list[tuple[int, str]] = []
    buffer = ""
    start = 0
    joined = 0
    for index, raw in enumerate(lines, start=1):
        if buffer:
            buffer = buffer + " " + raw.strip()
            joined += 1
        else:
            buffer = raw
            start = index
            joined = 0
        if _continues(buffer) and joined < MAX_CONTINUATION:
            continue
        out.append((start, buffer))
        buffer = ""
    if buffer:
        out.append((start, buffer))
    return out


def logical_lines(text: str) -> list[str]:
    """Physical lines with continuations joined by a single space."""
    return [line for _, line in numbered_logical_lines(text.splitlines())]


def is_import_line(line: str) -> bool:
    return bool(IMPORT_LINE_RE.match(line) or IMPORT_CALL_RE.search(line))


def import_lines(text: str) -> list[str]:
    return [line for line in logical_lines(text) if is_import_line(line)]


def identifier_tokens(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text)}


def tarjan_scc(adjacency: dict[str, set[str]]) -> list[list[str]]:
    """Strongly connected components (iterative Tarjan), each sorted, in finish order."""
    index_of: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    result: list[list[str]] = []
    counter = 0
    for root in sorted(adjacency):
        if root in index_of:
            continue
        index_of[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        work = [(root, iter(sorted(adjacency.get(root, ()))))]
        while work:
            node, children = work[-1]
            descended = False
            for child in children:
                if child not in adjacency:
                    continue
                if child not in index_of:
                    index_of[child] = low[child] = counter
                    counter += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, iter(sorted(adjacency.get(child, ())))))
                    descended = True
                    break
                if child in on_stack:
                    low[node] = min(low[node], index_of[child])
            if descended:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index_of[node]:
                component: list[str] = []
                while True:
                    top = stack.pop()
                    on_stack.discard(top)
                    component.append(top)
                    if top == node:
                        break
                result.append(sorted(component))
    return result


def _round(value: float) -> float:
    return round(value, 3)


def build_reference_graph(files: Sequence[GraphFile], fan_in_cfg: dict[str, Any]) -> GraphResult:
    """Fan-in, fan-out, modes, cycles and directory aggregates for ``files``."""
    mode_cfg = str(fan_in_cfg.get("mode", "auto"))
    min_len = int(fan_in_cfg.get("min_stem_length", 4))
    ambiguous_cfg = fan_in_cfg.get("ambiguous") or {}
    shared_stem = bool(ambiguous_cfg.get("shared_stem", True))
    package_files = {str(n) for n in ambiguous_cfg.get("package_files") or []}
    harness_files = {str(n) for n in ambiguous_cfg.get("harness_files") or []}
    stoplist = {str(n) for n in fan_in_cfg.get("stoplist") or []}

    targets = [f for f in files if f.path_class == "source"]
    referrers = [f for f in files if f.path_class in ("source", "tests")]
    stem_of = {f.path: file_stem(f.path) for f in targets}
    stem_count = Counter(stem_of.values())

    result = GraphResult()
    index: dict[str, str] = {}
    for path, stem in stem_of.items():
        if len(stem) < min_len:
            result.ambiguous[path] = "short-stem"
        elif shared_stem and stem_count[stem] > 1:
            result.ambiguous[path] = "shared-stem"
        elif stem in package_files:
            result.ambiguous[path] = "package-file"
        elif stem in harness_files:
            result.ambiguous[path] = "harness-file"
        elif stem in stoplist:
            result.ambiguous[path] = "stoplist"
        else:
            index[stem] = path
    result.fan_in = {p: (None if p in result.ambiguous else 0) for p in stem_of}
    result.fan_out = {p: 0 for p in stem_of}
    result.mode = dict.fromkeys(stem_of, "import-lines")

    lines_of = {f.path: import_lines(f.text) for f in referrers}
    lang_has_imports: set[str] = {f.language for f in referrers if lines_of[f.path]}

    def mode_for(referrer: GraphFile) -> str:
        if mode_cfg == "import-lines":
            return "import-lines"
        if mode_cfg == "anywhere":
            return "anywhere"
        return "import-lines" if referrer.language in lang_has_imports else "anywhere"

    strict_edges: list[tuple[str, str]] = []
    stems = set(index)
    for referrer in referrers:
        mode = mode_for(referrer)
        if mode == "import-lines":
            tokens = identifier_tokens("\n".join(lines_of[referrer.path]))
        else:
            tokens = identifier_tokens(referrer.text)
        for stem in sorted(tokens & stems):
            target = index[stem]
            if target == referrer.path:
                continue
            result.edges.append((referrer.path, target))
            current = result.fan_in[target]
            result.fan_in[target] = (current or 0) + 1
            if referrer.path in result.fan_out:
                result.fan_out[referrer.path] += 1
            if mode == "anywhere":
                result.mode[target] = "anywhere"
            else:
                strict_edges.append((referrer.path, target))

    adjacency: dict[str, set[str]] = {p: set() for p in index.values()}
    for source, target in strict_edges:
        if source in adjacency:
            adjacency[source].add(target)
    for component in tarjan_scc(adjacency):
        if MIN_CYCLE <= len(component) <= MAX_CYCLE:
            result.cycles.append(
                {"members": component, "approximate": True, "source": "import-lines",
                 "lead_only": True}
            )
    result.cycles.sort(key=lambda c: c["members"])

    dir_files: Counter[str] = Counter()
    dir_loc: Counter[str] = Counter()
    dir_churn: Counter[str] = Counter()
    for target in targets:
        directory = _dirname(target.path)
        dir_files[directory] += 1
        dir_loc[directory] += target.loc
        dir_churn[directory] += target.churn
    dir_in: Counter[str] = Counter()
    dir_out: Counter[str] = Counter()
    dir_edges: set[tuple[str, str]] = set()
    for source, target in result.edges:
        if source not in stem_of:
            continue  # tests-class referrers do not shape directory structure
        from_dir, to_dir = _dirname(source), _dirname(target)
        if from_dir == to_dir:
            continue
        dir_out[from_dir] += 1
        dir_in[to_dir] += 1
        dir_edges.add((from_dir, to_dir))
    instability: dict[str, float] = {}
    for directory in sorted(dir_files):
        total = dir_in[directory] + dir_out[directory]
        instability[directory] = _round(dir_out[directory] / total) if total else 0.0
        result.directories.append(
            {
                "path": directory,
                "files": dir_files[directory],
                "loc": dir_loc[directory],
                "churn": dir_churn[directory],
                "fan_in": dir_in[directory],
                "fan_out": dir_out[directory],
                "instability": instability[directory],
            }
        )
    for from_dir, to_dir in sorted(dir_edges):
        if instability[from_dir] < 0.3 and instability[to_dir] > 0.7:
            result.unstable_edges.append(
                {
                    "from": from_dir,
                    "to": to_dir,
                    "from_instability": instability[from_dir],
                    "to_instability": instability[to_dir],
                }
            )
    return result
```

- [ ] **Step 4: Wire the graph into `build_all`**

In `skills/tech-debt-scan/scripts/inventory.py`:

(a) Add `from reference_graph import GraphFile, build_reference_graph` to the imports.

(b) In the walk loop of `build_all`, read the text once and keep it. Replace

```python
        try:
            with path.open(encoding="utf-8", errors="ignore") as handle:
                loc, indent_total, max_indent, deep, longest = _line_metrics(handle)
        except OSError as exc:
            raise InventoryError(f"could not read {path}: {exc}") from exc
```

with

```python
        try:
            text = path.read_bytes().decode("utf-8", errors="ignore")
        except OSError as exc:
            raise InventoryError(f"could not read {path}: {exc}") from exc
        texts[rel_str] = text
        loc, indent_total, max_indent, deep, longest = _line_metrics(
            text.splitlines(keepends=True)
        )
```

and declare `texts: dict[str, str] = {}` next to `entries: list[FileEntry] = []`.

(c) After the coupling-degree loop (`for entry in entries: entry.coupling_degree = ...`) insert:

```python
    graph = build_reference_graph(
        [
            GraphFile(
                path=e.path, language=e.language, path_class=e.path_class,
                text=texts[e.path], loc=e.loc, churn=e.churn,
            )
            for e in entries
            if e.path_class in ("source", "tests")
        ],
        cfg["fan_in"],
    )
    for entry in entries:
        if entry.path_class == "source":
            entry.fan_in_approx = graph.fan_in.get(entry.path)
            entry.fan_out_approx = graph.fan_out.get(entry.path)
            entry.fan_in_mode = graph.mode.get(entry.path, "import-lines")
```

(d) In the coupling document, replace the three empty lists with `graph.cycles`, `graph.directories`, `graph.unstable_edges`.

(e) Add to the module docstring:

```
Approximate fan-in and fan-out (``reference_graph.py``): identifier-stem
matching over import-like lines by default, whole-file matching as the
labelled ``anywhere`` fallback, mechanical ambiguity (shared, short, package,
harness and stoplist stems give ``fan_in_approx`` null). Import-line SCCs of
size 2 to 5 are the ``cycles`` leads in ``coupling.json``, with directory
aggregates and ``unstable_edges``.
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest skills/tech-debt-scan/tests/test_inventory_v2.py skills/tech-debt-scan/tests/test_inventory.py -v`
Expected: all pass. If `test_fan_in_on_web_ts_matches_hand_count` reports one count off, print `graph.edges` for that repository and compare with the import lines listed in Task 4 before touching the rule: the hand count is derived from those imports and the rule, not from a run.

- [ ] **Step 6: Lint and type-check**

Run: `ruff check . && mypy`
Expected: `All checks passed!`, `Success: no issues found`.

- [ ] **Step 7: Commit**

```bash
git add skills/tech-debt-scan/scripts/reference_graph.py skills/tech-debt-scan/scripts/inventory.py skills/tech-debt-scan/tests/test_inventory_v2.py
git commit -m "feat(tech-debt-scan): approximate reference graph with fan-in, cycles and directory instability"
```

---

### Task 9: hotspot band, `hotspot_score`, blame share, test mapping, docs and tests blocks, `--workdir` CLI

**Files:**
- Modify: `skills/tech-debt-scan/scripts/inventory.py` (new helpers, the final `build_all`, `write_outputs`, `_main`, module docstring)
- Modify: `skills/tech-debt-scan/tests/test_inventory_v2.py` (append the Task 9 section)

**Interfaces:**
- Consumes: everything from Tasks 5 to 8; `blame_top_share` (Task 6); `load_config`, `ConfigError` (Task 1); `file_stem` (Task 8).
- Produces (used by Tasks 10 to 13):
  - `HOTSPOT_BLAME_CAP: int = 50`
  - `def _score_entries(entries: list[FileEntry]) -> None` (fills `hotspot_score` with the `_build_hotspots` formula)
  - `def _hotspot_band(entries: list[FileEntry], band_cfg: dict[str, Any]) -> list[str]`
  - `def _map_tests(entries: list[FileEntry]) -> None`
  - `def _tests_block(entries, artefacts, root) -> dict[str, Any]` (`test_to_source_ratio`, `coverage_gate`, `ci_retry_config`)
  - `def _docs_block(entries, artefacts, texts, git_block, git_available) -> dict[str, Any]`
  - `def _tooling_blocks(root: Path) -> tuple[list[str], list[str]]` (`boundary_tooling`, `lint_config`)
  - `def write_json(path: Path, document: dict[str, Any]) -> None` (LF-only JSON via `write_bytes`; Tasks 10 to 12 import it)
  - `def write_outputs(inventory: dict[str, Any], coupling: dict[str, Any], workdir: Path) -> tuple[Path, Path]` (LF-only `inventory.json` and `coupling.json`)
  - `_main(argv)` accepting `path`, `--workdir` (default `.tech-debt`), `--out` (v1 behaviour: only `inventory.json` at that path), `--churn-months`
  - the final top-level key order of `inventory.json`: `schema_version, root, total_files, total_loc, languages, git_available, churn_window_months, hotspots, hotspot_band, files, artefacts, docs, tests, git, boundary_tooling, lint_config, signal_sources`

**Spec:** 4.2 "Hotspots" (v1 `hotspots` shape and key set unchanged, `hotspot_score` on every entry, `hotspot_band` = top `fraction` 0.10 of source-class files, at least `min` 5 and at most `max` 50), blame on hotspot-band files capped at 50 giving `top_author_line_share`, "Test mapping" (the seven globs, same directory or any tests-class tree, `tests.test_to_source_ratio`, `tests.coverage_gate` by filename or key `fail_under`, `coverageThreshold`, `check-coverage`, `codecov.yml`, `tests.ci_retry_config`), "Docs block" (every listed key), `inventory.json` shape, `inline_disables` emitted 0, 3.3 (`--workdir`, `--out` kept). SKILL.md step 1's command (`--out .tech-debt/inventory.json`) keeps working unchanged.

**Decisions the spec leaves open, fixed here:** files with `hotspot_score` 0 never enter the band; the band size is `min(max(ceil(fraction * n_source), min), max)` truncated to the scored files available; `ci_retry_config` lists ci artefacts whose text matches `retry|rerun|retries|max_attempts` (case-insensitive); a doc token is a candidate reference when it sits in backticks or looks like a path and either carries a known code or config extension or starts with an existing top-level directory, and it is dangling when no walked path equals it, ends with it or lives under it and its stem is not a source stem (capped at 200); `stale_vs_code_days` is the whole-day distance between the doc's `last_touched` and the newest source `last_touched`; `boundary_tooling` and `lint_config` are detected by root file names (`.importlinter`, `.dependency-cruiser.*`, `.eslintrc*`, `eslint.config.*`, `tslint.json`, `ruff.toml`, `.ruff.toml`, `.flake8`, `.pylintrc`, `.golangci.yml`, `.rubocop.yml`, `stylecop.json`) plus `[tool.importlinter]`, `[tool.ruff]`, `[tool.flake8]` or `[tool.pylint]` inside `pyproject.toml`.

**Confidence:** 91% (assembly of verified pieces; the docs-block date arithmetic is checked against the fixture dates below, and `datetime.fromisoformat` accepts the `Z` suffix on Python 3.11+).

- [ ] **Step 1: Write the failing tests**

Append to `skills/tech-debt-scan/tests/test_inventory_v2.py`:

```python
# --- Task 9: band, score, blame, mapping, docs, tests block, CLI -------------------


def test_hotspot_score_band_and_blame_on_service_py(service_py_repo: Path) -> None:
    result = walk_inventory(service_py_repo, churn_months=240)
    files = {e["path"]: e for e in result["files"]}
    assert result["hotspots"][0]["path"] == "src/pay/refund.py"
    assert set(result["hotspots"][0]) == {"path", "churn", "complexity", "loc", "score"}
    assert files["src/pay/refund.py"]["hotspot_score"] == result["hotspots"][0]["score"]
    assert files["src/pay/refund.py"]["hotspot_score"] == 100.0
    assert files["setup.py"]["hotspot_score"] == 0.0
    band = result["hotspot_band"]
    assert band[0] == "src/pay/refund.py"
    assert "src/pay/ledger.py" in band
    assert len(band) == 5  # 8 source files: ceil(0.8) = 1, floored to min 5
    assert all(files[p]["path_class"] == "source" for p in band)
    assert "setup.py" not in band  # score 0 never enters the band
    assert files["src/pay/refund.py"]["top_author_line_share"] == 1.0
    ledger_share = files["src/pay/ledger.py"]["top_author_line_share"]
    assert ledger_share is not None and ledger_share < 1.0
    assert files["tests/test_refund.py"]["top_author_line_share"] is None


def test_hotspot_band_bounds() -> None:
    from inventory import FileEntry, _hotspot_band

    def entries(count: int) -> list[FileEntry]:
        out: list[FileEntry] = []
        for index in range(count):
            entry = FileEntry(f"f{index}.py", ".py", 1, 0.0, 1, 1, 1, language="python")
            entry.hotspot_score = float(count - index)
            out.append(entry)
        return out

    band_cfg = {"fraction": 0.10, "min": 5, "max": 50}
    assert len(_hotspot_band(entries(600), band_cfg)) == 50
    assert len(_hotspot_band(entries(200), band_cfg)) == 20
    assert len(_hotspot_band(entries(30), band_cfg)) == 5
    assert _hotspot_band(entries(3), band_cfg) == ["f0.py", "f1.py", "f2.py"]
    zero = entries(10)
    for entry in zero:
        entry.hotspot_score = 0.0
    assert _hotspot_band(zero, band_cfg) == []
    tests_only = entries(10)
    for entry in tests_only:
        entry.path_class = "tests"
    assert _hotspot_band(tests_only, band_cfg) == []


def test_test_mapping_across_seven_conventions(tmp_path: Path) -> None:
    pairs = {
        "src/alpha.py": "tests/test_alpha.py",
        "src/bravo.go": "src/bravo_test.go",
        "src/charlie.ts": "src/__tests__/charlie.test.ts",
        "src/delta.ts": "spec/delta.spec.ts",
        "lib/echo.rb": "spec/echo_spec.rb",
        "src/Foxtrot.java": "test/FoxtrotTest.java",
        "src/Golf.cs": "tests/GolfTests.cs",
    }
    for rel in [*pairs, *pairs.values(), "src/hotel.py"]:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x = 1\n", encoding="utf-8")
    files = {e["path"]: e for e in walk_inventory(tmp_path)["files"]}
    for source, test in pairs.items():
        assert files[source]["mapped_tests"] == [test], source
        assert files[test]["mapped_tests"] == []
    assert files["src/hotel.py"]["mapped_tests"] == []


def test_tests_block_on_corpus(service_py_repo: Path, web_ts_repo: Path) -> None:
    service = walk_inventory(service_py_repo, churn_months=240)["tests"]
    assert service == {
        "test_to_source_ratio": 0.5,
        "coverage_gate": ["pyproject.toml"],
        "ci_retry_config": [],
    }
    web = walk_inventory(web_ts_repo, churn_months=240)["tests"]
    assert web["test_to_source_ratio"] == 0.2
    assert web["coverage_gate"] == ["package.json"]
    assert web["ci_retry_config"] == [".github/workflows/ci.yml"]


def test_docs_block_on_service_py(service_py_repo: Path) -> None:
    docs = walk_inventory(service_py_repo, churn_months=240)["docs"]
    assert docs["readme_present"] is True
    assert docs["readme_loc"] == 10
    assert docs["contributing_present"] is False
    assert docs["adr_dir_present"] is True
    assert docs["changelog_present"] is True
    assert docs["changelog_last_commit"].startswith("2024-10-05")
    assert docs["latest_tag"] == "v0.2.0"
    assert docs["latest_tag_date"].startswith("2026-02-20")
    assert docs["dangling_refs"] == [
        {"file": "README.md", "line": 10, "token": "src/pay/exporter.py"}
    ]
    # README last touched 2024-08-15, newest source (refund.py) 2026-06-22
    assert docs["stale_vs_code_days"]["README.md"] == 676
    assert docs["stale_vs_code_days"]["docs/adr/0001-ledger.md"] == 625


def test_docs_block_on_web_ts_and_mixed(web_ts_repo: Path, mixed_decoys_repo: Path) -> None:
    web = walk_inventory(web_ts_repo, churn_months=240)["docs"]
    assert web["dangling_refs"] == []  # `src/cart` and `src/checkout` resolve as directories
    assert web["adr_dir_present"] is False
    mixed = walk_inventory(mixed_decoys_repo, churn_months=240)["docs"]
    assert mixed["dangling_refs"] == []  # `payments.killswitch` is not path-like
    assert mixed["changelog_present"] is False


def test_docs_block_without_git(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# x\n\nSee `lib/gone.py`.\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    docs = walk_inventory(tmp_path)["docs"]
    assert docs["readme_present"] is True
    assert docs["readme_loc"] == 3
    assert docs["changelog_last_commit"] is None
    assert docs["latest_tag"] is None
    assert docs["latest_tag_date"] is None
    assert docs["dangling_refs"] == [{"file": "README.md", "line": 3, "token": "lib/gone.py"}]
    assert docs["stale_vs_code_days"] == {"README.md": None}


def test_tooling_blocks(tmp_path: Path, web_ts_repo: Path) -> None:
    web = walk_inventory(web_ts_repo, churn_months=240)
    assert web["lint_config"] == [".eslintrc.json", "tslint.json"]
    assert web["boundary_tooling"] == []
    (tmp_path / "pyproject.toml").write_text(
        "[tool.ruff]\nline-length = 100\n\n[tool.importlinter]\nroot_package = 'x'\n",
        encoding="utf-8",
    )
    (tmp_path / ".importlinter").write_text("[importlinter]\n", encoding="utf-8")
    (tmp_path / "x.py").write_text("x = 1\n", encoding="utf-8")
    result = walk_inventory(tmp_path)
    assert result["boundary_tooling"] == [".importlinter", "pyproject.toml"]
    assert result["lint_config"] == ["pyproject.toml"]


def test_top_level_key_order_and_inline_disables(service_py_repo: Path) -> None:
    result = walk_inventory(service_py_repo, churn_months=240)
    assert list(result) == [
        "schema_version", "root", "total_files", "total_loc", "languages", "git_available",
        "churn_window_months", "hotspots", "hotspot_band", "files", "artefacts", "docs",
        "tests", "git", "boundary_tooling", "lint_config", "signal_sources",
    ]
    assert all(e["inline_disables"] == 0 for e in result["files"])


def test_cli_writes_both_files_under_workdir(service_py_repo: Path, tmp_path: Path) -> None:
    from inventory import _main

    workdir = tmp_path / "wd"
    assert _main([str(service_py_repo), "--workdir", str(workdir), "--churn-months", "240"]) == 0
    inv_bytes = (workdir / "inventory.json").read_bytes()
    cpl_bytes = (workdir / "coupling.json").read_bytes()
    assert b"\r\n" not in inv_bytes and b"\r\n" not in cpl_bytes
    inventory = json.loads(inv_bytes)
    coupling = json.loads(cpl_bytes)
    assert inventory["schema_version"] == 2 and coupling["schema_version"] == 2
    assert inventory["churn_window_months"] == 240
    assert len(coupling["pairs"]) == 1


def test_cli_out_flag_keeps_v1_behaviour(service_py_repo: Path, tmp_path: Path) -> None:
    from inventory import _main

    out = tmp_path / "v1" / "inv.json"
    assert _main([str(service_py_repo), "--out", str(out)]) == 0
    assert out.is_file()
    assert not (tmp_path / "v1" / "coupling.json").exists()
    assert json.loads(out.read_bytes())["total_files"] == 16


def test_cli_reads_config_from_root(service_py_repo: Path, tmp_path: Path) -> None:
    import shutil

    from inventory import _main

    repo = tmp_path / "copy"
    shutil.copytree(service_py_repo, repo)
    (repo / ".tech-debt.yaml").write_text("churn_months: 240\n", encoding="utf-8")
    workdir = tmp_path / "wd"
    assert _main([str(repo), "--workdir", str(workdir)]) == 0
    inventory = json.loads((workdir / "inventory.json").read_bytes())
    assert inventory["churn_window_months"] == 240
    assert inventory["total_files"] == 16  # .tech-debt.yaml is neither a file nor an artefact
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest skills/tech-debt-scan/tests/test_inventory_v2.py -k "band or mapping or tests_block or docs_block or tooling or key_order or cli" -v`
Expected: `test_hotspot_score_band_and_blame_on_service_py` FAILS with `AssertionError: assert 0.0 == 100.0` (`hotspot_score` is still its default), `test_hotspot_band_bounds` FAILS with `ImportError: cannot import name '_hotspot_band' from 'inventory'`, `test_tests_block_on_corpus` and `test_docs_block_on_service_py` FAIL with `KeyError: 'tests'` and `KeyError: 'docs'`, `test_cli_writes_both_files_under_workdir` FAILS with `SystemExit: 2` (argparse rejects `--workdir`).

- [ ] **Step 3: Add the helpers to `inventory.py`**

(a) Extend the imports: add `import math`, `from collections import defaultdict`, `from datetime import UTC, datetime` (already present from Task 6; keep one line), `from config import CONFIG_FILENAME, DEFAULTS, ConfigError, load_config`, add `blame_top_share` to the `git_history` import list, and `from reference_graph import GraphFile, build_reference_graph, file_stem`.

(b) Add these constants after `DEEP_INDENT_UNITS`/`RUN_INDENT_UNITS`:

```python
# Blame runs only for hotspot-band files (spec 4.2), at most this many.
HOTSPOT_BLAME_CAP = 50

# Test-file naming conventions (spec 4.2), one union table; {s} is the source
# stem lower-cased, {S} the stem as written.
TEST_NAME_GLOBS: tuple[str, ...] = (
    "test_{s}.*", "{s}_test.*", "{s}.test.*", "{s}.spec.*", "{s}_spec.*",
    "{S}Test.*", "{S}Tests.*",
)

_COVERAGE_GATE_RE = re.compile(r"fail_under|coverageThreshold|check-coverage")
_COVERAGE_GATE_NAMES = ("codecov.yml", ".codecov.yml")
_CI_RETRY_RE = re.compile(r"retry|rerun|retries|max_attempts", re.IGNORECASE)

_README_NAMES = ("readme.md", "readme.rst", "readme.adoc", "readme.txt", "readme")
_CONTRIBUTING_NAMES = ("contributing.md", "contributing.rst", "docs/contributing.md")
_CHANGELOG_NAMES = ("changelog.md", "changes.md", "history.md", "changelog.rst", "changelog")
_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
_PATHLIKE_RE = re.compile(r"(?<![\w./-])[\w.-]+(?:/[\w.-]+)+")
_DOC_REF_EXTS = frozenset(EXT_TO_LANG) | {
    ".yml", ".yaml", ".json", ".toml", ".ini", ".cfg", ".sh", ".ps1", ".sql", ".txt",
}
MAX_DANGLING_REFS = 200

_BOUNDARY_TOOLING_NAMES = (
    ".importlinter", ".dependency-cruiser.js", ".dependency-cruiser.cjs",
    ".dependency-cruiser.mjs", ".dependency-cruiser.json",
)
_LINT_CONFIG_NAMES = (
    ".eslintrc", ".eslintrc.json", ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.yml",
    ".eslintrc.yaml", "eslint.config.js", "eslint.config.mjs", "eslint.config.cjs",
    "tslint.json", "ruff.toml", ".ruff.toml", ".flake8", ".pylintrc", ".golangci.yml",
    ".golangci.yaml", ".rubocop.yml", "stylecop.json",
)
_PYPROJECT_BOUNDARY_KEYS = ("[tool.importlinter]",)
_PYPROJECT_LINT_KEYS = ("[tool.ruff]", "[tool.flake8]", "[tool.pylint]")
```

(c) Add these functions before `build_all`:

```python
def _score_entries(entries: list[FileEntry]) -> None:
    """Fill ``hotspot_score`` with the same formula ``_build_hotspots`` ranks by."""
    max_churn = max((e.churn for e in entries), default=0)
    max_cx = max((e.complexity for e in entries), default=0)
    if max_churn == 0 or max_cx == 0:
        return
    for entry in entries:
        ratio = (entry.churn / max_churn) * (entry.complexity / max_cx)
        entry.hotspot_score = round(ratio * 100, 1)


def _hotspot_band(entries: list[FileEntry], band_cfg: dict[str, Any]) -> list[str]:
    """Top ``fraction`` of source files by hotspot_score, between ``min`` and ``max`` paths."""
    source = [e for e in entries if e.path_class == "source"]
    scored = sorted(
        (e for e in source if e.hotspot_score > 0), key=lambda e: (-e.hotspot_score, e.path)
    )
    size = min(
        max(math.ceil(float(band_cfg["fraction"]) * len(source)), int(band_cfg["min"])),
        int(band_cfg["max"]),
    )
    return [e.path for e in scored[:size]]


def _test_stem_keys(basename: str) -> set[str]:
    """Source stems a test file name can belong to, lower-cased (the seven conventions)."""
    stem = basename.split(".", 1)[0]
    parts = basename.split(".")
    keys: set[str] = set()
    if stem.startswith("test_"):
        keys.add(stem[5:])
    if stem.endswith(("_test", "_spec")):
        keys.add(stem[:-5])
    if stem.endswith("Tests"):
        keys.add(stem[:-5])
    elif stem.endswith("Test"):
        keys.add(stem[:-4])
    if len(parts) > 2 and parts[1] in ("test", "spec"):
        keys.add(parts[0])
    return {k.lower() for k in keys if k}


def _map_tests(entries: list[FileEntry]) -> None:
    """Fill ``mapped_tests`` on source entries from tests-class file names (spec 4.2)."""
    by_key: dict[str, list[str]] = defaultdict(list)
    for entry in entries:
        if entry.path_class != "tests":
            continue
        for key in _test_stem_keys(entry.path.rsplit("/", 1)[-1]):
            by_key[key].append(entry.path)
    for entry in entries:
        if entry.path_class == "source":
            entry.mapped_tests = sorted(by_key.get(file_stem(entry.path), []))


def _read_head(path: Path, limit: int = 65536) -> str:
    try:
        with path.open("rb") as handle:
            return handle.read(limit).decode("utf-8", errors="ignore")
    except OSError:
        return ""


def _tests_block(
    entries: list[FileEntry], artefacts: dict[str, list[dict[str, Any]]], root: Path
) -> dict[str, Any]:
    n_tests = sum(1 for e in entries if e.path_class == "tests")
    n_source = sum(1 for e in entries if e.path_class == "source")
    gate: set[str] = set()
    retry: set[str] = set()
    for cls in ("manifest", "config", "ci"):
        for artefact in artefacts.get(cls, []):
            rel = str(artefact["path"])
            name = rel.rsplit("/", 1)[-1]
            text = _read_head(root / rel)
            if name in _COVERAGE_GATE_NAMES or _COVERAGE_GATE_RE.search(text):
                gate.add(rel)
            if cls == "ci" and _CI_RETRY_RE.search(text):
                retry.add(rel)
    return {
        "test_to_source_ratio": round(n_tests / n_source, 3) if n_source else 0.0,
        "coverage_gate": sorted(gate),
        "ci_retry_config": sorted(retry),
    }


def _days_between(first: str | None, second: str | None) -> int | None:
    if not first or not second:
        return None
    try:
        a = datetime.fromisoformat(first)
        b = datetime.fromisoformat(second)
    except ValueError:
        return None
    return abs((b - a).days)


def _looks_like_ref(token: str, top_level: set[str]) -> bool:
    if "://" in token or token.startswith(("http:", "https:")):
        return False
    lowered = token.lower()
    if lowered.endswith(tuple(_DOC_REF_EXTS)):
        return True
    return "/" in token and token.split("/", 1)[0] in top_level


def _ref_exists(token: str, all_paths: set[str], source_stems: set[str]) -> bool:
    clean = token.removeprefix("./").rstrip("/")
    if clean in all_paths or file_stem(clean) in source_stems:
        return True
    return any(p.endswith("/" + clean) or p.startswith(clean + "/") for p in all_paths)


def _docs_block(
    entries: list[FileEntry],
    artefacts: dict[str, list[dict[str, Any]]],
    texts: dict[str, str],
    git_block: dict[str, Any],
    git_available: bool,
) -> dict[str, Any]:
    root_files = {e.path.lower(): e for e in entries if "/" not in e.path}
    lowered = {e.path.lower(): e for e in entries}
    readme = next((root_files[n] for n in _README_NAMES if n in root_files), None)
    changelog = next((root_files[n] for n in _CHANGELOG_NAMES if n in root_files), None)
    contributing = any(n in lowered for n in _CONTRIBUTING_NAMES)
    all_paths = {e.path for e in entries}
    for items in artefacts.values():
        all_paths.update(str(a["path"]) for a in items)
    adr_present = any("adr" in p.lower().split("/")[:-1] for p in all_paths)
    top_level = {p.split("/", 1)[0] for p in all_paths if "/" in p}
    source_stems = {file_stem(e.path) for e in entries if e.path_class == "source"}
    tags = git_block.get("tags") or []
    latest = tags[-1] if tags else None

    dangling: list[dict[str, Any]] = []
    for entry in entries:
        if entry.path_class != "docs":
            continue
        for lineno, line in enumerate(texts.get(entry.path, "").splitlines(), start=1):
            tokens = set(_BACKTICK_RE.findall(line)) | set(_PATHLIKE_RE.findall(line))
            for raw in sorted(tokens):
                token = raw.strip().strip("`'\"()<>,;:")
                if not token or not _looks_like_ref(token, top_level):
                    continue
                if _ref_exists(token, all_paths, source_stems):
                    continue
                dangling.append({"file": entry.path, "line": lineno, "token": token})
                if len(dangling) >= MAX_DANGLING_REFS:
                    break
            if len(dangling) >= MAX_DANGLING_REFS:
                break
    newest_source = max(
        (e.last_touched for e in entries if e.path_class == "source" and e.last_touched),
        default=None,
    )
    stale: dict[str, int | None] = {}
    for entry in entries:
        if entry.path_class == "docs":
            stale[entry.path] = (
                _days_between(entry.last_touched, newest_source) if git_available else None
            )
    return {
        "readme_present": readme is not None,
        "readme_loc": readme.loc if readme else 0,
        "contributing_present": contributing,
        "adr_dir_present": adr_present,
        "changelog_present": changelog is not None,
        "changelog_last_commit": changelog.last_touched if changelog else None,
        "latest_tag": latest["name"] if latest else None,
        "latest_tag_date": latest["date"] if latest else None,
        "dangling_refs": dangling,
        "stale_vs_code_days": stale,
    }


def _tooling_blocks(root: Path) -> tuple[list[str], list[str]]:
    """(boundary_tooling, lint_config) by root file names and pyproject tables."""
    boundary = [n for n in _BOUNDARY_TOOLING_NAMES if (root / n).is_file()]
    lint = [n for n in _LINT_CONFIG_NAMES if (root / n).is_file()]
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        text = _read_head(pyproject)
        if any(key in text for key in _PYPROJECT_BOUNDARY_KEYS):
            boundary.append("pyproject.toml")
        if any(key in text for key in _PYPROJECT_LINT_KEYS):
            lint.append("pyproject.toml")
    return sorted(boundary), sorted(lint)


def write_json(path: Path, document: dict[str, Any]) -> None:
    """LF-only JSON via write_bytes so Windows text mode never inserts CRLF."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(document, indent=2) + "\n").encode("utf-8"))


def write_outputs(
    inventory: dict[str, Any], coupling: dict[str, Any], workdir: Path
) -> tuple[Path, Path]:
    """Write ``inventory.json`` and ``coupling.json`` under ``workdir``."""
    inventory_path = workdir / "inventory.json"
    coupling_path = workdir / "coupling.json"
    write_json(inventory_path, inventory)
    write_json(coupling_path, coupling)
    return inventory_path, coupling_path
```

(d) Replace `build_all` in full with its final form:

```python
def build_all(
    root: Path,
    *,
    ignore: tuple[str, ...] = DEFAULT_IGNORE,
    churn_months: int | None = None,
    config: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Walk ``root`` once and mine git once; return (inventory, coupling) documents."""
    root = root.resolve()
    if not root.exists():
        raise InventoryError(f"path not found: {root}")
    if not root.is_dir():
        raise InventoryError(f"path is not a directory: {root}")
    cfg = config if config is not None else copy.deepcopy(DEFAULTS)
    window = int(cfg["churn_months"]) if churn_months is None else churn_months
    names, globs = _ignore_sets(ignore, cfg)
    extra_classes: dict[str, list[str]] = cfg.get("path_classes") or {}
    bots = [str(b) for b in cfg["bot_authors"]]
    coupling_cfg = cfg["coupling"]
    bulk_threshold = int(coupling_cfg["bulk_threshold"])

    entries: list[FileEntry] = []
    texts: dict[str, str] = {}
    languages: set[str] = set()
    artefact_candidates: list[tuple[Path, str]] = []

    for path, rel_str in _iter_files(root, names, globs):
        ext = path.suffix.lower()
        lang = EXT_TO_LANG.get(ext)
        if lang is None:
            artefact_candidates.append((path, rel_str))
            continue
        try:
            text = path.read_bytes().decode("utf-8", errors="ignore")
        except OSError as exc:
            raise InventoryError(f"could not read {path}: {exc}") from exc
        texts[rel_str] = text
        loc, indent_total, max_indent, deep, longest = _line_metrics(
            text.splitlines(keepends=True)
        )
        entries.append(
            FileEntry(
                path=rel_str,
                ext=ext,
                loc=loc,
                mtime=path.stat().st_mtime,
                complexity=indent_total,
                max_indent=max_indent,
                churn=0,
                language=lang,
                path_class=_classify_path(rel_str, extra_classes),
                deep_indent_lines=deep,
                longest_indented_run=longest,
            )
        )
        languages.add(lang)
    by_path = {e.path: e for e in entries}

    commits = git_log_pass(root, window)
    git_available = commits is not None
    present = set(by_path) | {rel for _, rel in artefact_candidates}
    histories, bulk_excluded = derive_file_history(
        commits or [],
        present,
        is_test=lambda rel: _classify_path(rel, extra_classes) == "tests",
        bot_authors=bots,
        bulk_threshold=bulk_threshold,
    )
    if git_available:
        for entry in entries:
            _apply_history(entry, histories[entry.path])
    artefacts = _walk_artefacts(root, artefact_candidates, histories if git_available else {})

    present_source = {e.path for e in entries if e.path_class == "source"}
    pairs, degree = change_coupling(
        commits or [],
        present_source,
        min_shared=int(coupling_cfg["min_shared"]),
        min_ratio=float(coupling_cfg["min_ratio"]),
        bulk_threshold=bulk_threshold,
    )
    for entry in entries:
        entry.coupling_degree = degree.get(entry.path, 0)

    graph = build_reference_graph(
        [
            GraphFile(
                path=e.path, language=e.language, path_class=e.path_class,
                text=texts[e.path], loc=e.loc, churn=e.churn,
            )
            for e in entries
            if e.path_class in ("source", "tests")
        ],
        cfg["fan_in"],
    )
    for entry in entries:
        if entry.path_class == "source":
            entry.fan_in_approx = graph.fan_in.get(entry.path)
            entry.fan_out_approx = graph.fan_out.get(entry.path)
            entry.fan_in_mode = graph.mode.get(entry.path, "import-lines")

    _score_entries(entries)
    band = _hotspot_band(entries, cfg["hotspot_band"])
    if git_available:
        for rel in band[:HOTSPOT_BLAME_CAP]:
            share, _email = blame_top_share(root, rel, bots)
            by_path[rel].top_author_line_share = share
    _map_tests(entries)

    git_block = _git_block(root, commits, bulk_excluded, cfg)
    signal_sources: dict[str, str] = {}
    if git_available:
        signal_sources["git"] = datetime.now(UTC).isoformat(timespec="seconds")
    boundary, lint = _tooling_blocks(root)

    inventory: dict[str, Any] = {
        "schema_version": 2,
        "root": str(root),
        "total_files": len(entries),
        "total_loc": sum(e.loc for e in entries),
        "languages": sorted(languages),
        "git_available": git_available,
        "churn_window_months": window,
        "hotspots": _build_hotspots(entries),
        "hotspot_band": band,
        "files": [asdict(e) for e in entries],
        "artefacts": artefacts,
        "docs": _docs_block(entries, artefacts, texts, git_block, git_available),
        "tests": _tests_block(entries, artefacts, root),
        "git": git_block,
        "boundary_tooling": boundary,
        "lint_config": lint,
        "signal_sources": signal_sources,
    }
    coupling: dict[str, Any] = {
        "schema_version": 2,
        "min_shared": int(coupling_cfg["min_shared"]),
        "min_ratio": float(coupling_cfg["min_ratio"]),
        "bulk_threshold": bulk_threshold,
        "fan_in_mode": str(cfg["fan_in"]["mode"]),
        "pairs": pairs,
        "degree": degree,
        "cycles": graph.cycles,
        "directories": graph.directories,
        "unstable_edges": graph.unstable_edges,
    }
    return inventory, coupling
```

(e) Replace `_main` with:

```python
def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a file inventory for tech-debt-scan")
    parser.add_argument("path", help="repo root to scan")
    parser.add_argument(
        "--workdir",
        default=".tech-debt",
        help="directory that receives inventory.json and coupling.json (default .tech-debt)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="v1 compatibility: write only inventory.json to this path",
    )
    parser.add_argument(
        "--churn-months",
        type=int,
        default=None,
        help="git-history window in months; overrides churn_months in .tech-debt.yaml",
    )
    args = parser.parse_args(argv)

    root = Path(args.path)
    try:
        cfg = load_config(root)
        inventory, coupling = build_all(root, churn_months=args.churn_months, config=cfg)
    except (InventoryError, ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.out:
        out_path = Path(args.out)
        write_json(out_path, inventory)
        written = f"wrote {out_path}"
    else:
        inventory_path, coupling_path = write_outputs(inventory, coupling, Path(args.workdir))
        written = f"wrote {inventory_path} and {coupling_path}"
    hot = len(cast("list[dict[str, Any]]", inventory["hotspots"]))
    band = len(cast("list[str]", inventory["hotspot_band"]))
    pairs = len(cast("list[dict[str, Any]]", coupling["pairs"]))
    git_note = "git churn on" if inventory["git_available"] else "no git history"
    print(
        f"{written} ({inventory['total_files']} files, {inventory['total_loc']} LOC, "
        f"{hot} hotspots, {band} in band, {pairs} coupled pairs, {git_note})"
    )
    return 0
```

(f) Replace the module docstring's opening paragraph with:

```
"""Build a language-agnostic file inventory and coupling document (spec 4.2).

``python scripts/inventory.py <repo> --workdir .tech-debt`` writes
``inventory.json`` and ``coupling.json``; ``--out <path>`` keeps the v1
behaviour of writing only ``inventory.json`` to that path. ``.tech-debt.yaml``
at the repository root (``config.py``) supplies every threshold.
```

keeping the LOC and hotspot paragraphs, and append:

```
``hotspots`` keeps its v1 shape and key set; every ``files[]`` entry carries
``hotspot_score`` and the top-level ``hotspot_band`` lists the top fraction
of source-class files (``hotspot_band`` in config: 0.10, at least 5, at most
50). Blame runs only for band files (cap 50) to give ``top_author_line_share``.
``mapped_tests`` comes from one union table of test-name conventions; the
``tests`` block reports the test-to-source ratio, coverage gates and CI retry
configuration; the ``docs`` block reports README, CONTRIBUTING, ADR and
CHANGELOG presence, the latest tag, dangling references in docs and doc
staleness versus code. ``inline_disables`` is emitted as 0 and filled in
place by ``patterns.py``.
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest skills/tech-debt-scan/tests/test_inventory_v2.py skills/tech-debt-scan/tests/test_inventory.py skills/tech-debt-scan/tests/test_e2e.py skills/tech-debt-scan/tests/test_skill_check.py -v`
Expected: all pass. `test_real_skill_md_passes` still passes because `--out` and `--churn-months` remain in `--help`.

- [ ] **Step 5: Lint, type-check and the skill lint**

Run: `ruff check . && mypy && python skills/tech-debt-scan/scripts/skill_check.py`
Expected: `All checks passed!`, `Success: no issues found`, `ok: all SKILL.md commands match their scripts (...)`.

- [ ] **Step 6: Commit**

```bash
git add skills/tech-debt-scan/scripts/inventory.py skills/tech-debt-scan/tests/test_inventory_v2.py
git commit -m "feat(tech-debt-scan): hotspot band, blame share, test mapping, docs and tests blocks, --workdir"
```

---

### Task 10: `patterns.py` (regex leads, SATD table, inline-disable write-back)

**Files:**
- Create: `skills/tech-debt-scan/scripts/patterns.py`
- Create: `skills/tech-debt-scan/tests/test_patterns.py`

**Interfaces:**
- Consumes: `LANG_COMMENT`, `DEFAULT_COMMENT`, `build_all`, `write_json` (Tasks 5 and 9); `run_git` (Task 6); `import_lines` (Task 8); `DEFAULTS`, `load_config`, `ConfigError` (Task 1); the corpus fixtures (Task 4).
- Produces (used by Task 11's leads block, Task 13's docs, and phase 2):
  - `SCHEMA_VERSION = 2`, `BLAME_FILE_CAP = 200`, `LEAD_PROMPT_CAP = 40`, `FAMILIES: tuple[str, ...]`
  - `SATD_MARKERS: tuple[str, ...]` (62 entries) and `SATD_RE`
  - `@dataclass(frozen=True) class Rule(family, rule, regex, scope: frozenset[str], blame: bool = False, kind: str = "line", exclude: re.Pattern[str] | None = None)` and the table `RULES: tuple[Rule, ...]`
  - `@dataclass(slots=True) class Lead(rule, file, line, quote, path_class, extra)` with `as_dict()`
  - `def comment_text(line: str, markers: Markers) -> str | None`, `def is_comment_line(line: str, markers: Markers) -> bool`, `def strip_markers(line: str, markers: Markers) -> str`
  - `def run_patterns(root: Path, inventory: dict[str, Any], config: dict[str, Any], *, blame: bool = True) -> tuple[dict[str, Any], dict[str, int]]` returning the `patterns.json` document and the per-file inline-disable counts
  - `def redact(text: str) -> str` (credential values cut to four characters; added in sub-deliverable C)
  - `def capped_leads(leads: Sequence[dict[str, Any]], band: Sequence[str], limit: int = LEAD_PROMPT_CAP) -> list[dict[str, Any]]` (hotspot-band files first; phase 2's prompt cap)
  - CLI `python scripts/patterns.py <repo> --workdir .tech-debt [--no-blame]` writing `patterns.json` and rewriting `inventory.json` with `files[].inline_disables`

**Spec:** 4.3 in full (rule table by group, union-of-idioms regexes, comment markers from the extension map, blame for the `satd` group on at most 200 files and `--no-blame`, the amended error-masking rule with the caught-variable capture and the exception-carrier exclusion, `extra.annotated`, catches-everything variants, the assertion-disabling signal rule, commented-out-code heuristic, legacy names, deprecation union with approximate caller count, flag SDK union, the security rules with placeholder and tests-class exclusions and four-character redaction, test-quality signals, the no-timeout union, stdout-versus-logger, inline disables written into `inventory.files[].inline_disables`, `patterns.json` shape, 40-per-family prompt cap with the file keeping everything, stats); 0(d) and 3.3 (no language branch, two languages per rule); 9 (the only cross-script in-place edit).

**Decisions the spec leaves open, fixed here:** a "comment line" is a line whose stripped text starts with one of the file's line markers, a block-open marker, or `*` inside a `/* */` block; SATD markers are searched in comment text only (the 62-entry list below stands in for the Potdar and Shihab list the research cites but does not reproduce); defect markers (`known bug`, `known issue`, `kludge`, `workaround`) are members of that list rather than a separate rule; the catch rule scans source files only (a try or catch inside a test body is the test-quality rule's job); a catch body is classified `empty`, `pass`, `return` (the spec's `return`, `return None`, `return null`, plus Go's `return nil`) or `log-only`; the logger-present test for the observability rule is a union of logger names over every source file's import lines (`log`, `logging`, `structlog`, `loguru`, `winston`, `pino`, `bunyan`, `log4js`, `loglevel`, `serilog`, `nlog`, `log4net`, `logrus`, `zap`, `zerolog`, `slog`, `log4j`, `slf4j`, `logback`, `tracing`) and "CLI" means a path with a `cli`, `cmd`, `bin`, `scripts` or `tools` segment or an entry-point marker (`if __name__ == "__main__"`, `func main()`, `static void Main`, `fn main()`, `process.argv`); files over 2 MB or with a NUL byte in the first KB are skipped; `commits_since` is `git rev-list --count <blame-sha>..HEAD -- <path>`. Rules without a corpus positive in two languages (assertion switches, CORS in a second language, the rarer test-quality signals, commented-out code in a brace language) get two-language synthetic positives in the test file; spec 3.3 names the corpus languages, not the corpus files, so a synthetic Go or TypeScript positive satisfies it.

**Confidence:** 91% after Step 0 (was 86%: regex rules across three languages). Mitigations inside the task: Step 0 grounds every expected hit in the tests on an actual regex run over the replayed corpus before any RED step, so the test expectations and the regexes cannot disagree by construction; three sub-deliverables that each end green; per-rule positive and decoy tests in two languages; corpus line numbers fixed by Task 4's tree test. Residual: every rule is a lead, never a finding, so a false positive on real code costs a scout question rather than a report line, and cross-language precision is measured only at the phase 5 live run.

- [ ] **Step 0: Spike the rule table against the replayed corpus (throwaway, not committed)**

Before writing any test, copy every regex from sub-deliverables A, B and C into a scratch script under the session scratchpad (not the repository), replay the three fixtures with `replay_fixture` (Task 3) into a temporary directory, and print every match as `rule<TAB>file<TAB>line<TAB>quote` for each fixture:

```python
"""Throwaway: run the Task 10 regexes over the replayed corpus and print hits."""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "skills/tech-debt-scan/tests/helpers")
sys.path.insert(0, "skills/tech-debt-scan/scripts")
from make_history import replay_fixture  # noqa: E402

RULE_REGEXES: dict[str, str] = {
    # paste each (rule name, regex source) pair from Steps A, B and C here verbatim
}

for fixture in ("service-py", "web-ts", "mixed-decoys"):
    with tempfile.TemporaryDirectory() as tmp:
        root = replay_fixture(fixture, Path(tmp))
        for path in sorted(p for p in root.rglob("*") if p.is_file() and ".git" not in p.parts):
            text = path.read_text(encoding="utf-8", errors="replace")
            for name, source in RULE_REGEXES.items():
                for n, line in enumerate(text.splitlines(), start=1):
                    if re.search(source, line):
                        rel = path.relative_to(root).as_posix()
                        print(f"{fixture}\t{name}\t{rel}\t{n}\t{line.strip()[:80]}")
```

Run: `python <scratchpad>/spike_patterns.py` from the repository root.

Compare the printed hits with the expected hits written in Steps A1, B1 and C1. Where a line number or a hit set differs, correct the TEST EXPECTATION to the printed value (the fixture tree is fixed by Task 4 and must not change), and where a regex misses a planted positive or hits a decoy, correct the REGEX in the implementation step and re-run until the printed hits equal the planted positives for every rule and no decoy appears. Only then proceed to Step A1. Delete the scratch script; nothing from this step is committed.

#### Sub-deliverable A: scanner core, SATD table with blame, `--no-blame`

- [ ] **Step A1: Write the failing tests**

Create `skills/tech-debt-scan/tests/test_patterns.py`:

```python
"""patterns.py: regex leads, SATD table, redaction, inline disables (spec 4.3)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from config import DEFAULTS
from inventory import build_all
from patterns import RULES, Lead, capped_leads, run_patterns

SCRIPTS = Path(__file__).parent.parent / "scripts"


@pytest.fixture(scope="module")
def service_py(service_py_repo: Path) -> tuple[Path, dict[str, Any]]:
    inventory, _ = build_all(service_py_repo, churn_months=240)
    return service_py_repo, inventory


@pytest.fixture(scope="module")
def web_ts(web_ts_repo: Path) -> tuple[Path, dict[str, Any]]:
    inventory, _ = build_all(web_ts_repo, churn_months=240)
    return web_ts_repo, inventory


@pytest.fixture(scope="module")
def mixed(mixed_decoys_repo: Path) -> tuple[Path, dict[str, Any]]:
    inventory, _ = build_all(mixed_decoys_repo, churn_months=240)
    return mixed_decoys_repo, inventory


def _run(repo: tuple[Path, dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    doc, _inline = run_patterns(repo[0], repo[1], DEFAULTS, **kwargs)
    return doc


def _leads(doc: dict[str, Any], family: str, rule: str) -> dict[tuple[str, int], dict[str, Any]]:
    return {
        (item["file"], item["line"]): item
        for item in doc["leads"][family]
        if item["rule"] == rule
    }


def _synthetic(tmp_path: Path, files: dict[str, str]) -> tuple[Path, dict[str, Any]]:
    for rel, content in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    inventory, _ = build_all(tmp_path)
    return tmp_path, inventory


# --- A: core, SATD, blame -------------------------------------------------------


def test_rule_table_is_data_with_family_scope_and_blame() -> None:
    for rule in RULES:
        assert isinstance(rule.regex, re.Pattern)
        assert rule.scope and isinstance(rule.scope, frozenset)
        assert rule.family in {
            "half-finished", "error-masking", "dead-code", "security", "test-quality",
            "pipeline-infra", "lint",
        }
    satd = next(r for r in RULES if r.rule == "satd-marker")
    assert satd.blame is True
    assert {"source", "tests", "docs", "ci", "config", "build"} <= satd.scope
    assert all(not r.blame for r in RULES if r.rule != "satd-marker")


def test_satd_markers_with_age_ticket_and_commits_since(
    service_py: tuple[Path, dict[str, Any]],
) -> None:
    doc = _run(service_py)
    satd = {(s["file"], s["line"]): s for s in doc["satd"]}
    fixme = satd[("src/pay/refund.py", 35)]
    assert fixme["marker"] == "fixme"
    assert fixme["quote"].startswith("# FIXME: the gateway retries")
    assert fixme["ticket_ref"] is False
    assert fixme["age_days"] >= 700  # blamed to c1 on 2024-08-15
    assert fixme["commits_since"] == 6  # c6, c7, c9, c11, c14, c16
    assert fixme["path_class"] == "source"
    todo = satd[("src/pay/legacy_export.py", 7)]
    assert todo["marker"] == "todo"
    assert todo["ticket_ref"] is True  # "#42"
    assert todo["commits_since"] == 0
    assert set(fixme) == {
        "marker", "file", "line", "quote", "ticket_ref", "age_days", "commits_since", "path_class",
    }
    stats = doc["stats"]
    assert stats["markers_by_age_band"][">365d"] >= 2
    assert list(stats["markers_by_age_band"]) == [
        "<30d", "30-180d", "180-365d", ">365d", "unknown",
    ]
    assert 0.0 < stats["markers_without_ticket_share"] < 1.0
    assert set(stats["leads_per_family"]) == set(doc["leads"])


def test_satd_marker_in_a_second_language(mixed: tuple[Path, dict[str, Any]]) -> None:
    doc = _run(mixed)
    satd = {(s["file"], s["line"]): s for s in doc["satd"]}
    assert satd[("internal/httpc/httpc.go", 11)]["marker"] == "deprecated"
    assert satd[("internal/httpc/httpc.go", 11)]["age_days"] is not None


def test_satd_markers_only_in_comments(tmp_path: Path) -> None:
    repo = _synthetic(
        tmp_path,
        {
            "app.py": 'label = "TODO list"\n# TODO: real marker\n',
            "web.ts": 'const x = "hack";\n/* HACK: block marker */\n',
        },
    )
    doc = _run(repo, blame=False)
    assert [(s["file"], s["line"], s["marker"]) for s in doc["satd"]] == [
        ("app.py", 2, "todo"),
        ("web.ts", 2, "hack"),
    ]


def test_no_blame_leaves_age_and_commits_null(service_py: tuple[Path, dict[str, Any]]) -> None:
    doc = _run(service_py, blame=False)
    assert doc["satd"]
    assert all(s["age_days"] is None and s["commits_since"] is None for s in doc["satd"])
    assert doc["stats"]["markers_by_age_band"]["unknown"] == len(doc["satd"])


def test_patterns_document_shape(service_py: tuple[Path, dict[str, Any]]) -> None:
    doc = _run(service_py, blame=False)
    assert list(doc) == ["schema_version", "leads", "satd", "stats"]
    assert doc["schema_version"] == 2
    assert list(doc["leads"]) == [
        "half-finished", "error-masking", "dead-code", "security", "test-quality",
        "pipeline-infra",
    ]
    for item in (lead for leads in doc["leads"].values() for lead in leads):
        assert list(item) == ["rule", "file", "line", "quote", "path_class", "extra"]


def test_capped_leads_hotspot_band_first() -> None:
    leads = [Lead("r", f"f{i}.py", 1, "q", "source").as_dict() for i in range(60)]
    band = [f"f{i}.py" for i in range(50, 60)]
    capped = capped_leads(leads, band)
    assert len(capped) == 40
    assert [item["file"] for item in capped[:10]] == band
    assert [item["file"] for item in capped[10:]] == [f"f{i}.py" for i in range(30)]
    assert capped_leads(leads, band, limit=5) == capped[:5]
```

- [ ] **Step A2: Run the tests to verify they fail**

Run: `pytest skills/tech-debt-scan/tests/test_patterns.py -v`
Expected: collection error `ModuleNotFoundError: No module named 'patterns'`.

- [ ] **Step A3: Write `patterns.py` (core and SATD)**

Create `skills/tech-debt-scan/scripts/patterns.py`:

```python
"""Regex lead miner and SATD table for the scout families (spec 4.3).

One rule table keyed by family. Each ``Rule`` row has ``family``, ``rule``,
a compiled regex, a path-class scope and a blame flag; ``kind`` names the
scanner that applies it (a plain line match, or one of the multi-line
scanners for catch bodies, commented-out runs, call arguments, per-file
counts and assertion-free tests). Every regex is a union of idioms across
languages; the only language-aware input is ``LANG_COMMENT`` from the
inventory's extension map, which says which comment markers to strip. No
function here branches on a language name (spec 0(d)); a grep test enforces
it.

Leads feed scouts and corroborate the merge; counts go to report statistics,
never to a finding. Blame runs only for the SATD markers, on at most
``BLAME_FILE_CAP`` files; ``--no-blame`` skips it and leaves ``age_days`` and
``commits_since`` null. Credential values are redacted to their first four
characters before anything is written. ``inline_disables`` per source file
is written back into ``inventory.json`` in place, the only cross-script
in-place edit in the pipeline (spec 9).

``python scripts/patterns.py <repo> --workdir .tech-debt [--no-blame]``
reads ``<workdir>/inventory.json`` and writes ``<workdir>/patterns.json``.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from config import ConfigError, load_config
from git_history import run_git
from inventory import DEFAULT_COMMENT, LANG_COMMENT, write_json
from reference_graph import import_lines

SCHEMA_VERSION: Final[int] = 2
BLAME_FILE_CAP: Final[int] = 200
LEAD_PROMPT_CAP: Final[int] = 40
MAX_SCAN_BYTES: Final[int] = 2_000_000

Markers = tuple[tuple[str, ...], tuple[tuple[str, str], ...]]

FAMILIES: Final[tuple[str, ...]] = (
    "half-finished", "error-masking", "dead-code", "security", "test-quality", "pipeline-infra",
)

SOURCE: Final[frozenset[str]] = frozenset({"source"})
SOURCE_TESTS: Final[frozenset[str]] = frozenset({"source", "tests"})
SOURCE_CI_CONFIG: Final[frozenset[str]] = frozenset({"source", "ci", "config"})
TESTS: Final[frozenset[str]] = frozenset({"tests"})
ARTEFACT_SCAN_CLASSES: Final[tuple[str, ...]] = (
    "ci", "config", "build", "manifest", "container", "iac", "sql", "runtime_version",
    "governance",
)
ALL_TEXT: Final[frozenset[str]] = frozenset({"source", "tests", "docs", *ARTEFACT_SCAN_CLASSES})

# Self-admitted debt markers: the 62-entry union used for the satd group,
# matched case-insensitively inside comment text only.
SATD_MARKERS: Final[tuple[str, ...]] = (
    "todo", "fixme", "xxx", "hack", "hacky", "kludge", "kluge", "workaround", "work around",
    "temporary", "temp fix", "quick fix", "quick and dirty", "band-aid", "bandaid", "stopgap",
    "stop-gap", "not implemented", "unimplemented", "needs work", "needs refactor",
    "refactor this", "refactor me", "clean up later", "cleanup later", "remove this", "remove me",
    "get rid of", "rewrite this", "should be rewritten", "should be refactored", "should be fixed",
    "must be fixed", "to be fixed", "fix later", "fix me later", "revisit", "for now", "someday",
    "eventually", "ugly", "nasty", "broken", "known bug", "known issue", "known problem",
    "this is wrong", "this is bad", "this isn't right", "doesn't work", "does not work",
    "won't work", "not sure why", "no idea why", "not tested", "untested", "unsafe", "dangerous",
    "deprecated", "obsolete", "legacy", "smell",
)
SATD_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:" + "|".join(re.escape(m).replace(r"\ ", r"\s+") for m in SATD_MARKERS) + r")\b",
    re.IGNORECASE,
)
TICKET_RE: Final[re.Pattern[str]] = re.compile(
    r"#\d+|\b[A-Z][A-Z0-9]+-\d+\b|https?://\S+/issues/\d+"
)
AGE_BANDS: Final[tuple[str, ...]] = ("<30d", "30-180d", "180-365d", ">365d", "unknown")


@dataclass(frozen=True)
class Rule:
    family: str
    rule: str
    regex: re.Pattern[str]
    scope: frozenset[str]
    blame: bool = False
    kind: str = "line"
    exclude: re.Pattern[str] | None = None


@dataclass(slots=True)
class Lead:
    rule: str
    file: str
    line: int
    quote: str
    path_class: str
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "file": self.file,
            "line": self.line,
            "quote": self.quote,
            "path_class": self.path_class,
            "extra": self.extra,
        }


@dataclass(slots=True)
class ScanFile:
    path: str
    path_class: str
    language: str
    text: str
    lines: list[str]
    markers: Markers


@dataclass(slots=True)
class ScanContext:
    fan_in: dict[str, int | None]
    logger_present: bool


Handler = Callable[[ScanFile, Rule, ScanContext], list[Lead]]


# --- comment handling -----------------------------------------------------------


def comment_text(line: str, markers: Markers) -> str | None:
    """The comment part of ``line`` (text after the first comment marker), or None."""
    stripped = line.strip()
    positions: list[tuple[int, int]] = []  # (index of marker, marker length)
    for marker in markers[0]:
        idx = line.find(marker)
        if idx != -1:
            positions.append((idx, len(marker)))
    for open_marker, close_marker in markers[1]:
        idx = line.find(open_marker)
        if idx != -1:
            positions.append((idx, len(open_marker)))
        elif open_marker == "/*" and stripped.startswith("*"):
            positions.append((line.find("*"), 1))  # a line inside a block comment
        elif stripped.endswith(close_marker):
            positions.append((0, 0))  # the closing line of a block comment
    if not positions:
        return None
    idx, length = min(positions)
    text = line[idx + length :]
    for _open_marker, close_marker in markers[1]:
        text = text.replace(close_marker, "")
    return text.strip()


def is_comment_line(line: str, markers: Markers) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if any(stripped.startswith(m) for m in markers[0]):
        return True
    for open_marker, close_marker in markers[1]:
        if stripped.startswith(open_marker) or stripped.endswith(close_marker):
            return True
        if open_marker == "/*" and stripped.startswith("*"):
            return True
    return False


def strip_markers(line: str, markers: Markers) -> str:
    stripped = line.strip()
    for marker in markers[0]:
        if stripped.startswith(marker):
            return stripped[len(marker) :].strip()
    for open_marker, close_marker in markers[1]:
        if stripped.startswith(open_marker):
            stripped = stripped[len(open_marker) :]
        if stripped.endswith(close_marker):
            stripped = stripped[: -len(close_marker)]
        if open_marker == "/*" and stripped.lstrip().startswith("*"):
            stripped = stripped.lstrip().lstrip("*")
    return stripped.strip()


# --- scanners -------------------------------------------------------------------


def _scan_lines(sf: ScanFile, rule: Rule, _ctx: ScanContext) -> list[Lead]:
    leads: list[Lead] = []
    for lineno, line in enumerate(sf.lines, start=1):
        if rule.regex.search(line) and not (rule.exclude and rule.exclude.search(line)):
            leads.append(Lead(rule.rule, sf.path, lineno, line.strip(), sf.path_class))
    return leads


def _scan_satd(sf: ScanFile, rule: Rule, _ctx: ScanContext) -> list[Lead]:
    leads: list[Lead] = []
    for lineno, line in enumerate(sf.lines, start=1):
        comment = comment_text(line, sf.markers)
        if comment is None:
            continue
        match = rule.regex.search(comment)
        if match is None:
            continue
        marker = re.sub(r"\s+", " ", match.group(0).lower())
        leads.append(
            Lead(
                rule.rule, sf.path, lineno, line.strip(), sf.path_class,
                {"marker": marker, "ticket_ref": TICKET_RE.search(comment) is not None},
            )
        )
    return leads


# --- blame ----------------------------------------------------------------------


def _blame_lines(root: Path, rel: str) -> dict[int, tuple[int, str]] | None:
    """Map final line number -> (author epoch seconds, commit sha) via blame -w."""
    stdout = run_git(
        root, ["-c", "core.quotePath=false", "blame", "-w", "--line-porcelain", "--", rel]
    )
    if stdout is None:
        return None
    out: dict[int, tuple[int, str]] = {}
    sha = ""
    line_no = 0
    for raw in stdout.splitlines():
        if re.match(r"^[0-9a-f]{40} \d+ \d+", raw):
            parts = raw.split()
            sha, line_no = parts[0], int(parts[2])
        elif raw.startswith("author-time "):
            out[line_no] = (int(raw[12:].strip()), sha)
    return out


def _commits_since(
    root: Path, sha: str, rel: str, cache: dict[tuple[str, str], int | None]
) -> int | None:
    key = (sha, rel)
    if key not in cache:
        stdout = run_git(root, ["rev-list", "--count", f"{sha}..HEAD", "--", rel])
        cache[key] = int(stdout.strip()) if stdout and stdout.strip().isdigit() else None
    return cache[key]


def _attach_blame(root: Path, satd: list[dict[str, Any]]) -> None:
    files: list[str] = []
    for entry in satd:
        if entry["file"] not in files:
            files.append(str(entry["file"]))
    now = datetime.now(UTC)
    cache: dict[tuple[str, str], int | None] = {}
    for rel in files[:BLAME_FILE_CAP]:
        blamed = _blame_lines(root, rel)
        if blamed is None:
            continue
        for entry in satd:
            if entry["file"] != rel:
                continue
            hit = blamed.get(int(entry["line"]))
            if hit is None:
                continue
            epoch, sha = hit
            entry["age_days"] = (now - datetime.fromtimestamp(epoch, UTC)).days
            entry["commits_since"] = _commits_since(root, sha, rel, cache)


def _age_band(age: int | None) -> str:
    if age is None:
        return "unknown"
    if age < 30:
        return "<30d"
    if age < 180:
        return "30-180d"
    if age < 365:
        return "180-365d"
    return ">365d"


# --- rule table -----------------------------------------------------------------

RULES: Final[tuple[Rule, ...]] = (
    Rule("half-finished", "satd-marker", SATD_RE, ALL_TEXT, blame=True, kind="satd"),
)

_HANDLERS: Final[dict[str, Handler]] = {
    "line": _scan_lines,
    "satd": _scan_satd,
}


# --- driver ---------------------------------------------------------------------


def _read_text(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_SCAN_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:1024]:
        return None
    return data.decode("utf-8", errors="replace")


def _scan_files(root: Path, inventory: dict[str, Any]) -> list[ScanFile]:
    files: list[ScanFile] = []
    for entry in inventory["files"]:
        path_class = str(entry["path_class"])
        if path_class in ("generated", "vendored"):
            continue
        text = _read_text(root / str(entry["path"]))
        if text is None:
            continue
        language = str(entry.get("language") or "")
        markers = LANG_COMMENT.get(language, DEFAULT_COMMENT)
        files.append(
            ScanFile(str(entry["path"]), path_class, language, text, text.splitlines(), markers)
        )
    artefacts = inventory.get("artefacts") or {}
    for cls in ARTEFACT_SCAN_CLASSES:
        for artefact in artefacts.get(cls, []):
            text = _read_text(root / str(artefact["path"]))
            if text is None:
                continue
            files.append(
                ScanFile(str(artefact["path"]), cls, "", text, text.splitlines(), DEFAULT_COMMENT)
            )
    return files


LOGGER_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:log|logging|structlog|loguru|winston|pino|bunyan|log4js|loglevel|serilog|nlog|"
    r"log4net|logrus|zap|zerolog|slog|log4j|slf4j|logback|tracing)\b"
)


def _logger_present(files: Sequence[ScanFile]) -> bool:
    for sf in files:
        if sf.path_class == "source" and any(
            LOGGER_RE.search(line) for line in import_lines(sf.text)
        ):
            return True
    return False


def _satd_entry(lead: Lead) -> dict[str, Any]:
    return {
        "marker": lead.extra["marker"],
        "file": lead.file,
        "line": lead.line,
        "quote": lead.quote,
        "ticket_ref": lead.extra["ticket_ref"],
        "age_days": None,
        "commits_since": None,
        "path_class": lead.path_class,
    }


def _stats(satd: list[dict[str, Any]], leads: dict[str, list[Lead]]) -> dict[str, Any]:
    bands: Counter[str] = Counter(_age_band(s["age_days"]) for s in satd)
    without = sum(1 for s in satd if not s["ticket_ref"])
    return {
        "markers_by_age_band": {band: bands[band] for band in AGE_BANDS},
        "markers_without_ticket_share": round(without / len(satd), 3) if satd else 0.0,
        "leads_per_family": {family: len(items) for family, items in leads.items()},
    }


def run_patterns(
    root: Path, inventory: dict[str, Any], config: dict[str, Any], *, blame: bool = True
) -> tuple[dict[str, Any], dict[str, int]]:
    """Return (patterns document, inline-disable counts per source path)."""
    root = root.resolve()
    files = _scan_files(root, inventory)
    ctx = ScanContext(
        fan_in={str(e["path"]): e.get("fan_in_approx") for e in inventory["files"]},
        logger_present=_logger_present(files),
    )
    leads: dict[str, list[Lead]] = {family: [] for family in FAMILIES}
    satd: list[dict[str, Any]] = []
    inline: dict[str, int] = {}
    for sf in files:
        for rule in RULES:
            if sf.path_class not in rule.scope:
                continue
            found = _HANDLERS[rule.kind](sf, rule, ctx)
            if rule.kind == "satd":
                satd.extend(_satd_entry(lead) for lead in found)
            else:
                leads[rule.family].extend(found)
        if sf.path_class == "source":
            inline[sf.path] = 0
    if blame:
        _attach_blame(root, satd)
    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "leads": {family: [lead.as_dict() for lead in items] for family, items in leads.items()},
        "satd": satd,
        "stats": _stats(satd, leads),
    }
    return document, inline


def capped_leads(
    leads: Sequence[dict[str, Any]], band: Sequence[str], limit: int = LEAD_PROMPT_CAP
) -> list[dict[str, Any]]:
    """The first ``limit`` leads with hotspot-band files first (spec 4.3 prompt cap)."""
    in_band = set(band)
    first = [lead for lead in leads if lead["file"] in in_band]
    rest = [lead for lead in leads if lead["file"] not in in_band]
    return [*first, *rest][:limit]


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mine regex leads and SATD markers")
    parser.add_argument("path", help="repo root to scan")
    parser.add_argument(
        "--workdir",
        default=".tech-debt",
        help="directory holding inventory.json (default .tech-debt)",
    )
    parser.add_argument("--no-blame", action="store_true", help="skip git blame for SATD ages")
    args = parser.parse_args(argv)
    root = Path(args.path)
    workdir = Path(args.workdir)
    inventory_path = workdir / "inventory.json"
    if not inventory_path.is_file():
        print(f"error: {inventory_path} not found; run inventory.py first", file=sys.stderr)
        return 2
    try:
        inventory = json.loads(inventory_path.read_bytes())
        cfg = load_config(root)
        document, inline = run_patterns(root, inventory, cfg, blame=not args.no_blame)
    except (OSError, ValueError, ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for entry in inventory["files"]:
        entry["inline_disables"] = inline.get(str(entry["path"]), 0)
    patterns_path = workdir / "patterns.json"
    write_json(patterns_path, document)
    write_json(inventory_path, inventory)
    counts = ", ".join(f"{f} {n}" for f, n in document["stats"]["leads_per_family"].items())
    print(f"wrote {patterns_path} ({len(document['satd'])} SATD markers; leads: {counts})")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
```

(`SOURCE_TESTS`, `SOURCE_CI_CONFIG` and `TESTS` are used by the rules added in sub-deliverables B and C; ruff does not flag unused module constants.)

- [ ] **Step A4: Run the A tests to verify they pass**

Run: `pytest skills/tech-debt-scan/tests/test_patterns.py -v`
Expected: 7 passed.

- [ ] **Step A5: Lint, type-check, commit**

Run: `ruff check . && mypy`
Expected: clean.

```bash
git add skills/tech-debt-scan/scripts/patterns.py skills/tech-debt-scan/tests/test_patterns.py
git commit -m "feat(tech-debt-scan): patterns.py scanner core with the SATD table and blame ages"
```

#### Sub-deliverable B: error-masking and dead-code rules

- [ ] **Step B1: Write the failing tests**

Append to `skills/tech-debt-scan/tests/test_patterns.py`:

```python
# --- B: error-masking and dead-code ----------------------------------------------


def test_swallowed_catch_positives_in_three_languages(
    service_py: tuple[Path, dict[str, Any]],
    web_ts: tuple[Path, dict[str, Any]],
    mixed: tuple[Path, dict[str, Any]],
) -> None:
    py = _leads(_run(service_py, blame=False), "error-masking", "swallowed-catch")
    lead = py[("src/pay/refund.py", 33)]
    assert lead["quote"] == "except Exception:"
    assert lead["extra"] == {
        "variable": None,
        "body": "pass",
        "catch_all": False,
        "annotated": False,
        "line_end": 34,
    }
    ts = _leads(_run(web_ts, blame=False), "error-masking", "swallowed-catch")
    lead = ts[("src/api/client.ts", 11)]
    assert lead["extra"]["variable"] == "e"
    assert lead["extra"]["body"] == "empty"
    go = _leads(_run(mixed, blame=False), "error-masking", "swallowed-catch")
    assert go[("internal/store/store.go", 27)]["extra"]["body"] == "return"
    assert go[("internal/store/store.go", 27)]["extra"]["variable"] == "err"
    assert go[("internal/store/store.go", 27)]["extra"]["line_end"] == 29
    assert go[("internal/store/store.go", 31)]["extra"]["body"] == "log-only"


def test_catch_decoys_are_not_leads(
    service_py: tuple[Path, dict[str, Any]],
    web_ts: tuple[Path, dict[str, Any]],
    mixed: tuple[Path, dict[str, Any]],
) -> None:
    py = _leads(_run(service_py, blame=False), "error-masking", "swallowed-catch")
    assert ("src/pay/refund.py", 38) not in py  # log.exception(...) then raise ... from exc
    ts = _leads(_run(web_ts, blame=False), "error-masking", "swallowed-catch")
    assert ("src/api/client-admin.ts", 14) not in ts  # console.error("...", e)
    go = _leads(_run(mixed, blame=False), "error-masking", "swallowed-catch")
    assert ("internal/store/store.go", 19) not in go  # return nil, err
    assert not any(path == "cmd/app/main.go" for path, _ in go)  # logs err and exits


def test_catch_all_variants_and_annotation(tmp_path: Path) -> None:
    repo = _synthetic(
        tmp_path,
        {
            "a.py": "try:\n    run()\nexcept:  # noqa: E722\n    pass\n",
            "B.java": "class B {\n  void f() {\n    try { g(); } catch (Throwable t) {}\n  }\n}\n",
            "c.cs": "class C {\n  void F() {\n    try { G(); } catch { }\n  }\n}\n",
            "d.rb": "def d\n  run\nrescue => e\n  # ignored\nend\n",
        },
    )
    leads = _leads(_run(repo, blame=False), "error-masking", "swallowed-catch")
    assert leads[("a.py", 3)]["extra"]["catch_all"] is True
    assert leads[("a.py", 3)]["extra"]["annotated"] is True
    assert leads[("B.java", 3)]["extra"]["catch_all"] is True
    assert leads[("B.java", 3)]["extra"]["variable"] == "t"
    assert leads[("c.cs", 3)]["extra"]["catch_all"] is True
    assert leads[("c.cs", 3)]["extra"]["variable"] is None
    assert leads[("d.rb", 3)]["extra"]["variable"] == "e"
    assert leads[("d.rb", 3)]["extra"]["body"] == "empty"


def test_assertion_switches_two_languages(tmp_path: Path) -> None:
    repo = _synthetic(
        tmp_path,
        {
            ".github/workflows/ci.yml": (
                "jobs:\n  t:\n    steps:\n"
                "      - run: python -O app.py\n"
                "      - run: java -da -jar app.jar\n"
            ),
            "app.py": "x = 1\n# assert x > 0\n",
            "build.cpp": "#define NDEBUG\nint main() { return 0; }\n",
            "settings.json": '{"assertions": false}\n',
        },
    )
    leads = _leads(_run(repo, blame=False), "error-masking", "assertions-disabled")
    assert set(leads) == {
        (".github/workflows/ci.yml", 4),
        (".github/workflows/ci.yml", 5),
        ("app.py", 2),
        ("build.cpp", 1),
        ("settings.json", 1),
    }


def test_commented_out_code_two_languages(
    service_py: tuple[Path, dict[str, Any]], tmp_path: Path
) -> None:
    py = _leads(_run(service_py, blame=False), "dead-code", "commented-out-code")
    lead = py[("src/pay/legacy_export.py", 17)]
    assert lead["extra"] == {"line_end": 19, "code_like": 3, "total": 3}
    assert lead["quote"] == "# def export_v0(refund_id):"
    repo = _synthetic(
        tmp_path,
        {
            "store.go": (
                "package store\n\n// if err != nil {\n//     return err\n// }\n\nfunc F() {}\n"
            ),
            "prose.go": (
                "package prose\n\n// This helper exists because the upstream\n"
                "// client retries on our behalf and we\n"
                "// need to avoid double posting.\nfunc G() {}\n"
            ),
            "short.py": "# x = 1\n# y = 2\nz = 3\n",
            "unbalanced.py": "# if a:\n#     f(\n#     g(\nz = 3\n",
        },
    )
    leads = _leads(_run(repo, blame=False), "dead-code", "commented-out-code")
    assert set(leads) == {("store.go", 3)}
    assert leads[("store.go", 3)]["extra"] == {"line_end": 5, "code_like": 2, "total": 3}


def test_legacy_names_two_languages(
    service_py: tuple[Path, dict[str, Any]],
    mixed: tuple[Path, dict[str, Any]],
    tmp_path: Path,
) -> None:
    py = _leads(_run(service_py, blame=False), "dead-code", "legacy-name")
    assert py[("src/pay/legacy_export.py", 1)]["extra"] == {"where": "path", "token": "legacy"}
    assert py[("src/pay/legacy_export.py", 8)]["extra"] == {"where": "symbol", "token": "v1"}
    go = _leads(_run(mixed, blame=False), "dead-code", "legacy-name")
    assert go[("internal/dispatch/dispatch.go", 30)]["extra"] == {
        "where": "symbol", "token": "legacy",
    }
    repo = _synthetic(
        tmp_path,
        {
            "hold.py": "def holdOrder():\n    pass\n\n\nclass Bolder:\n    pass\n",
            "oldham/town.go": "package town\n",
        },
    )
    assert _leads(_run(repo, blame=False), "dead-code", "legacy-name") == {}


def test_deprecation_two_languages_with_caller_count(
    web_ts: tuple[Path, dict[str, Any]], mixed: tuple[Path, dict[str, Any]]
) -> None:
    ts = _leads(_run(web_ts, blame=False), "dead-code", "deprecation")
    assert ts[("src/util/format-legacy.ts", 3)]["extra"] == {"callers_approx": 1}
    go = _leads(_run(mixed, blame=False), "dead-code", "deprecation")
    assert go[("internal/httpc/httpc.go", 11)]["extra"] == {"callers_approx": 1}


def test_flag_sdk_two_languages(
    web_ts: tuple[Path, dict[str, Any]], mixed: tuple[Path, dict[str, Any]]
) -> None:
    ts = _leads(_run(web_ts, blame=False), "dead-code", "flag-sdk")
    assert ("src/checkout/checkout.ts", 7) in ts
    go = _leads(_run(mixed, blame=False), "dead-code", "flag-sdk")
    assert ("cmd/app/main.go", 22) in go
```

- [ ] **Step B2: Run the B tests to verify they fail**

Run: `pytest skills/tech-debt-scan/tests/test_patterns.py -k "catch or assertion or commented or legacy or deprecation or flag" -v`
Expected: every B test FAILS with `KeyError` on the first lookup (for example `KeyError: ('src/pay/refund.py', 33)`), because the families have no leads yet; `test_legacy_names_two_languages` reaches its final `== {}` only after the earlier `KeyError`.

- [ ] **Step B3: Add the scanners and rule rows**

Insert into `skills/tech-debt-scan/scripts/patterns.py` before the `# --- rule table` section:

```python
# --- error-masking --------------------------------------------------------------

# One union of catch idioms with the caught variable captured from whichever
# idiom matched (spec 4.3). Go's `if err != nil {` is the catch-less form.
CATCH_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*except\b(?P<py>[^:]*):"
    r"|\bcatch\s*\((?P<c>[^)]*)\)"
    r"|\bcatch\s*\{"
    r"|\bcatch\s+(?P<bare>[A-Za-z_]\w*)\s*(?:=>|\{|$)"
    r"|^\s*rescue\b(?P<rb>.*)$"
    r"|\bon\s+\w+\s+catch\s*\((?P<dart>[^)]*)\)"
    r"|\bif\b[^{]*?\b(?P<go>\w*[eE]rr\w*)\s*!=\s*nil\s*\{"
)
CARRIER_RE: Final[re.Pattern[str]] = re.compile(
    r"exc_info|\.exception\(|\bstack\w*|stackTrace|\berr\b|\bex\b|\be\)"
)
LOG_CALL_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:log|logger|logging|console|Log|fmt\.Print\w*|print|puts|warn|warning|error|info|"
    r"debug|trace|Console\.WriteLine|System\.out)\b"
)
SWALLOW_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:pass|return(?:\s+(?:None|null|nil))?;?|\.\.\.|;)$"
)
ANNOTATION_RE: Final[re.Pattern[str]] = re.compile(
    r"\bnoqa\b|\bnolint\b|eslint-disable|\bpragma\b"
)
PY_CATCH_ALL_RE: Final[re.Pattern[str]] = re.compile(r"^\s*$|\bBaseException\b")
C_CATCH_ALL_RE: Final[re.Pattern[str]] = re.compile(r"\bThrowable\b|^\s*\.\.\.\s*$")
IDENT_RE: Final[re.Pattern[str]] = re.compile(r"[A-Za-z_]\w*")
ASSERT_OFF_RE: Final[re.Pattern[str]] = re.compile(
    r"\bNDEBUG\b|\bpython[\d.]*\s+-OO?\b|(?<![\w-])-da\b|enableassertions\s*=\s*false"
    r"|\bassert(?:ions)?[\"']?\s*:\s*false|^\s*(?:#|//)\s*assert\b"
)


def _catch_variable(match: re.Match[str]) -> tuple[str | None, bool, bool]:
    """(caught variable, catches everything, body delimited by indentation)."""
    if match.group("py") is not None:
        spec = match.group("py")
        as_match = re.search(r"\bas\s+(\w+)", spec)
        variable = as_match.group(1) if as_match else None
        return variable, PY_CATCH_ALL_RE.search(spec) is not None, True
    if match.group("rb") is not None:
        arrow = re.search(r"=>\s*(\w+)", match.group("rb"))
        return (arrow.group(1) if arrow else None), False, True
    if match.group("c") is not None:
        spec = match.group("c")
        idents = IDENT_RE.findall(spec)
        return (idents[-1] if idents else None), C_CATCH_ALL_RE.search(spec) is not None, False
    if match.group("dart") is not None:
        idents = IDENT_RE.findall(match.group("dart"))
        return (idents[-1] if idents else None), False, False
    if match.group("bare") is not None:
        return match.group("bare"), False, False
    if match.group("go") is not None:
        return match.group("go"), False, False
    return None, True, False  # the `catch {` form


def _indented_body(lines: list[str], index: int) -> tuple[list[str], int]:
    """Stripped lines indented deeper than ``lines[index]``, and the last line's index."""
    start = lines[index]
    indent = len(start) - len(start.lstrip())
    body: list[str] = []
    end = index
    for j in range(index + 1, len(lines)):
        raw = lines[j]
        if not raw.strip():
            continue
        if len(raw) - len(raw.lstrip()) <= indent:
            break
        body.append(raw.strip())
        end = j
    return body, end


def _brace_body(lines: list[str], index: int, from_col: int) -> tuple[list[str], int]:
    """Stripped text chunks between the first `{` at or after ``from_col`` and its `}`."""
    depth = 0
    started = False
    chunks: list[str] = []
    current = ""
    for j in range(index, len(lines)):
        raw = lines[j]
        start = from_col if j == index else 0
        for char in raw[start:]:
            if char == "{":
                depth += 1
                if depth == 1:
                    started = True
                    continue
            elif char == "}":
                depth -= 1
                if started and depth == 0:
                    chunks.append(current)
                    return [c.strip() for c in chunks if c.strip()], j
            if started:
                current += char
        if started:
            chunks.append(current)
            current = ""
    return [c.strip() for c in chunks if c.strip()], len(lines) - 1


def _classify_body(body: list[str], variable: str | None, markers: Markers) -> str | None:
    """empty | pass | return | log-only, or None when the catch handles the error."""
    code = [b for b in body if not is_comment_line(b, markers)]
    if not code:
        return "empty"
    if all(SWALLOW_RE.match(b) for b in code):
        return "return" if any(b.startswith("return") for b in code) else "pass"
    if all(LOG_CALL_RE.search(b) for b in code):
        text = " ".join(code)
        if variable and re.search(rf"\b{re.escape(variable)}\b", text):
            return None
        if CARRIER_RE.search(text):
            return None
        return "log-only"
    return None


def _scan_catches(sf: ScanFile, rule: Rule, _ctx: ScanContext) -> list[Lead]:
    leads: list[Lead] = []
    for index, line in enumerate(sf.lines):
        match = rule.regex.search(line)
        if match is None:
            continue
        variable, catch_all, indented = _catch_variable(match)
        if indented:
            body, end = _indented_body(sf.lines, index)
        else:
            brace = line.find("{", match.start())
            if brace != -1:
                body, end = _brace_body(sf.lines, index, brace)
            elif index + 1 < len(sf.lines):
                body, end = _brace_body(sf.lines, index + 1, 0)
            else:
                body, end = [], index
        kind = _classify_body(body, variable, sf.markers)
        if kind is None:
            continue
        tail = line[match.end() :]
        annotated = bool(ANNOTATION_RE.search(line)) or "#" in tail or "//" in tail
        leads.append(
            Lead(
                rule.rule, sf.path, index + 1, line.strip(), sf.path_class,
                {
                    "variable": variable,
                    "body": kind,
                    "catch_all": catch_all,
                    "annotated": annotated,
                    "line_end": end + 1,
                },
            )
        )
    return leads


# --- dead-code ------------------------------------------------------------------

STATEMENT_KEYWORDS: Final[tuple[str, ...]] = (
    "if", "for", "while", "return", "def", "function", "class", "var", "let", "const", "int",
    "string", "public", "private", "static", "fn", "func", "import", "using", "switch", "case",
    "try", "catch", "elif", "else", "foreach",
)
CODE_LINE_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:" + "|".join(STATEMENT_KEYWORDS) + r")\b|^[A-Za-z_][\w.]*\s*(?:=[^=]|\()|[;{]$"
)
LEGACY_TOKENS: Final[frozenset[str]] = frozenset({"old", "bak", "v1", "legacy"})
DEF_LINE_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?(?:def|function|func|class|fn|struct|interface|type|"
    r"public|private|protected|internal|static|const|let|var)\b"
)
DEPRECATION_RE: Final[re.Pattern[str]] = re.compile(
    r"@deprecated\b|\[Obsolete\]|@Deprecated\b|DeprecationWarning|#\[deprecated\]"
    r"|^\s*(?://|#|\*|///)\s*Deprecated:|@available\(\*,\s*deprecated"
)
FLAG_SDK_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:bool)?[vV]ariation\(|\bisEnabled\(|\bIsEnabled\(|\bis_active\(|\bgetFeatureFlag\("
    r"|\bgetBooleanValue\(|\bFEATURE_[A-Z0-9_]+\b"
)


def _balanced(text: str) -> bool:
    return all(text.count(o) == text.count(c) for o, c in (("(", ")"), ("[", "]"), ("{", "}")))


def _scan_commented_code(sf: ScanFile, rule: Rule, _ctx: ScanContext) -> list[Lead]:
    leads: list[Lead] = []
    run: list[tuple[int, str]] = []

    def flush() -> None:
        if len(run) < 3:
            return
        bodies = [body for _, body in run]
        code_like = sum(1 for body in bodies if rule.regex.match(body))
        if code_like * 2 > len(bodies) and _balanced("\n".join(bodies)):
            first = run[0][0]
            leads.append(
                Lead(
                    rule.rule, sf.path, first, sf.lines[first - 1].strip(), sf.path_class,
                    {"line_end": run[-1][0], "code_like": code_like, "total": len(bodies)},
                )
            )

    for lineno, line in enumerate(sf.lines, start=1):
        if is_comment_line(line, sf.markers):
            run.append((lineno, strip_markers(line, sf.markers)))
        else:
            flush()
            run.clear()
    flush()
    return leads


def _identifier_words(identifier: str) -> list[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", identifier)
    return [word.lower() for word in re.split(r"[_\s-]+", spaced) if word]


def _scan_legacy_names(sf: ScanFile, rule: Rule, _ctx: ScanContext) -> list[Lead]:
    leads: list[Lead] = []
    path_words = [w for part in re.split(r"[/._-]+", sf.path) for w in _identifier_words(part)]
    hit = next((w for w in path_words if w in LEGACY_TOKENS), None)
    if hit and sf.lines:
        leads.append(
            Lead(
                rule.rule, sf.path, 1, sf.lines[0].strip(), sf.path_class,
                {"where": "path", "token": hit},
            )
        )
    for lineno, line in enumerate(sf.lines, start=1):
        if not rule.regex.match(line):
            continue
        for ident in IDENT_RE.findall(line):
            token = next((w for w in _identifier_words(ident) if w in LEGACY_TOKENS), None)
            if token:
                leads.append(
                    Lead(
                        rule.rule, sf.path, lineno, line.strip(), sf.path_class,
                        {"where": "symbol", "token": token},
                    )
                )
                break
    return leads


def _scan_deprecation(sf: ScanFile, rule: Rule, ctx: ScanContext) -> list[Lead]:
    leads = _scan_lines(sf, rule, ctx)
    for lead in leads:
        lead.extra = {"callers_approx": ctx.fan_in.get(sf.path)}
    return leads
```

Then replace the `RULES` tuple and `_HANDLERS` dict with:

```python
RULES: Final[tuple[Rule, ...]] = (
    Rule("half-finished", "satd-marker", SATD_RE, ALL_TEXT, blame=True, kind="satd"),
    Rule("error-masking", "swallowed-catch", CATCH_RE, SOURCE, kind="catch"),
    Rule("error-masking", "assertions-disabled", ASSERT_OFF_RE, SOURCE_CI_CONFIG),
    Rule("dead-code", "commented-out-code", CODE_LINE_RE, SOURCE, kind="commented-code"),
    Rule("dead-code", "legacy-name", DEF_LINE_RE, SOURCE, kind="legacy-name"),
    Rule("dead-code", "deprecation", DEPRECATION_RE, SOURCE, kind="deprecation"),
    Rule("dead-code", "flag-sdk", FLAG_SDK_RE, SOURCE),
)

_HANDLERS: Final[dict[str, Handler]] = {
    "line": _scan_lines,
    "satd": _scan_satd,
    "catch": _scan_catches,
    "commented-code": _scan_commented_code,
    "legacy-name": _scan_legacy_names,
    "deprecation": _scan_deprecation,
}
```

- [ ] **Step B4: Run the tests to verify they pass**

Run: `pytest skills/tech-debt-scan/tests/test_patterns.py -v`
Expected: 15 passed.

- [ ] **Step B5: Lint, type-check, commit**

Run: `ruff check . && mypy`
Expected: clean.

```bash
git add skills/tech-debt-scan/scripts/patterns.py skills/tech-debt-scan/tests/test_patterns.py
git commit -m "feat(tech-debt-scan): error-masking and dead-code pattern rules"
```

#### Sub-deliverable C: stubs and skips, security, test-quality, no-timeout, stdout, lint write-back, CLI, language-conditional grep

- [ ] **Step C1: Write the failing tests**

Extend the import block of `skills/tech-debt-scan/tests/test_patterns.py` to:

```python
import json
import re
from pathlib import Path
from typing import Any

import pytest
from config import DEFAULTS
from inventory import build_all, write_json
from patterns import RULES, Lead, capped_leads, redact, run_patterns
```

then append:

```python
# --- C: stubs, security, test-quality, no-timeout, stdout, lint, CLI, grep -------

LANGUAGE_BRANCH_RE = re.compile(
    r"^\s*(?:if|elif)\b.*(?:\b(?:language|lang)\b\s*(?:==|!=|\bin\b)"
    r"|[\"'](?:python|typescript|javascript|go|csharp|java|rust|ruby|php|kotlin|swift|cpp|c"
    r"|markdown)[\"'])"
)


def test_rule_table_covers_every_group() -> None:
    names = {r.rule for r in RULES}
    assert names >= {
        "satd-marker", "stub", "skip-marker", "no-timeout", "swallowed-catch",
        "assertions-disabled", "commented-out-code", "legacy-name", "deprecation", "flag-sdk",
        "credential", "string-sql", "dynamic-eval", "tls-disabled", "weak-hash",
        "permissive-cors", "security-suppression", "sleep", "retry-marker", "wall-clock",
        "unseeded-random", "try-in-test", "conditional-in-test", "numeric-assert",
        "assert-free", "stdout-write", "inline-disable",
    }
    assert len(RULES) >= 27


def test_stub_and_skip_leads_in_two_languages(
    service_py: tuple[Path, dict[str, Any]],
    web_ts: tuple[Path, dict[str, Any]],
    mixed: tuple[Path, dict[str, Any]],
) -> None:
    py = _run(service_py, blame=False)
    assert ("tests/test_refund.py", 21) in _leads(py, "half-finished", "stub")
    assert ("tests/test_refund.py", 19) in _leads(py, "half-finished", "skip-marker")
    go = _run(mixed, blame=False)
    assert ("internal/dispatch/dispatch.go", 31) in _leads(go, "half-finished", "stub")
    ts = _run(web_ts, blame=False)
    assert ("src/__tests__/pricing.spec.ts", 7) in _leads(ts, "half-finished", "skip-marker")


def test_credential_detected_and_redacted_in_two_languages(
    service_py: tuple[Path, dict[str, Any]], mixed: tuple[Path, dict[str, Any]]
) -> None:
    py = _leads(_run(service_py, blame=False), "security", "credential")
    lead = py[("src/pay/gateway.py", 11)]
    assert "sk_l***" in lead["quote"]
    assert "sk_live_51H8" not in lead["quote"]
    assert lead["extra"] == {"redacted": True}
    go = _leads(_run(mixed, blame=False), "security", "credential")
    assert "tok_***" in go[("internal/httpc/httpc.go", 9)]["quote"]
    assert redact('api_key = "sk_live_51H8f2kL9mN3pQ7rS4tU6vW"') == 'api_key = "sk_l***"'


def test_credential_exclusions(service_py: tuple[Path, dict[str, Any]], tmp_path: Path) -> None:
    py = _leads(_run(service_py, blame=False), "security", "credential")
    assert not any(path == "tests/fixtures/seed.py" for path, _ in py)
    repo = _synthetic(
        tmp_path,
        {
            "app.yml": (
                'password: "${DB_PASSWORD}"\n'
                'token: "{{ secrets.token }}"\n'
                'secret: "changeme-please-now"\n'
                'api_key: "<your-key-here>"\n'
                'password: "example_password_1"\n'
                'admin_password: "hunter2hunter2hunter2"\n'
                'short: "abc"\n'
            ),
            "src/x.py": "x = 1\n",
        },
    )
    leads = _leads(_run(repo, blame=False), "security", "credential")
    assert list(leads) == [("app.yml", 6)]
    assert leads[("app.yml", 6)]["quote"] == 'admin_password: "hunt***"'


def test_string_sql_two_languages_and_decoy(
    service_py: tuple[Path, dict[str, Any]], mixed: tuple[Path, dict[str, Any]], tmp_path: Path
) -> None:
    py = _leads(_run(service_py, blame=False), "security", "string-sql")
    assert ("src/pay/legacy_export.py", 11) in py
    go = _leads(_run(mixed, blame=False), "security", "string-sql")
    assert ("internal/store/store.go", 38) in go
    repo = _synthetic(
        tmp_path,
        {
            "db.py": (
                'cur.execute("SELECT 1 WHERE id = ?", (rid,))\n'
                'cur.execute("SELECT 1 WHERE id = %s", (rid,))\n'
            )
        },
    )
    assert _leads(_run(repo, blame=False), "security", "string-sql") == {}


def test_eval_tls_hash_cors_and_suppression_in_two_languages(
    service_py: tuple[Path, dict[str, Any]], mixed: tuple[Path, dict[str, Any]], tmp_path: Path
) -> None:
    py = _run(service_py, blame=False)
    go = _run(mixed, blame=False)
    assert ("src/pay/legacy_export.py", 13) in _leads(py, "security", "dynamic-eval")
    assert ("internal/shell/run.go", 7) in _leads(go, "security", "dynamic-eval")
    assert ("src/pay/gateway.py", 24) in _leads(py, "security", "tls-disabled")
    assert ("internal/httpc/httpc.go", 13) in _leads(go, "security", "tls-disabled")
    assert ("src/pay/utils.py", 11) in _leads(py, "security", "weak-hash")
    assert ("internal/crypto/hash.go", 9) in _leads(go, "security", "weak-hash")
    assert ("src/pay/gateway.py", 12) in _leads(py, "security", "permissive-cors")
    assert ("src/pay/legacy_export.py", 11) in _leads(py, "security", "security-suppression")
    assert ("internal/shell/run.go", 7) in _leads(go, "security", "security-suppression")
    repo = _synthetic(
        tmp_path,
        {
            "srv.go": (
                "package srv\n\nfunc h(w http.ResponseWriter) {\n"
                '\tw.Header().Set("Access-Control-Allow-Origin", "*")\n}\n'
            )
        },
    )
    assert ("srv.go", 4) in _leads(_run(repo, blame=False), "security", "permissive-cors")


def test_test_quality_signals_in_two_languages(
    service_py: tuple[Path, dict[str, Any]], mixed: tuple[Path, dict[str, Any]], tmp_path: Path
) -> None:
    py = _run(service_py, blame=False)
    go = _run(mixed, blame=False)
    assert ("tests/test_ledger.py", 13) in _leads(py, "test-quality", "sleep")
    assert ("internal/store/store_test.go", 15) in _leads(go, "test-quality", "sleep")
    py_free = _leads(py, "test-quality", "assert-free")
    go_free = _leads(go, "test-quality", "assert-free")
    assert py_free[("tests/test_ledger.py", 17)]["extra"] == {"test": "test_reverse_smoke"}
    assert go_free[("internal/store/store_test.go", 14)]["extra"] == {"test": "TestLoadSmoke"}
    assert ("tests/test_ledger.py", 10) not in py_free
    assert ("internal/store/store_test.go", 8) not in go_free
    assert ("tests/test_ledger.py", 14) in _leads(py, "test-quality", "numeric-assert")
    assert not any(p.startswith("src/") for p, _ in _leads(py, "test-quality", "sleep"))
    repo = _synthetic(
        tmp_path,
        {
            "tests/test_time.py": (
                "import random\nimport pytest\nfrom datetime import datetime\n\n"
                "@pytest.mark.flaky(reruns=3)\n"
                "def test_clock():\n"
                "    stamp = datetime.now()\n"
                "    pick = random.choice([1, 2])\n"
                "    try:\n"
                "        run(stamp, pick)\n"
                "    except ValueError:\n"
                "        pass\n"
                "    if pick == 1:\n"
                "        assert stamp\n"
            ),
            "src/__tests__/clock.test.ts": (
                "jest.retryTimes(3);\n"
                'test("clock", () => {\n'
                "  const stamp = Date.now();\n"
                "  const pick = Math.random();\n"
                "  try {\n"
                "    run(stamp, pick);\n"
                "  } catch (e) {}\n"
                "  if (pick > 0.5) {\n"
                "    expect(stamp).toBeGreaterThan(1700000000000);\n"
                "  }\n"
                "});\n"
            ),
        },
    )
    doc = _run(repo, blame=False)
    ts = "src/__tests__/clock.test.ts"
    expected = {
        "retry-marker": {("tests/test_time.py", 5), (ts, 1)},
        "wall-clock": {("tests/test_time.py", 7), (ts, 3)},
        "unseeded-random": {("tests/test_time.py", 8), (ts, 4)},
        "try-in-test": {("tests/test_time.py", 9), (ts, 5), (ts, 7)},
        "conditional-in-test": {("tests/test_time.py", 13), (ts, 8)},
        "numeric-assert": {(ts, 9)},
        "assert-free": set(),
    }
    for rule, hits in expected.items():
        assert set(_leads(doc, "test-quality", rule)) == hits, rule
    assert doc["leads"]["error-masking"] == []  # the catch in a test is not the catch rule's job


def test_no_timeout_in_three_languages_with_decoys(
    service_py: tuple[Path, dict[str, Any]],
    web_ts: tuple[Path, dict[str, Any]],
    mixed: tuple[Path, dict[str, Any]],
) -> None:
    py = _leads(_run(service_py, blame=False), "half-finished", "no-timeout")
    assert py[("src/pay/gateway.py", 20)]["extra"] == {"client": "requests/httpx"}
    assert ("src/pay/legacy_export.py", 18) not in py  # commented-out fetch( is skipped
    ts = _leads(_run(web_ts, blame=False), "half-finished", "no-timeout")
    assert ts[("src/api/client.ts", 9)]["extra"] == {"client": "fetch"}
    assert not any(path == "src/api/client-admin.ts" for path, _ in ts)
    go = _leads(_run(mixed, blame=False), "half-finished", "no-timeout")
    assert go[("internal/httpc/httpc.go", 14)]["extra"] == {"client": "net/http"}
    assert not any(path == "internal/httpc/httpc_safe.go" for path, _ in go)


def test_stdout_writes_need_a_logger_and_skip_cli(
    service_py: tuple[Path, dict[str, Any]],
    web_ts: tuple[Path, dict[str, Any]],
    mixed: tuple[Path, dict[str, Any]],
    tmp_path: Path,
) -> None:
    py = _leads(_run(service_py, blame=False), "pipeline-infra", "stdout-write")
    assert py[("src/pay/refund.py", 41)]["extra"] == {"count": 1}
    go = _leads(_run(mixed, blame=False), "pipeline-infra", "stdout-write")
    assert ("internal/store/store.go", 32) in go
    assert not any(path == "cmd/app/main.go" for path, _ in go)
    assert _run(web_ts, blame=False)["leads"]["pipeline-infra"] == []  # no logger library
    repo = _synthetic(
        tmp_path,
        {
            "cmd/tool/main.go": (
                'package main\n\nimport "fmt"\n\nfunc main() { fmt.Println("x") }\n'
            ),
            "internal/work.go": 'package work\n\nimport "log"\n\nfunc W() { fmt.Println("y") }\n',
            "server.py": 'import logging\n\ndef serve():\n    print("up")\n    print("ready")\n',
        },
    )
    leads = _leads(_run(repo, blame=False), "pipeline-infra", "stdout-write")
    assert set(leads) == {("internal/work.go", 5), ("server.py", 4)}
    assert leads[("server.py", 4)]["extra"] == {"count": 2}


def test_inline_disables_counted_and_written_back(
    service_py: tuple[Path, dict[str, Any]], mixed: tuple[Path, dict[str, Any]], tmp_path: Path
) -> None:
    from patterns import _main

    _, inline = run_patterns(service_py[0], service_py[1], DEFAULTS, blame=False)
    assert inline["src/pay/legacy_export.py"] == 2
    assert inline["src/pay/refund.py"] == 0
    assert "tests/test_refund.py" not in inline  # source files only
    _, inline_go = run_patterns(mixed[0], mixed[1], DEFAULTS, blame=False)
    assert inline_go["internal/shell/run.go"] == 1
    workdir = tmp_path / "wd"
    write_json(workdir / "inventory.json", service_py[1])
    assert _main([str(service_py[0]), "--workdir", str(workdir), "--no-blame"]) == 0
    inventory = json.loads((workdir / "inventory.json").read_bytes())
    counts = {e["path"]: e["inline_disables"] for e in inventory["files"]}
    assert counts["src/pay/legacy_export.py"] == 2
    assert counts["tests/test_refund.py"] == 0
    raw = (workdir / "patterns.json").read_bytes()
    assert b"\r\n" not in raw
    patterns = json.loads(raw)
    assert patterns["schema_version"] == 2
    assert all(s["age_days"] is None for s in patterns["satd"])
    assert "sk_live_51H8" not in raw.decode("utf-8")


def test_cli_missing_inventory_exits_2(tmp_path: Path) -> None:
    from patterns import _main

    assert _main([str(tmp_path), "--workdir", str(tmp_path / "none")]) == 2


def test_no_script_branches_on_a_language_name() -> None:
    allowed = {"tools_probe.py"}  # the spec's tool normalisers are the one exception (0(d))
    offenders: list[str] = []
    for script in sorted(SCRIPTS.glob("*.py")):
        if script.name in allowed:
            continue
        for lineno, line in enumerate(script.read_text(encoding="utf-8").splitlines(), start=1):
            if LANGUAGE_BRANCH_RE.search(line):
                offenders.append(f"{script.name}:{lineno}: {line.strip()}")
    assert offenders == []
```

- [ ] **Step C2: Run the C tests to verify they fail**

Run: `pytest skills/tech-debt-scan/tests/test_patterns.py -v`
Expected: collection error `ImportError: cannot import name 'redact' from 'patterns'` (the name does not exist until Step C3). Once C3 lands, each corpus assertion is exercised for real; a rule that misfires shows as a `KeyError` on its `(file, line)` lookup, and `test_no_script_branches_on_a_language_name` also guards every pre-existing script.

- [ ] **Step C3: Add the remaining scanners and rule rows**

Change the `reference_graph` import at the top of `skills/tech-debt-scan/scripts/patterns.py` to `from reference_graph import import_lines, numbered_logical_lines`, then insert before the `# --- rule table` section:

```python
# --- half-finished: stubs, skips, no-timeout ---------------------------------------

STUB_RE: Final[re.Pattern[str]] = re.compile(
    r"NotImplementedError|NotImplementedException|\bnot implemented\b|unimplemented!"
    r"|panic\(\"not implemented|throw new Error\(\"not implemented|\bTODO\(\)",
    re.IGNORECASE,
)
SKIP_RE: Final[re.Pattern[str]] = re.compile(
    r"\bxfail\b|expectedFailure|@pytest\.mark\.skip|@Ignore\b|@Disabled\b|\bit\.skip\("
    r"|\btest\.skip\(|\[Ignore\]|\bt\.Skip\("
)
# (label, client-call idiom, the timeout argument that idiom must carry)
TIMEOUT_TABLE: Final[tuple[tuple[str, re.Pattern[str], re.Pattern[str]], ...]] = (
    (
        "requests/httpx",
        re.compile(r"\b(?:requests|httpx)\.(?:get|post|put|delete|patch|head|request)\("),
        re.compile(r"\btimeout\s*="),
    ),
    ("fetch", re.compile(r"\bfetch\("), re.compile(r"\bsignal\b|\btimeout\b")),
    ("axios", re.compile(r"\baxios(?:\.\w+)?\("), re.compile(r"\btimeout\b|\bsignal\b")),
    ("HttpClient", re.compile(r"new\s+HttpClient\("), re.compile(r"\bTimeout\b")),
    ("net/http", re.compile(r"\bhttp\.(?:Get|Post|Head|PostForm)\("), re.compile(r"\bTimeout\b")),
    ("http.Client", re.compile(r"&http\.Client\{"), re.compile(r"\bTimeout\b")),
    ("Net::HTTP", re.compile(r"Net::HTTP"), re.compile(r"read_timeout")),
    ("urlopen", re.compile(r"\burlopen\("), re.compile(r"\btimeout\b")),
    ("curl", re.compile(r"(?<![\w.])curl\b"), re.compile(r"--max-time|(?<!\w)-m\s+\d")),
)
NO_TIMEOUT_RE: Final[re.Pattern[str]] = re.compile(
    "|".join(call.pattern for _label, call, _timeout in TIMEOUT_TABLE)
)


def _scan_no_timeout(sf: ScanFile, rule: Rule, _ctx: ScanContext) -> list[Lead]:
    leads: list[Lead] = []
    for lineno, logical in numbered_logical_lines(sf.lines):
        if is_comment_line(logical, sf.markers):
            continue
        for label, call_re, timeout_re in TIMEOUT_TABLE:
            if call_re.search(logical) and not timeout_re.search(logical):
                leads.append(
                    Lead(
                        rule.rule, sf.path, lineno, sf.lines[lineno - 1].strip(), sf.path_class,
                        {"client": label},
                    )
                )
                break
    return leads


# --- security -------------------------------------------------------------------

CREDENTIAL_RE: Final[re.Pattern[str]] = re.compile(
    r"\b\w*(?:password|passwd|secret|token|api_key|apikey|access_key)\w*[\"']?\s*(?:=|:=|:)\s*"
    r"[\"'](?P<value>[^\"'\n]{8,})[\"']",
    re.IGNORECASE,
)
PLACEHOLDER_RE: Final[re.Pattern[str]] = re.compile(
    r"fake|dummy|example|placeholder|changeme|your_|xxx", re.IGNORECASE
)
PLACEHOLDER_PREFIXES: Final[tuple[str, ...]] = ("$", "${", "{{", "<", "%")
SQL_CALL_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:execute|query|Query|ExecuteSqlRaw|Raw|createStatement|executeQuery|Exec)\s*\("
    r"(?P<arg>[^\n]*)"
)
SQL_BUILT_RE: Final[re.Pattern[str]] = re.compile(
    r"\+\s*\w|\w\s*\+|\bf[\"']|\$\{|String\.format|\$\"|[\"']\s*%\s*[\w(]|\.format\("
)
DYNAMIC_EVAL_RE: Final[re.Pattern[str]] = re.compile(
    r"\beval\(|\bexec\(|shell\s*=\s*True|shell:\s*true|child_process\.exec\(|Runtime\.exec\("
    r"|Process\.Start\(|exec\.Command\(|\bsystem\("
)
TLS_OFF_RE: Final[re.Pattern[str]] = re.compile(
    r"verify\s*=\s*False|rejectUnauthorized:\s*false|InsecureSkipVerify:\s*true"
    r"|ServerCertificateValidationCallback|VERIFY_NONE|(?<!\w)--insecure\b"
)
WEAK_HASH_RE: Final[re.Pattern[str]] = re.compile(
    r"\bmd5\(|\bsha1\(|MD5\.Create|getInstance\(\"MD5\"\)|createHash\(['\"]md5['\"]\)"
    r"|Digest::MD5|\bmd5\.(?:Sum|New)\(|\bsha1\.(?:Sum|New)\("
)
CORS_RE: Final[re.Pattern[str]] = re.compile(r"Access-Control-Allow-Origin[\"']?\s*[:,]\s*[\"']?\*")
SEC_SUPPRESS_RE: Final[re.Pattern[str]] = re.compile(
    r"\bnosec\b|eslint-disable[^\n]*security|nolint:gosec"
    r"|pragma\s+warning\s+disable[^\n]*\bCA\d+"
)


def redact(text: str) -> str:
    """Cut every credential-shaped value in ``text`` to its first four characters."""

    def cut(match: re.Match[str]) -> str:
        value = match.group("value")
        return match.group(0).replace(value, value[:4] + "***")

    return CREDENTIAL_RE.sub(cut, text)


def _scan_credentials(sf: ScanFile, rule: Rule, _ctx: ScanContext) -> list[Lead]:
    if sf.path_class == "tests":
        return []
    leads: list[Lead] = []
    for lineno, line in enumerate(sf.lines, start=1):
        match = rule.regex.search(line)
        if match is None:
            continue
        value = match.group("value")
        if value.startswith(PLACEHOLDER_PREFIXES) or PLACEHOLDER_RE.search(value):
            continue
        leads.append(
            Lead(
                rule.rule, sf.path, lineno, redact(line.strip()), sf.path_class,
                {"redacted": True},
            )
        )
    return leads


def _scan_string_sql(sf: ScanFile, rule: Rule, _ctx: ScanContext) -> list[Lead]:
    leads: list[Lead] = []
    for lineno, line in enumerate(sf.lines, start=1):
        match = rule.regex.search(line)
        if match is not None and SQL_BUILT_RE.search(match.group("arg")):
            leads.append(Lead(rule.rule, sf.path, lineno, line.strip(), sf.path_class))
    return leads


# --- test-quality ---------------------------------------------------------------

SLEEP_RE: Final[re.Pattern[str]] = re.compile(r"\bsleep\(|Thread\.Sleep|setTimeout\(|time\.Sleep\(")
RETRY_RE: Final[re.Pattern[str]] = re.compile(
    r"@retry\b|\bflaky\b|\breruns\b|\bretries\s*[=:(]|jest\.retryTimes|\[Retry\]|@Repeat\b"
)
WALLCLOCK_RE: Final[re.Pattern[str]] = re.compile(
    r"\bnow\(\)|Date\.now\(|DateTime\.(?:Now|UtcNow)|time\.Now\(|Time\.now|new Date\(\)"
)
RANDOM_RE: Final[re.Pattern[str]] = re.compile(
    r"\brandom\.\w+\(|Math\.random\(|\brand\.\w+\(|new Random\(\)"
)
SEEDED_RE: Final[re.Pattern[str]] = re.compile(r"seed", re.IGNORECASE)
TRY_IN_TEST_RE: Final[re.Pattern[str]] = re.compile(r"^\s*try\s*[:{]?\s*$|\bcatch\s*\(")
CONDITIONAL_RE: Final[re.Pattern[str]] = re.compile(r"^\s*(?:if|elif|else if|switch)\b")
NUMERIC_ASSERT_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:assert\w*|expect|Assert\.\w+|require\.\w+|should)\b[^\n]*?"
    r"(?<![\w.])(?:\d{2,}|\d+\.\d+)\b"
)
TEST_FN_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:async\s+)?def\s+test_\w+|^\s*func\s+Test\w+\(|^\s*(?:it|test)(?:\.only|\.skip)?\s*\("
    r"|^\s*@Test\b|^\s*\[(?:Fact|Test)\]"
)
TEST_NAME_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:def|func)\s+(\w+)|(?:it|test)(?:\.\w+)?\s*\(\s*[\"'`]([^\"'`]*)"
)
ASSERT_RE: Final[re.Pattern[str]] = re.compile(
    r"\bassert\w*\b|\bexpect\(|\bAssert\.|\brequire\."
    r"|\bt\.(?:Error|Errorf|Fatal|Fatalf|Fail|FailNow)\b"
    r"|\bshould\b|\.toBe|\.toEqual|pytest\.raises|\.Should\("
)


def _scan_assert_free(sf: ScanFile, rule: Rule, _ctx: ScanContext) -> list[Lead]:
    leads: list[Lead] = []
    lines = sf.lines
    starts = [i for i, line in enumerate(lines) if rule.regex.match(line)]
    for start in starts:
        end = len(lines)
        for j in range(start + 1, len(lines)):
            line = lines[j]
            top_level = bool(line.strip()) and not line[0].isspace() and not line.startswith("}")
            if rule.regex.match(line) or top_level:
                end = j
                break
        if ASSERT_RE.search("\n".join(lines[start:end])):
            continue
        name_match = TEST_NAME_RE.search(lines[start])
        name = lines[start].strip()[:60]
        if name_match is not None:
            name = name_match.group(1) or name_match.group(2) or name
        leads.append(
            Lead(rule.rule, sf.path, start + 1, lines[start].strip(), sf.path_class, {"test": name})
        )
    return leads


# --- pipeline-infra: stdout writes; lint: inline disables --------------------------

STDOUT_RE: Final[re.Pattern[str]] = re.compile(
    r"\bprint\(|console\.log\(|System\.out\.println\(|fmt\.Print(?:ln|f)?\(|^\s*puts\s|^\s*echo\s"
    r"|Console\.WriteLine\(|\bprintf\("
)
CLI_SEGMENTS: Final[frozenset[str]] = frozenset({"cli", "cmd", "bin", "scripts", "tools"})
ENTRY_RE: Final[re.Pattern[str]] = re.compile(
    r"if __name__ == [\"']__main__[\"']|func main\(\)|static void Main|fn main\(\)|process\.argv"
)
INLINE_DISABLE_RE: Final[re.Pattern[str]] = re.compile(
    r"\bnoqa\b|eslint-disable|pragma\s+warning\s+disable|SuppressWarnings|\bnolint\b"
    r"|rubocop:disable|#\[allow\(|\bnosec\b"
)


def _scan_stdout(sf: ScanFile, rule: Rule, ctx: ScanContext) -> list[Lead]:
    if not ctx.logger_present:
        return []
    if CLI_SEGMENTS & set(sf.path.split("/")[:-1]) or ENTRY_RE.search(sf.text):
        return []
    hits = [(i, line) for i, line in enumerate(sf.lines, start=1) if rule.regex.search(line)]
    if not hits:
        return []
    first, line = hits[0]
    return [Lead(rule.rule, sf.path, first, line.strip(), sf.path_class, {"count": len(hits)})]
```

Replace the `RULES` tuple and `_HANDLERS` dict with the complete table:

```python
RULES: Final[tuple[Rule, ...]] = (
    # satd group (half-finished)
    Rule("half-finished", "satd-marker", SATD_RE, ALL_TEXT, blame=True, kind="satd"),
    Rule("half-finished", "stub", STUB_RE, SOURCE_TESTS),
    Rule("half-finished", "skip-marker", SKIP_RE, SOURCE_TESTS),
    # requirement group (half-finished)
    Rule("half-finished", "no-timeout", NO_TIMEOUT_RE, SOURCE, kind="no-timeout"),
    # error-masking
    Rule("error-masking", "swallowed-catch", CATCH_RE, SOURCE, kind="catch"),
    Rule("error-masking", "assertions-disabled", ASSERT_OFF_RE, SOURCE_CI_CONFIG),
    # dead-code
    Rule("dead-code", "commented-out-code", CODE_LINE_RE, SOURCE, kind="commented-code"),
    Rule("dead-code", "legacy-name", DEF_LINE_RE, SOURCE, kind="legacy-name"),
    Rule("dead-code", "deprecation", DEPRECATION_RE, SOURCE, kind="deprecation"),
    Rule("dead-code", "flag-sdk", FLAG_SDK_RE, SOURCE),
    # security
    Rule("security", "credential", CREDENTIAL_RE, SOURCE_CI_CONFIG, kind="credential"),
    Rule("security", "string-sql", SQL_CALL_RE, SOURCE, kind="string-sql"),
    Rule("security", "dynamic-eval", DYNAMIC_EVAL_RE, SOURCE_CI_CONFIG),
    Rule("security", "tls-disabled", TLS_OFF_RE, SOURCE_CI_CONFIG),
    Rule("security", "weak-hash", WEAK_HASH_RE, SOURCE),
    Rule("security", "permissive-cors", CORS_RE, SOURCE_CI_CONFIG),
    Rule("security", "security-suppression", SEC_SUPPRESS_RE, SOURCE_CI_CONFIG),
    # test-quality
    Rule("test-quality", "sleep", SLEEP_RE, TESTS),
    Rule("test-quality", "retry-marker", RETRY_RE, TESTS),
    Rule("test-quality", "wall-clock", WALLCLOCK_RE, TESTS),
    Rule("test-quality", "unseeded-random", RANDOM_RE, TESTS, exclude=SEEDED_RE),
    Rule("test-quality", "try-in-test", TRY_IN_TEST_RE, TESTS),
    Rule("test-quality", "conditional-in-test", CONDITIONAL_RE, TESTS),
    Rule("test-quality", "numeric-assert", NUMERIC_ASSERT_RE, TESTS),
    Rule("test-quality", "assert-free", TEST_FN_RE, TESTS, kind="assert-free"),
    # observability (pipeline-infra)
    Rule("pipeline-infra", "stdout-write", STDOUT_RE, SOURCE, kind="stdout"),
    # lint (signal only; counted into inventory.files[].inline_disables)
    Rule("lint", "inline-disable", INLINE_DISABLE_RE, SOURCE, kind="inline-disable"),
)

_HANDLERS: Final[dict[str, Handler]] = {
    "line": _scan_lines,
    "satd": _scan_satd,
    "catch": _scan_catches,
    "commented-code": _scan_commented_code,
    "legacy-name": _scan_legacy_names,
    "deprecation": _scan_deprecation,
    "no-timeout": _scan_no_timeout,
    "credential": _scan_credentials,
    "string-sql": _scan_string_sql,
    "assert-free": _scan_assert_free,
    "stdout": _scan_stdout,
    "inline-disable": _scan_lines,
}
```

and change the per-file loop inside `run_patterns` to route the lint row and redact every security quote:

```python
    for sf in files:
        for rule in RULES:
            if sf.path_class not in rule.scope:
                continue
            found = _HANDLERS[rule.kind](sf, rule, ctx)
            if rule.kind == "satd":
                satd.extend(_satd_entry(lead) for lead in found)
            elif rule.kind == "inline-disable":
                inline[sf.path] = len(found)
            else:
                if rule.family == "security":
                    for lead in found:
                        lead.quote = redact(lead.quote)
                leads[rule.family].extend(found)
```

(delete the earlier `if sf.path_class == "source": inline[sf.path] = 0` lines; the lint row's `SOURCE` scope gives every source file an entry).

- [ ] **Step C4: Run the whole file to verify it passes**

Run: `pytest skills/tech-debt-scan/tests/test_patterns.py -v`
Expected: 27 passed.

- [ ] **Step C5: Lint, type-check, whole suite, commit**

Run: `ruff check . && mypy && pytest -q`
Expected: clean; every test passing.

```bash
git add skills/tech-debt-scan/scripts/patterns.py skills/tech-debt-scan/tests/test_patterns.py
git commit -m "feat(tech-debt-scan): security, test-quality, no-timeout, stdout and lint pattern rules with CLI"
```

---

### Task 11: `rules.py` (deterministic pipeline-infra, manifest and ownership findings)

**Files:**
- Create: `skills/tech-debt-scan/scripts/rules.py`
- Create: `skills/tech-debt-scan/tests/test_rules.py`

**Interfaces:**
- Consumes: `build_all`, `write_json` (Tasks 7 and 9); `DEFAULTS`, `deep_merge`, `load_config`, `ConfigError` (Task 1); the inventory shape from Tasks 5 to 9 (`artefacts`, `git`, `hotspot_band`, `hotspots`, `docs`, `files[].top_author_line_share`, `files[].top_author`, `files[].authors`); the corpus fixtures (Task 4).
- Produces (used by Task 12's evaluator, Task 13's docs and phase 2's `merge_findings.py`):
  - `SCHEMA_VERSION = 2`
  - `@dataclass(slots=True) class Hit(rule_id: str, file: str | None, line: int | None, quote: str, note: str, severity: int)`
  - `GROUP_META: dict[str, tuple[str, str, str, str]]` mapping group to `(family, debt_type, type_id, effort)`
  - `def fingerprint(family: str, path: str, quote: str) -> tuple[str, str]` (spec 4.7: `sha1(family + "|" + path + "|" + sha1(normalised quote))[:16]` and the inner `quote_hash`)
  - `def run_rules(root: Path, inventory: dict[str, Any], config: dict[str, Any], *, now: datetime | None = None) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]` returning `(findings, leads)`: each finding is a spec 4.7 candidate with `source: "rule"`, `tier: "A"`, `confirmed_by: ["rule:<rule_id>", ...]`; `leads` is `{"migration": [...]}`
  - CLI `python scripts/rules.py <repo> --workdir .tech-debt` writing `rule-findings.json` as `{"schema_version": 2, "findings": [...], "leads": {"migration": [...]}}`

**Spec:** 4.4 (every rule group, one aggregated finding per file, severity 2 to 3 with the `release|publish|deploy` rule, dev-only severity drop, ownership severities and suppression below three human authors, thresholds under `rules` in config, output in the 4.7 candidate schema with `source: "rule"`, `tier: "A"`, `confirmed_by: ["rule:<rule_id>"]`), 4.7 (candidate schema and fingerprint), 2.3 (ownership wording "no commits in N days", never "has left"; ownership tier A by construction), 2.1 (TD-14, TD-19, TD-27 for the pipeline-infra groups, TD-02 for the manifest group, TD-16 and TD-23 for ownership).

**Decisions the spec leaves open, fixed here (flagged for the lead):** spec 4.4 says `rule-findings.json` "is a list" and also that migration leads go "into the leads block, not findings"; since spec 9 makes the `patterns.py` write-back the only cross-script in-place edit, the file is an object `{schema_version, findings, leads}` so the leads have a home, and phase 2's `merge_findings.py` reads `findings`. Manifest-group findings carry family `dependency-debt` (their debt type is `dependency` in 4.4's table) at tier A per 4.4, although 2.3 caps structural dependency facts at tier B; the lead decides which wins. Repository-level facts (tag cadence, stale environment branches, no CODEOWNERS, stale branch count, missing ADR and PR template) have no file: their evidence carries `file: null`, `line_start: null`, `line_end: null`, a quote stating the fact and `quote_verified: true`, the shape spec 4.5 gives osv facts; ownership findings on a hotspot file carry the file with null lines. Efforts: `S` for ci, container, iac and manifest, `M` for release and ownership. Severities 4.4 does not state are 2 (former contributor, unowned hotspot, no CODEOWNERS, too many stale branches). Title: `"<group label> in <path>"`, or the label alone for repository-level findings, cut to 80 characters. Job-level ci rules apply to files under `.github/workflows/`; the commented-out job check applies to every ci artefact. The iac group checks YAML documents with a `kind` and `containers`/`initContainers` lists only (Terraform and Bicep rules are not in 4.4). `main` and `master` never count as stale branches.

**Confidence:** 90% (YAML parsing and threshold logic over the verified inventory; the release rules depend on branch dates that only get older, and the former-contributor rule starts firing on the corpus after 2026-12-19, which the tests allow for by asserting membership rather than exact rule sets; `now` is injectable so the release tests pin 2026-09-04).

- [ ] **Step 1: Write the failing tests**

Create `skills/tech-debt-scan/tests/test_rules.py`:

```python
"""rules.py: deterministic pipeline-infra, manifest, release and ownership findings."""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from config import DEFAULTS, deep_merge
from inventory import build_all, write_json
from rules import fingerprint, run_rules

NOW = datetime(2026, 9, 4, tzinfo=UTC)
Repo = tuple[Path, dict[str, Any]]
Finding = dict[str, Any]


@pytest.fixture(scope="module")
def service_py(service_py_repo: Path) -> Repo:
    inventory, _ = build_all(service_py_repo, churn_months=240)
    return service_py_repo, inventory


@pytest.fixture(scope="module")
def web_ts(web_ts_repo: Path) -> Repo:
    inventory, _ = build_all(web_ts_repo, churn_months=240)
    return web_ts_repo, inventory


@pytest.fixture(scope="module")
def mixed(mixed_decoys_repo: Path) -> Repo:
    inventory, _ = build_all(mixed_decoys_repo, churn_months=240)
    return mixed_decoys_repo, inventory


def _run(repo: Repo, config: dict[str, Any] | None = None) -> list[Finding]:
    findings, _leads = run_rules(repo[0], repo[1], config or DEFAULTS, now=NOW)
    return findings


def _leads(repo: Repo) -> dict[str, list[dict[str, Any]]]:
    _findings, leads = run_rules(repo[0], repo[1], DEFAULTS, now=NOW)
    return leads


def _at(findings: list[Finding], family: str, path: str | None) -> Finding | None:
    for finding in findings:
        if finding["family"] == family and finding["evidence"][0]["file"] == path:
            return finding
    return None


def _rules(finding: Finding | None) -> set[str]:
    return set(finding["confirmed_by"]) if finding else set()


def test_finding_schema_source_tier_and_one_per_file(service_py: Repo) -> None:
    findings = _run(service_py)
    keys = [(f["family"], f["evidence"][0]["file"]) for f in findings]
    assert len(keys) == len(set(keys))
    ci = _at(findings, "pipeline-infra", ".github/workflows/ci.yml")
    assert ci is not None
    assert list(ci) == [
        "fingerprint", "quote_hash", "family", "debt_type", "type_id", "title", "severity",
        "effort", "source", "rule_id", "note", "evidence", "confirmed_by", "signals_cited",
        "signals", "tier",
    ]
    assert (ci["source"], ci["tier"], ci["debt_type"], ci["type_id"]) == (
        "rule", "A", "build", "TD-14",
    )
    assert _rules(ci) == {
        "rule:ci.no-timeout", "rule:ci.no-permissions", "rule:ci.unpinned-action",
        "rule:ci.mutable-runner", "rule:ci.no-cache",
    }
    assert ci["severity"] == 2
    assert ci["effort"] == "S"
    assert ci["rule_id"].startswith("ci.")
    assert all(e["quote_verified"] is True for e in ci["evidence"])
    assert all(e["line_start"] == e["line_end"] for e in ci["evidence"])
    assert len(ci["fingerprint"]) == 16 and len(ci["quote_hash"]) == 40
    assert ci["signals"]["path_class"] == "ci"
    assert ci["signals"]["in_hotspot_band"] is False
    assert len(ci["title"]) <= 80
    assert ci["signals_cited"] == []


def test_fingerprint_matches_the_merge_formula() -> None:
    inner = hashlib.sha1(b"uses: actions/checkout@v4").hexdigest()
    outer = hashlib.sha1(f"pipeline-infra|.github/workflows/ci.yml|{inner}".encode()).hexdigest()
    got = fingerprint("pipeline-infra", ".github/workflows/ci.yml", "uses:   actions/checkout@v4")
    assert got == (outer[:16], inner)


def test_release_workflow_without_permissions_is_severity_3(service_py: Repo) -> None:
    release = _at(_run(service_py), "pipeline-infra", ".github/workflows/release.yml")
    assert release is not None
    assert release["severity"] == 3
    assert "rule:ci.no-permissions" in _rules(release)
    assert "rule:ci.unpinned-action" not in _rules(release)
    assert "rule:ci.no-timeout" not in _rules(release)
    assert "rule:ci.mutable-runner" not in _rules(release)


def test_clean_workflow_and_commented_job(web_ts: Repo, mixed: Repo) -> None:
    assert _at(_run(web_ts), "pipeline-infra", ".github/workflows/ci.yml") is None
    ci = _at(_run(mixed), "pipeline-infra", ".github/workflows/ci.yml")
    assert _rules(ci) == {
        "rule:ci.continue-on-error", "rule:ci.unpinned-action", "rule:ci.mutable-runner",
        "rule:ci.commented-job",
    }
    assert ci is not None and ci["severity"] == 2


def test_container_rules_and_dev_only_drop(service_py: Repo, mixed: Repo) -> None:
    docker = _at(_run(service_py), "pipeline-infra", "Dockerfile")
    assert _rules(docker) == {"rule:container.no-user", "rule:container.unversioned-install"}
    assert docker is not None
    assert docker["severity"] == 2
    assert (docker["debt_type"], docker["type_id"]) == ("infrastructure", "TD-19")
    mixed_findings = _run(mixed)
    assert _rules(_at(mixed_findings, "pipeline-infra", "Dockerfile")) == {
        "rule:container.unversioned-install",
    }
    dev = _at(mixed_findings, "pipeline-infra", "docker-compose.dev.yml")
    assert _rules(dev) == {"rule:container.latest-image"}
    assert dev is not None
    assert dev["severity"] == 1  # dev-only path drops one severity
    assert [e["line_start"] for e in dev["evidence"]] == [3, 5]
    assert _at(mixed_findings, "pipeline-infra", "docker-compose.yml") is None


def test_iac_rules(mixed: Repo) -> None:
    findings = _run(mixed)
    deployment = _at(findings, "pipeline-infra", "k8s/deployment.yaml")
    assert _rules(deployment) == {
        "rule:iac.no-resource-limits", "rule:iac.latest-image", "rule:iac.privileged",
    }
    assert deployment is not None and deployment["severity"] == 2
    assert _at(findings, "pipeline-infra", "k8s/service.yaml") is None


def test_manifest_rules_and_migration_leads(service_py: Repo, web_ts: Repo, mixed: Repo) -> None:
    findings = _run(service_py)
    pyproject = _at(findings, "dependency-debt", "pyproject.toml")
    assert _rules(pyproject) == {"rule:manifest.no-lockfile"}
    assert pyproject is not None
    assert (pyproject["debt_type"], pyproject["type_id"]) == ("dependency", "TD-02")
    assert pyproject["evidence"][0]["quote"] == "[project]"
    assert _at(findings, "dependency-debt", "requirements.txt") is None
    assert _leads(service_py) == {
        "migration": [
            {
                "rule": "dual-manifest",
                "file": "setup.py",
                "line": 1,
                "quote": '"""Legacy packaging shim; pyproject.toml is the source of truth."""',
                "path_class": "source",
                "extra": {"pair": ["setup.py", "pyproject.toml"]},
            }
        ]
    }
    web_findings = _run(web_ts)
    assert _rules(_at(web_findings, "dependency-debt", "package.json")) == {
        "rule:manifest.two-lockfiles",
    }
    web_leads = _leads(web_ts)["migration"]
    assert [lead["file"] for lead in web_leads] == ["tslint.json"]
    assert web_leads[0]["extra"] == {"pair": ["tslint.json", ".eslintrc.json"]}
    assert _at(_run(mixed), "dependency-debt", "go.mod") is None
    assert _leads(mixed) == {"migration": []}


@pytest.mark.parametrize(
    ("fixture_name", "branch"),
    [("service_py", "hotfix/ledger-rounding"), ("web_ts", "release/1.2"), ("mixed", "staging")],
)
def test_stale_environment_branches(
    request: pytest.FixtureRequest, fixture_name: str, branch: str
) -> None:
    repo: Repo = request.getfixturevalue(fixture_name)
    release = _at(_run(repo), "pipeline-infra", None)
    assert release is not None
    assert "rule:release.stale-env-branch" in _rules(release)
    assert branch in release["evidence"][0]["quote"]
    assert release["evidence"][0]["line_start"] is None
    assert release["type_id"] == "TD-27"
    assert release["effort"] == "M"
    assert "rule:release.tag-cadence" not in _rules(release)


def test_tag_cadence_threshold_from_config(service_py: Repo) -> None:
    inventory = json.loads(json.dumps(service_py[1]))
    dates = [
        "2024-01-01T00:00:00Z", "2024-02-01T00:00:00Z", "2024-03-01T00:00:00Z",
        "2024-04-01T00:00:00Z", "2024-05-01T00:00:00Z", "2026-01-01T00:00:00Z",
    ]
    inventory["git"]["tags"] = [{"name": f"v0.{i}", "date": d} for i, d in enumerate(dates)]
    findings, _ = run_rules(service_py[0], inventory, DEFAULTS, now=NOW)
    release = _at(findings, "pipeline-infra", None)
    assert "rule:release.tag-cadence" in _rules(release)
    assert release is not None and "v0.4 to v0.5" in release["note"]
    relaxed = deep_merge(DEFAULTS, {"rules": {"release": {"gap_multiple": 30}}})
    findings, _ = run_rules(service_py[0], inventory, relaxed, now=NOW)
    assert "rule:release.tag-cadence" not in _rules(_at(findings, "pipeline-infra", None))


def test_ownership_island_and_repo_level_facts(service_py: Repo, web_ts: Repo) -> None:
    findings = _run(service_py)
    island = _at(findings, "ownership", "src/pay/refund.py")
    assert island is not None
    assert "rule:ownership.knowledge-island" in _rules(island)
    assert island["severity"] == 4  # top-5 hotspot
    assert (island["debt_type"], island["type_id"], island["effort"]) == (
        "knowledge-process", "TD-16", "M",
    )
    assert island["evidence"][0]["line_start"] is None
    assert "has left" not in island["note"]
    assert _at(findings, "ownership", "src/pay/ledger.py") is None
    repo_level = _at(findings, "ownership", None)
    assert "rule:ownership.no-codeowners" in _rules(repo_level)
    assert "rule:ownership.no-adr-no-pr-template" not in _rules(repo_level)  # ADR dir present
    assert repo_level is not None and repo_level["type_id"] == "TD-23"
    web_repo_level = _at(_run(web_ts), "ownership", None)
    assert {"rule:ownership.no-codeowners", "rule:ownership.no-adr-no-pr-template"} <= _rules(
        web_repo_level
    )
    assert web_repo_level is not None and web_repo_level["severity"] == 2


def test_ownership_suppressed_below_three_human_authors(mixed: Repo, service_py: Repo) -> None:
    assert not any(f["family"] == "ownership" for f in _run(mixed))
    strict = deep_merge(DEFAULTS, {"rules": {"ownership": {"min_human_authors": 4}}})
    assert not any(f["family"] == "ownership" for f in _run(service_py, strict))


def test_ownership_thresholds_from_config(service_py: Repo) -> None:
    for override in ({"island_share": 1.1}, {"island_max_authors": 0}):
        cfg = deep_merge(DEFAULTS, {"rules": {"ownership": override}})
        findings = _run(service_py, cfg)
        assert not any("rule:ownership.knowledge-island" in _rules(f) for f in findings)


def test_unowned_hotspot_with_codeowners(service_py: Repo, tmp_path: Path) -> None:
    repo = tmp_path / "copy"
    shutil.copytree(service_py[0], repo)
    (repo / "CODEOWNERS").write_text("src/pay/ledger.py @grace\n", encoding="utf-8")
    inventory, _ = build_all(repo, churn_months=240)
    findings, _ = run_rules(repo, inventory, DEFAULTS, now=NOW)
    unowned = _at(findings, "ownership", "CODEOWNERS")
    assert _rules(unowned) == {"rule:ownership.unowned-hotspot"}
    assert unowned is not None
    assert "src/pay/refund.py" in unowned["note"]
    assert "src/pay/ledger.py" not in unowned["note"]
    assert not any("rule:ownership.no-codeowners" in _rules(f) for f in findings)


def test_no_git_gives_only_artefact_findings(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM alpine:3.20\nRUN apk add curl\n", encoding="utf-8")
    inventory, _ = build_all(tmp_path)
    findings, leads = run_rules(tmp_path, inventory, DEFAULTS, now=NOW)
    assert [f["evidence"][0]["file"] for f in findings] == ["Dockerfile"]
    assert leads == {"migration": []}


def test_cli_writes_rule_findings(service_py: Repo, tmp_path: Path) -> None:
    from rules import _main

    workdir = tmp_path / "wd"
    write_json(workdir / "inventory.json", service_py[1])
    assert _main([str(service_py[0]), "--workdir", str(workdir)]) == 0
    raw = (workdir / "rule-findings.json").read_bytes()
    assert b"\r\n" not in raw
    document = json.loads(raw)
    assert list(document) == ["schema_version", "findings", "leads"]
    assert document["schema_version"] == 2
    assert any(f["family"] == "ownership" for f in document["findings"])
    assert document["leads"]["migration"][0]["file"] == "setup.py"


def test_cli_missing_inventory_exits_2(tmp_path: Path) -> None:
    from rules import _main

    assert _main([str(tmp_path), "--workdir", str(tmp_path / "none")]) == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest skills/tech-debt-scan/tests/test_rules.py -v`
Expected: collection error `ModuleNotFoundError: No module named 'rules'`.

- [ ] **Step 3: Write `rules.py`**

Create `skills/tech-debt-scan/scripts/rules.py`:

```python
"""Deterministic findings for pipeline-infra, dependency manifests and ownership (spec 4.4).

Each rule is a single-line fact whose quote is taken from disk or stated as
a repository fact, so rule findings skip scouts and verifier and enter the
merge as tier A candidates with ``source: "rule"``. One aggregated finding
per file (or per group for repository-level facts): the finding lists every
rule hit as evidence, carries the maximum severity, and names every rule in
``confirmed_by`` as ``rule:<group>.<rule>``.

Groups: ci (GitHub workflow jobs), container (Dockerfiles, compose and
devcontainer images), iac (Kubernetes manifests), manifest (lockfiles beside
manifests; ``setup.py`` beside ``pyproject.toml`` and ``tslint`` beside
``eslint`` are migration leads, not findings), release (tag cadence, stale
environment branches) and ownership (knowledge islands, former contributors,
CODEOWNERS coverage, stale branches, missing ADRs and PR template). Severity
is 2 to 3 for the artefact groups: 3 when a permissions or pinning gap sits
on a workflow whose file or job name matches ``release|publish|deploy``; a
dev-only container path drops one severity. Ownership runs only with git and
at least ``rules.ownership.min_human_authors`` human authors, says "no
commits in N days" and never "has left". Every threshold comes from the
``rules`` block of ``.tech-debt.yaml``.

Repository-level facts have no file: their evidence carries null file and
lines and a quote stating the fact, with ``quote_verified`` true (the shape
spec 4.5 gives osv facts). Only ``yaml.safe_load`` is used.

``python scripts/rules.py <repo> --workdir .tech-debt`` reads
``<workdir>/inventory.json`` and writes ``<workdir>/rule-findings.json`` as
``{"schema_version": 2, "findings": [...], "leads": {"migration": [...]}}``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Final

import yaml

from config import ConfigError, load_config
from inventory import write_json

SCHEMA_VERSION: Final[int] = 2

# group -> (family, debt_type, type_id, effort)
GROUP_META: Final[dict[str, tuple[str, str, str, str]]] = {
    "ci": ("pipeline-infra", "build", "TD-14", "S"),
    "container": ("pipeline-infra", "infrastructure", "TD-19", "S"),
    "iac": ("pipeline-infra", "infrastructure", "TD-19", "S"),
    "manifest": ("dependency-debt", "dependency", "TD-02", "S"),
    "release": ("pipeline-infra", "build", "TD-27", "M"),
    "ownership": ("ownership", "knowledge-process", "TD-16", "M"),
}
GROUP_LABEL: Final[dict[str, str]] = {
    "ci": "CI workflow gaps",
    "container": "Container configuration gaps",
    "iac": "Kubernetes manifest gaps",
    "manifest": "Dependency manifest gaps",
    "release": "Release process gaps",
    "ownership": "Ownership gaps",
}
# Ownership rules about process rather than knowledge concentration carry TD-23.
PROCESS_RULES: Final[frozenset[str]] = frozenset(
    {"ownership.no-codeowners", "ownership.stale-branches", "ownership.no-adr-no-pr-template"}
)

RELEASE_NAME_RE: Final[re.Pattern[str]] = re.compile(r"release|publish|deploy", re.IGNORECASE)
SHA_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
COMMENTED_JOB_RE: Final[re.Pattern[str]] = re.compile(r"^#\s*(?:runs-on|steps)\s*:")
UNVERSIONED_INSTALL_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:apt-get\s+install|apt\s+install|apk\s+add|pip3?\s+install|gem\s+install)\b"
    r"(?![^|&;]*(?:==|=\d|@\d|-r\s|--requirement|\.txt))"
)
IMAGE_LINE_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:-\s*)?[\"']?image[\"']?:\s*[\"']?([^\s\"']+)"
)
ARCHIVE_SUFFIXES: Final[tuple[str, ...]] = (".tar", ".gz", ".tgz", ".bz2", ".xz", ".zip")
DEV_ONLY_NAMES: Final[tuple[str, ...]] = ("docker-compose.dev.yml", "docker-compose.dev.yaml")
ENV_BRANCH_RE: Final[re.Pattern[str]] = re.compile(r"^(?:hotfix|release)/|^(?:prod|staging)$")
DEFAULT_BRANCHES: Final[frozenset[str]] = frozenset({"main", "master"})
LOCKFILES_FOR: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("package.json", ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "npm-shrinkwrap.json")),
    ("pyproject.toml", ("poetry.lock", "uv.lock", "pdm.lock")),
    ("go.mod", ("go.sum",)),
    ("Cargo.toml", ("Cargo.lock",)),
    ("Gemfile", ("Gemfile.lock",)),
    ("*.csproj", ("packages.lock.json",)),
    ("build.gradle*", ("gradle.lockfile",)),
)
ESLINT_NAMES: Final[tuple[str, ...]] = (
    ".eslintrc", ".eslintrc.json", ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.yml",
    ".eslintrc.yaml", "eslint.config.js", "eslint.config.mjs", "eslint.config.cjs",
)


@dataclass(slots=True)
class Hit:
    rule_id: str
    file: str | None
    line: int | None
    quote: str
    note: str
    severity: int


def fingerprint(family: str, path: str, quote: str) -> tuple[str, str]:
    """Spec 4.7: sha1(family|path|sha1(normalised quote))[:16] and the inner hash."""
    normalised = " ".join(quote.split())
    quote_hash = hashlib.sha1(normalised.encode("utf-8")).hexdigest()
    outer = hashlib.sha1(f"{family}|{path}|{quote_hash}".encode()).hexdigest()
    return outer[:16], quote_hash


def _parse_date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _read(root: Path, rel: str) -> str:
    try:
        return (root / rel).read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _find_line(lines: list[str], pattern: str) -> int | None:
    regex = re.compile(pattern)
    for index, line in enumerate(lines, start=1):
        if regex.search(line):
            return index
    return None


def _image_is_latest(image: str) -> bool:
    if "@" in image or image.startswith("$"):
        return False
    tail = image.rsplit("/", 1)[-1]
    return ":" not in tail or image.endswith(":latest")


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _dirname(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else ""


def _join(directory: str, name: str) -> str:
    return f"{directory}/{name}" if directory else name


# --- ci -------------------------------------------------------------------------


def _job_hits(path: str, name: str, job: dict[str, Any], lines: list[str], *,
              top_permissions: bool, release_file: bool) -> list[Hit]:
    hits: list[Hit] = []
    job_line = _find_line(lines, rf"^\s*{re.escape(name)}:\s*$") or 1
    job_quote = lines[job_line - 1].strip()
    release = release_file or RELEASE_NAME_RE.search(name) is not None
    gap_severity = 3 if release else 2
    if "timeout-minutes" not in job:
        hits.append(Hit("ci.no-timeout", path, job_line, job_quote,
                        f"job {name} has no timeout-minutes", 2))
    if not top_permissions and "permissions" not in job:
        hits.append(Hit("ci.no-permissions", path, job_line, job_quote,
                        f"job {name} has no permissions block", gap_severity))
    if job.get("continue-on-error") is True:
        line = _find_line(lines, r"continue-on-error:\s*true") or job_line
        hits.append(Hit("ci.continue-on-error", path, line, lines[line - 1].strip(),
                        f"job {name} continues on error", 2))
    runs_on = job.get("runs-on")
    if isinstance(runs_on, str) and runs_on.endswith("-latest"):
        line = _find_line(lines, rf"runs-on:\s*{re.escape(runs_on)}") or job_line
        hits.append(Hit("ci.mutable-runner", path, line, lines[line - 1].strip(),
                        f"job {name} runs on the mutable label {runs_on}", 2))
    has_cache = False
    steps = job.get("steps") if isinstance(job.get("steps"), list) else []
    for step in steps:
        if not isinstance(step, dict):
            continue
        uses = step.get("uses")
        if isinstance(uses, str):
            if "actions/cache" in uses:
                has_cache = True
            ref = uses.rsplit("@", 1)[1] if "@" in uses else ""
            if not uses.startswith(("./", "docker://")) and not SHA_RE.match(ref):
                line = _find_line(lines, rf"uses:\s*{re.escape(uses)}") or job_line
                hits.append(Hit("ci.unpinned-action", path, line, lines[line - 1].strip(),
                                f"{uses} is not pinned to a commit SHA", gap_severity))
        with_block = step.get("with")
        if isinstance(with_block, dict) and "cache" in with_block:
            has_cache = True
    if not has_cache:
        hits.append(Hit("ci.no-cache", path, job_line, job_quote,
                        f"job {name} has no cache step", 2))
    return hits


def _ci_hits(path: str, text: str) -> list[Hit]:
    lines = text.splitlines()
    hits: list[Hit] = []
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:
        doc = None
    jobs = doc.get("jobs") if isinstance(doc, dict) else None
    if ".github/workflows/" in path and isinstance(doc, dict) and isinstance(jobs, dict):
        release_file = RELEASE_NAME_RE.search(_basename(path)) is not None
        for name, job in jobs.items():
            if isinstance(job, dict):
                hits.extend(_job_hits(path, str(name), job, lines,
                                      top_permissions="permissions" in doc,
                                      release_file=release_file))
    for index, line in enumerate(lines, start=1):
        if COMMENTED_JOB_RE.match(line.strip()):
            hits.append(Hit("ci.commented-job", path, index, line.strip(),
                            "commented-out job block", 2))
            break
    return hits


# --- container ------------------------------------------------------------------


def _dockerfile_hits(path: str, lines: list[str]) -> list[Hit]:
    hits: list[Hit] = []
    stages: set[str] = set()
    pipefail = False
    has_user = False
    from_line: int | None = None
    for index, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        upper = line.upper()
        if upper.startswith("FROM "):
            from_line = from_line or index
            parts = line.split()
            image = parts[1] if len(parts) > 1 else ""
            if len(parts) >= 4 and parts[2].upper() == "AS":
                stages.add(parts[3])
            is_stage = image in stages or image == "scratch"
            if image and not is_stage and _image_is_latest(image):
                hits.append(Hit("container.untagged-base", path, index, line,
                                f"base image {image} is untagged or latest", 2))
        elif upper.startswith("SHELL ") and "pipefail" in line:
            pipefail = True
        elif upper.startswith("USER "):
            has_user = True
        elif upper.startswith("RUN "):
            if UNVERSIONED_INSTALL_RE.search(line):
                hits.append(Hit("container.unversioned-install", path, index, line,
                                "package install without a version pin", 2))
            if "|" in line and not pipefail:
                hits.append(Hit("container.no-pipefail", path, index, line,
                                "piped RUN without pipefail", 2))
        elif upper.startswith("ADD "):
            parts = line.split()
            source = parts[1] if len(parts) > 1 else ""
            remote = source.startswith(("http://", "https://"))
            if not remote and not source.endswith(ARCHIVE_SUFFIXES):
                hits.append(Hit("container.add-local", path, index, line,
                                "ADD used for a local file; COPY is explicit", 2))
    if from_line is not None and not has_user:
        hits.append(Hit("container.no-user", path, from_line, lines[from_line - 1].strip(),
                        "no USER instruction; the container runs as root", 2))
    return hits


def _container_hits(path: str, text: str) -> list[Hit]:
    lines = text.splitlines()
    name = _basename(path)
    if name.startswith("Dockerfile") or name.endswith(".dockerfile"):
        hits = _dockerfile_hits(path, lines)
    else:
        hits = []
        for index, raw in enumerate(lines, start=1):
            match = IMAGE_LINE_RE.match(raw)
            if match and _image_is_latest(match.group(1)):
                hits.append(Hit("container.latest-image", path, index, raw.strip(),
                                f"image {match.group(1)} is untagged or latest", 2))
    if name in DEV_ONLY_NAMES or ".devcontainer/" in path:
        for hit in hits:
            hit.severity = max(1, hit.severity - 1)
    return hits


# --- iac ------------------------------------------------------------------------


def _containers(node: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("containers", "initContainers") and isinstance(value, list):
                found.extend(item for item in value if isinstance(item, dict))
            else:
                found.extend(_containers(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_containers(item))
    return found


def _iac_hits(path: str, text: str) -> list[Hit]:
    if not path.lower().endswith((".yml", ".yaml")):
        return []
    try:
        docs = list(yaml.safe_load_all(text))
    except yaml.YAMLError:
        return []
    lines = text.splitlines()
    hits: list[Hit] = []
    for doc in docs:
        if not isinstance(doc, dict) or "kind" not in doc:
            continue
        for container in _containers(doc):
            cname = str(container.get("name", "container"))
            line = _find_line(lines, rf"-\s*name:\s*{re.escape(cname)}\b") or 1
            resources = container.get("resources")
            if not (isinstance(resources, dict) and isinstance(resources.get("limits"), dict)):
                hits.append(Hit("iac.no-resource-limits", path, line, lines[line - 1].strip(),
                                f"container {cname} has no resources.limits", 2))
            image = container.get("image")
            if isinstance(image, str) and _image_is_latest(image):
                img_line = _find_line(lines, rf"image:\s*{re.escape(image)}") or line
                hits.append(Hit("iac.latest-image", path, img_line, lines[img_line - 1].strip(),
                                f"container {cname} uses {image}", 2))
            context = container.get("securityContext")
            if isinstance(context, dict) and context.get("privileged") is True:
                priv = _find_line(lines, r"privileged:\s*true") or line
                hits.append(Hit("iac.privileged", path, priv, lines[priv - 1].strip(),
                                f"container {cname} is privileged", 2))
    return hits


# --- manifest -------------------------------------------------------------------


def _expected_lockfiles(name: str) -> tuple[str, ...]:
    for pattern, locks in LOCKFILES_FOR:
        if fnmatchcase(name, pattern):
            return locks
    return ()


def _manifest_hits(
    root: Path, inventory: dict[str, Any]
) -> tuple[dict[str, list[Hit]], list[dict[str, Any]]]:
    artefacts = inventory.get("artefacts") or {}
    lockfiles = {str(a["path"]) for a in artefacts.get("lockfile", [])}
    manifests = [str(a["path"]) for a in artefacts.get("manifest", [])]
    configs = {str(a["path"]) for a in artefacts.get("config", [])}
    files = {str(e["path"]): e for e in inventory["files"]}
    hits: dict[str, list[Hit]] = {}
    for rel in manifests:
        name = _basename(rel)
        expected = _expected_lockfiles(name)
        if not expected:
            continue
        directory = _dirname(rel)
        present = [lock for lock in expected if _join(directory, lock) in lockfiles]
        quote = _first_line(_read(root, rel))
        if not present:
            hits.setdefault(rel, []).append(Hit(
                "manifest.no-lockfile", rel, 1, quote,
                f"no lockfile ({', '.join(expected)}) beside {name}", 2,
            ))
        elif len(present) >= 2:
            hits.setdefault(rel, []).append(Hit(
                "manifest.two-lockfiles", rel, 1, quote,
                f"two lockfile kinds beside {name}: {', '.join(present)}", 2,
            ))
    leads: list[dict[str, Any]] = []
    for rel in manifests:
        if _basename(rel) != "pyproject.toml":
            continue
        setup = _join(_dirname(rel), "setup.py")
        if setup in files:
            leads.append({
                "rule": "dual-manifest", "file": setup, "line": 1,
                "quote": _first_line(_read(root, setup)),
                "path_class": str(files[setup]["path_class"]),
                "extra": {"pair": [setup, rel]},
            })
    for rel in sorted(configs):
        if _basename(rel) != "tslint.json":
            continue
        directory = _dirname(rel)
        candidates = [_join(directory, n) for n in ESLINT_NAMES]
        eslint = next((c for c in candidates if c in configs or (root / c).is_file()), None)
        if eslint is not None:
            leads.append({
                "rule": "dual-manifest", "file": rel, "line": 1,
                "quote": _first_line(_read(root, rel)), "path_class": "config",
                "extra": {"pair": [rel, eslint]},
            })
    return hits, leads


# --- release --------------------------------------------------------------------


def _release_hits(inventory: dict[str, Any], config: dict[str, Any], now: datetime) -> list[Hit]:
    release_cfg = config["rules"]["release"]
    git = inventory.get("git") or {}
    hits: list[Hit] = []
    tags = [t for t in git.get("tags", []) if _parse_date(t.get("date")) is not None]
    if len(tags) >= int(release_cfg["min_tags"]):
        dates = [_parse_date(t["date"]) for t in tags]
        gaps = [(b - a).days for a, b in zip(dates, dates[1:], strict=True) if a and b]
        if gaps:
            median = statistics.median(gaps)
            longest = max(gaps)
            if median > 0 and longest > float(release_cfg["gap_multiple"]) * median:
                at = gaps.index(longest)
                hits.append(Hit(
                    "release.tag-cadence", None, None,
                    f"{len(tags)} tags, median gap {median:.0f} days, longest gap {longest} days",
                    f"irregular release cadence ({tags[at]['name']} to {tags[at + 1]['name']})", 2,
                ))
    stale_days = int(release_cfg["stale_branch_days"])
    for branch in git.get("branches", []):
        name = str(branch.get("name", ""))
        local = str(branch.get("ref", "")).startswith("refs/heads/")
        if not local or not ENV_BRANCH_RE.match(name) or branch.get("merged") is not False:
            continue
        last = _parse_date(branch.get("last_commit"))
        if last is None:
            continue
        age = (now - last).days
        if age >= stale_days:
            when = str(branch["last_commit"])[:10]
            hits.append(Hit(
                "release.stale-env-branch", None, None,
                f"branch {name} unmerged, last commit {when} ({age} days ago)",
                "long-lived environment branch", 2,
            ))
    return hits


# --- ownership ------------------------------------------------------------------


def _codeowners_match(path: str, pattern: str) -> bool:
    pattern = pattern.strip()
    if pattern in ("*", "**"):
        return True
    anchored = pattern.startswith("/")
    pattern = pattern.lstrip("/")
    if pattern.endswith("/"):
        return path.startswith(pattern) or (not anchored and f"/{pattern}" in f"/{path}")
    if "/" in pattern:
        if fnmatchcase(path, pattern) or path.startswith(pattern + "/"):
            return True
        return not anchored and fnmatchcase(path, "*/" + pattern)
    return fnmatchcase(_basename(path), pattern) or fnmatchcase(path, pattern)


def _codeowners_patterns(text: str) -> list[str]:
    patterns: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            patterns.append(line.split()[0])
    return patterns


def _band_hits(
    inventory: dict[str, Any], own: dict[str, Any], now: datetime
) -> list[Hit]:
    files = {str(e["path"]): e for e in inventory["files"]}
    top5 = [str(h["path"]) for h in inventory.get("hotspots", [])[:5]]
    humans = (inventory.get("git") or {}).get("authors", [])
    last_active = {str(a["email"]): _parse_date(a.get("last_active")) for a in humans}
    hits: list[Hit] = []
    for path in [str(p) for p in inventory.get("hotspot_band", [])]:
        entry = files.get(path)
        if entry is None:
            continue
        share = entry.get("top_author_line_share")
        authors = entry.get("authors")
        island = (
            isinstance(share, float)
            and isinstance(authors, int)
            and share >= float(own["island_share"])
            and authors <= int(own["island_max_authors"])
        )
        if island:
            hits.append(Hit(
                "ownership.knowledge-island", path, None,
                f"{path}: {share:.0%} of lines by one author, {authors} author(s) in the window",
                "knowledge island on a hotspot-band file", 4 if path in top5 else 3,
            ))
        top = entry.get("top_author")
        active = last_active.get(str(top)) if top else None
        if active is not None and (now - active).days > int(own["inactive_days"]):
            idle = (now - active).days
            hits.append(Hit(
                "ownership.former-contributor", path, None,
                f"{path}: top author has no commits in {idle} days",
                "hotspot whose top author is inactive", 2,
            ))
    return hits


def _ownership_hits(
    root: Path, inventory: dict[str, Any], config: dict[str, Any], now: datetime
) -> list[Hit]:
    own = config["rules"]["ownership"]
    git = inventory.get("git") or {}
    humans = git.get("authors", [])
    if not inventory.get("git_available") or len(humans) < int(own["min_human_authors"]):
        return []
    hits = _band_hits(inventory, own, now)
    band = [str(p) for p in inventory.get("hotspot_band", [])]
    governance = (inventory.get("artefacts") or {}).get("governance", [])
    codeowners = next(
        (str(a["path"]) for a in governance if _basename(str(a["path"])) == "CODEOWNERS"), None
    )
    if codeowners is not None:
        patterns = _codeowners_patterns(_read(root, codeowners))
        unowned = [p for p in band if not any(_codeowners_match(p, pat) for pat in patterns)]
        if unowned:
            listed = ", ".join(unowned)
            hits.append(Hit(
                "ownership.unowned-hotspot", codeowners, 1, _first_line(_read(root, codeowners)),
                f"{len(unowned)} hotspot-band file(s) match no CODEOWNERS rule: {listed}", 2,
            ))
    else:
        hits.append(Hit(
            "ownership.no-codeowners", None, None,
            f"no CODEOWNERS file with {len(humans)} human authors", "no ownership map", 2,
        ))
    stale_days = int(config["rules"]["release"]["stale_branch_days"])
    stale = 0
    for branch in git.get("branches", []):
        name = str(branch.get("name", ""))
        local = str(branch.get("ref", "")).startswith("refs/heads/")
        if not local or name in DEFAULT_BRANCHES or branch.get("merged") is not False:
            continue
        last = _parse_date(branch.get("last_commit"))
        if last is not None and (now - last).days >= stale_days:
            stale += 1
    if stale > int(own["max_stale_branches"]):
        hits.append(Hit(
            "ownership.stale-branches", None, None,
            f"{stale} unmerged branches older than {stale_days} days", "branch hygiene", 2,
        ))
    docs = inventory.get("docs") or {}
    has_template = any(
        _basename(str(a["path"])).startswith("PULL_REQUEST_TEMPLATE") for a in governance
    )
    if not docs.get("adr_dir_present") and not has_template:
        hits.append(Hit(
            "ownership.no-adr-no-pr-template", None, None,
            "no ADR directory and no pull request template", "decision and review process", 1,
        ))
    return hits


# --- assembly -------------------------------------------------------------------


def _signals(inventory: dict[str, Any], path: str | None) -> dict[str, Any]:
    signals: dict[str, Any] = {
        "hotspot_score": 0.0, "churn": 0, "coupling_degree": 0, "fan_in_approx": None,
        "path_class": None, "in_hotspot_band": False,
    }
    if path is None:
        return signals
    for entry in inventory["files"]:
        if entry["path"] == path:
            signals["hotspot_score"] = entry["hotspot_score"]
            signals["churn"] = entry["churn"]
            signals["coupling_degree"] = entry["coupling_degree"]
            signals["fan_in_approx"] = entry["fan_in_approx"]
            signals["path_class"] = entry["path_class"]
            signals["in_hotspot_band"] = path in inventory.get("hotspot_band", [])
            return signals
    for cls, entries in (inventory.get("artefacts") or {}).items():
        for artefact in entries:
            if artefact["path"] == path:
                signals["churn"] = artefact["churn"]
                signals["path_class"] = cls
                return signals
    return signals


def _candidate(
    group: str, path: str | None, hits: list[Hit], inventory: dict[str, Any]
) -> dict[str, Any]:
    family, debt_type, type_id, effort = GROUP_META[group]
    if group == "ownership" and all(h.rule_id in PROCESS_RULES for h in hits):
        type_id = "TD-23"
    primary = max(hits, key=lambda h: (h.severity, -hits.index(h)))
    fp, quote_hash = fingerprint(family, path or "", primary.quote)
    label = GROUP_LABEL[group]
    title = f"{label} in {path}" if path else label
    return {
        "fingerprint": fp,
        "quote_hash": quote_hash,
        "family": family,
        "debt_type": debt_type,
        "type_id": type_id,
        "title": title[:80],
        "severity": max(h.severity for h in hits),
        "effort": effort,
        "source": "rule",
        "rule_id": primary.rule_id,
        "note": "; ".join(h.note for h in hits)[:300],
        "evidence": [
            {"file": h.file, "line_start": h.line, "line_end": h.line, "quote": h.quote,
             "quote_verified": True}
            for h in hits
        ],
        "confirmed_by": sorted({f"rule:{h.rule_id}" for h in hits}),
        "signals_cited": [],
        "signals": _signals(inventory, path),
        "tier": "A",
    }


def run_rules(
    root: Path,
    inventory: dict[str, Any],
    config: dict[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """Return (rule findings in the 4.7 candidate schema, migration leads)."""
    root = root.resolve()
    current = now or datetime.now(UTC)
    artefacts = inventory.get("artefacts") or {}
    grouped: list[tuple[str, str | None, list[Hit]]] = []
    scanners = (("ci", _ci_hits), ("container", _container_hits), ("iac", _iac_hits))
    for group, scanner in scanners:
        for artefact in artefacts.get(group, []):
            rel = str(artefact["path"])
            hits = scanner(rel, _read(root, rel))
            if hits:
                grouped.append((group, rel, hits))
    manifest_hits, migration_leads = _manifest_hits(root, inventory)
    for rel, hits in manifest_hits.items():
        grouped.append(("manifest", rel, hits))
    release_hits = _release_hits(inventory, config, current)
    if release_hits:
        grouped.append(("release", None, release_hits))
    ownership: dict[str | None, list[Hit]] = {}
    for hit in _ownership_hits(root, inventory, config, current):
        ownership.setdefault(hit.file, []).append(hit)
    for path, hits in ownership.items():
        grouped.append(("ownership", path, hits))
    findings = [_candidate(group, path, hits, inventory) for group, path, hits in grouped]
    return findings, {"migration": migration_leads}


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit deterministic rule findings")
    parser.add_argument("path", help="repo root to scan")
    parser.add_argument(
        "--workdir",
        default=".tech-debt",
        help="directory holding inventory.json (default .tech-debt)",
    )
    args = parser.parse_args(argv)
    root = Path(args.path)
    workdir = Path(args.workdir)
    inventory_path = workdir / "inventory.json"
    if not inventory_path.is_file():
        print(f"error: {inventory_path} not found; run inventory.py first", file=sys.stderr)
        return 2
    try:
        inventory = json.loads(inventory_path.read_bytes())
        cfg = load_config(root)
        findings, leads = run_rules(root, inventory, cfg)
    except (OSError, ValueError, ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    out_path = workdir / "rule-findings.json"
    document = {"schema_version": SCHEMA_VERSION, "findings": findings, "leads": leads}
    write_json(out_path, document)
    print(f"wrote {out_path} ({len(findings)} findings, {len(leads['migration'])} migration leads)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest skills/tech-debt-scan/tests/test_rules.py -v`
Expected: 17 passed (14 functions, the stale-branch case expands to 3).

- [ ] **Step 5: Lint, type-check, whole suite, commit**

Run: `ruff check . && mypy && pytest -q`
Expected: clean; every test passing.

```bash
git add skills/tech-debt-scan/scripts/rules.py skills/tech-debt-scan/tests/test_rules.py
git commit -m "feat(tech-debt-scan): rules.py findings for CI, containers, IaC, manifests, release and ownership"
```

---

### Task 12: `evaluate.py` (score findings against `planted.json`)

**Files:**
- Create: `skills/tech-debt-scan/scripts/evaluate.py`
- Create: `skills/tech-debt-scan/tests/test_evaluate.py`

**Interfaces:**
- Consumes: `write_json` (Task 9) in the test only; `CORPUS_ROOT` from `make_history.py` (Task 3) for the corpus `planted.json`; the candidate shape from Task 11 (`family`, `evidence[{file, line_start, line_end}]`, `tier`, `fingerprint`).
- Produces (used by Task 13's docs, phase 2's golden checks and the phase 5 live harness):
  - `SCHEMA_VERSION = 2`, `REPORTED_TIERS = ("A", "B")`
  - `def load_findings(workdir: Path) -> tuple[list[dict[str, Any]], str]` (`findings.json` when present, else `verified.json`; accepts a list or an object holding `findings` or `candidates`; returns the list and the file name used)
  - `def load_top_n(workdir: Path) -> set[str]` (fingerprints in `ranked.json`'s `top_n`, empty when absent)
  - `def hits(finding: dict[str, Any], item: dict[str, Any]) -> bool` (same family; same evidence file, `null` path matching `null` evidence; line ranges overlap when the item has a non-zero range and the evidence has lines)
  - `def evaluate(findings, planted_doc, top_n, *, top: int = 5) -> dict[str, Any]`
  - `def render_table(report: dict[str, Any]) -> str`
  - CLI `python scripts/evaluate.py --planted <planted.json> --workdir <dir> [--top N] [--json]`

**Spec:** 6 (`evaluate.py` scores `verified.json`, `ranked.json` or `findings.json` against `planted.json`: per-family precision, recall and decoy hits by tier, and whether any decoy sits in the top N; runs in CI over canned goldens and in the live run over real output; "zero decoys in tier A or the top N" is the hard bar from v2.0), 1 success criterion 2.

**Decisions the spec leaves open, fixed here:** a finding is "reported" when its tier is A or B (tier C is listed for a human, never reported, per 4.8); precision for a family is reported findings that hit a planted item over all reported findings in that family; recall is planted items hit by at least one reported finding over planted items; decoy hits count every tier, since a decoy at tier C still says something about the scouts; `tier_met` is true when the best tier among the hitting findings is at least the item's `expect_tier`; a reported finding that hits neither a planted item nor a decoy is counted as `unplanted`; a decoy or planted item with `lines` `[0, 0]` or without `lines` matches on family and path alone; an evidence item with null lines matches any range in its file. The report never fails the process: the bar check belongs to the phase 5 live harness, which reads `decoys_in_tier_a` and `decoys_in_top_n`.

**Confidence:** 95% (pure JSON arithmetic driven by a hand-written `verified.json`).

- [ ] **Step 1: Write the failing tests**

Create `skills/tech-debt-scan/tests/test_evaluate.py`:

```python
"""evaluate.py: precision, recall, decoy tiers and top-N decoys against planted.json (spec 6)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from evaluate import evaluate, hits, load_findings, render_table
from inventory import write_json
from make_history import CORPUS_ROOT


def _finding(
    family: str,
    file: str | None,
    start: int | None,
    end: int | None,
    tier: str,
    fingerprint: str,
) -> dict[str, Any]:
    return {
        "fingerprint": fingerprint,
        "family": family,
        "tier": tier,
        "evidence": [{"file": file, "line_start": start, "line_end": end, "quote": "q",
                      "quote_verified": True}],
    }


# A hand-written verified.json for service-py: six planted hits, two reported decoy hits,
# one unplanted finding and one tier-C decoy hit that is never "reported".
VERIFIED: list[dict[str, Any]] = [
    _finding("error-masking", "src/pay/refund.py", 31, 34, "A", "f01"),  # p1
    _finding("half-finished", "src/pay/refund.py", 35, 35, "B", "f02"),  # p2
    _finding("security", "src/pay/gateway.py", 11, 11, "B", "f03"),  # p3
    _finding("security", "tests/fixtures/seed.py", 2, 2, "C", "f04"),  # decoy d2, unreported
    _finding("duplication", "tests/fixtures/seed.py", 4, 5, "B", "f05"),  # decoy d1
    _finding("dead-code", "src/pay/__init__.py", 1, 1, "A", "f06"),  # decoy d4 at tier A
    _finding("pipeline-infra", "Dockerfile", 1, 1, "A", "f07"),  # p8
    _finding("ownership", "src/pay/refund.py", None, None, "A", "f08"),  # p7, file-level
    _finding("pipeline-infra", None, None, None, "A", "f09"),  # p19, repository-level
    _finding("security", "src/pay/gateway.py", 26, 26, "B", "f10"),  # unplanted
]
RANKED = {"schema_version": 2, "top_n": ["f01", "f06", "f07", "f08", "f09"]}


@pytest.fixture
def planted() -> dict[str, Any]:
    path = CORPUS_ROOT / "service-py" / "planted.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_hits_matches_family_file_and_overlap() -> None:
    item = {"family": "security", "path": "src/pay/gateway.py", "lines": [20, 25]}
    assert hits(_finding("security", "src/pay/gateway.py", 24, 24, "B", "x"), item)
    assert hits(_finding("security", "src/pay/gateway.py", 18, 21, "B", "x"), item)
    assert not hits(_finding("security", "src/pay/gateway.py", 26, 26, "B", "x"), item)
    assert not hits(_finding("half-finished", "src/pay/gateway.py", 24, 24, "B", "x"), item)
    assert hits(_finding("security", "src/pay/gateway.py", None, None, "B", "x"), item)
    repo_level = {"family": "pipeline-infra", "path": None, "lines": [0, 0]}
    assert hits(_finding("pipeline-infra", None, None, None, "A", "x"), repo_level)
    assert not hits(_finding("pipeline-infra", "Dockerfile", 1, 1, "A", "x"), repo_level)
    no_lines = {"family": "duplication", "path": "tests/fixtures/seed.py"}
    assert hits(_finding("duplication", "tests/fixtures/seed.py", 9, 9, "B", "x"), no_lines)


def test_evaluate_per_family_precision_recall_and_decoys(planted: dict[str, Any]) -> None:
    report = evaluate(VERIFIED, planted, set(RANKED["top_n"]), top=5)
    families = report["families"]
    assert families["error-masking"] == {
        "planted": 1, "found": 1, "recall": 1.0, "reported": 1, "precise": 1, "precision": 1.0,
        "decoy_hits": {"A": 0, "B": 0, "C": 0},
    }
    security = families["security"]
    assert (security["planted"], security["found"], security["recall"]) == (5, 1, 0.2)
    assert (security["reported"], security["precise"], security["precision"]) == (2, 1, 0.5)
    assert security["decoy_hits"] == {"A": 0, "B": 0, "C": 1}
    assert families["dead-code"]["precision"] == 0.0
    assert families["dead-code"]["decoy_hits"] == {"A": 1, "B": 0, "C": 0}
    assert families["duplication"]["planted"] == 0
    assert families["duplication"]["recall"] is None
    assert families["duplication"]["decoy_hits"]["B"] == 1
    assert (families["pipeline-infra"]["found"], families["pipeline-infra"]["planted"]) == (2, 4)
    assert families["pipeline-infra"]["precision"] == 1.0
    assert families["ownership"]["recall"] == 1.0
    assert families["test-gaps"] == {
        "planted": 1, "found": 0, "recall": 0.0, "reported": 0, "precise": 0, "precision": None,
        "decoy_hits": {"A": 0, "B": 0, "C": 0},
    }
    by_id = {item["id"]: item for item in report["planted"]}
    assert by_id["p1"] == {"id": "p1", "family": "error-masking", "found": True,
                           "tiers": ["A"], "tier_met": True}
    assert by_id["p4"]["found"] is False
    assert by_id["p19"]["found"] is True
    decoys = {item["id"]: item for item in report["decoys"]}
    assert decoys["d4"] == {"id": "d4", "family": "dead-code", "hit_tiers": ["A"],
                            "in_top_n": True}
    assert decoys["d1"]["hit_tiers"] == ["B"] and decoys["d1"]["in_top_n"] is False
    assert decoys["d2"]["hit_tiers"] == ["C"]
    assert report["decoys_in_tier_a"] == 1
    assert report["decoys_in_top_n"] == 1
    assert report["counts"] == {"reported": 9, "on_planted": 6, "on_decoys": 2, "unplanted": 1}
    assert report["top"] == 5
    assert report["schema_version"] == 2


def test_tier_met_uses_the_best_hitting_tier(planted: dict[str, Any]) -> None:
    findings = [
        _finding("error-masking", "src/pay/refund.py", 31, 34, "C", "a"),
        _finding("error-masking", "src/pay/refund.py", 32, 33, "B", "b"),
    ]
    report = evaluate(findings, planted, set(), top=5)
    p1 = next(item for item in report["planted"] if item["id"] == "p1")
    assert p1["found"] is True
    assert p1["tiers"] == ["B", "C"]
    assert p1["tier_met"] is False  # expect_tier A, best tier B


def test_load_findings_prefers_findings_json_and_accepts_shapes(tmp_path: Path) -> None:
    write_json(tmp_path / "verified.json", {"candidates": VERIFIED})
    findings, source = load_findings(tmp_path)
    assert source == "verified.json" and len(findings) == 10
    write_json(tmp_path / "findings.json", {"findings": VERIFIED[:3]})
    findings, source = load_findings(tmp_path)
    assert source == "findings.json" and len(findings) == 3
    (tmp_path / "findings.json").write_bytes(json.dumps(VERIFIED[:2]).encode("utf-8"))
    findings, _ = load_findings(tmp_path)
    assert len(findings) == 2


def test_render_table_and_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from evaluate import _main

    workdir = tmp_path / "wd"
    write_json(workdir / "verified.json", {"candidates": VERIFIED})
    write_json(workdir / "ranked.json", RANKED)
    planted_path = CORPUS_ROOT / "service-py" / "planted.json"
    assert _main(["--planted", str(planted_path), "--workdir", str(workdir)]) == 0
    out = capsys.readouterr().out
    assert "error-masking" in out and "decoys in tier A: 1" in out and "decoys in top 5: 1" in out
    assert _main(["--planted", str(planted_path), "--workdir", str(workdir), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["source"] == "verified.json"
    assert report["decoys_in_top_n"] == 1
    table = render_table(report)
    assert table.splitlines()[0].startswith("family")


def test_cli_missing_inputs_exit_2(tmp_path: Path) -> None:
    from evaluate import _main

    planted_path = CORPUS_ROOT / "service-py" / "planted.json"
    assert _main(["--planted", str(planted_path), "--workdir", str(tmp_path)]) == 2
    write_json(tmp_path / "verified.json", {"candidates": []})
    assert _main(["--planted", str(tmp_path / "none.json"), "--workdir", str(tmp_path)]) == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest skills/tech-debt-scan/tests/test_evaluate.py -v`
Expected: collection error `ModuleNotFoundError: No module named 'evaluate'`.

- [ ] **Step 3: Write `evaluate.py`**

Create `skills/tech-debt-scan/scripts/evaluate.py`:

```python
"""Score scan output against a fixture's ``planted.json`` (spec 6).

Reads ``findings.json`` (preferred) or ``verified.json`` from the workdir,
plus ``ranked.json`` when present for top-N membership, and reports per
family: planted items found (recall), reported findings that hit a planted
item (precision), and decoy hits by tier; plus whether any decoy sits in
tier A or in the top N, which are the hard release bars from v2.0. A finding
is "reported" when its tier is A or B; tier C is listed for a human and never
counts toward precision or recall.

A finding hits a planted item or decoy when the families match and one
evidence item names the same file (a null path matches a repository-level
finding with null evidence) and, when the item carries a non-zero line range
and the evidence carries lines, the ranges overlap. The report never fails
the process; the phase 5 live harness reads the counts.

``python scripts/evaluate.py --planted <planted.json> --workdir <dir> [--top N] [--json]``
prints a table, or the JSON report with ``--json``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Final

SCHEMA_VERSION: Final[int] = 2
REPORTED_TIERS: Final[tuple[str, ...]] = ("A", "B")
TIER_RANK: Final[dict[str, int]] = {"A": 0, "B": 1, "C": 2}


def _as_list(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        return [item for item in document if isinstance(item, dict)]
    if isinstance(document, dict):
        for key in ("findings", "candidates"):
            if isinstance(document.get(key), list):
                return [item for item in document[key] if isinstance(item, dict)]
    return []


def load_findings(workdir: Path) -> tuple[list[dict[str, Any]], str]:
    """(findings, file name used): findings.json when present, else verified.json."""
    for name in ("findings.json", "verified.json"):
        path = workdir / name
        if path.is_file():
            return _as_list(json.loads(path.read_bytes())), name
    raise FileNotFoundError(f"neither findings.json nor verified.json in {workdir}")


def load_top_n(workdir: Path) -> set[str]:
    path = workdir / "ranked.json"
    if not path.is_file():
        return set()
    document = json.loads(path.read_bytes())
    top = document.get("top_n") if isinstance(document, dict) else None
    return {str(fp) for fp in top} if isinstance(top, list) else set()


def _ranges_overlap(start: int, end: int, lines: list[int]) -> bool:
    return not (end < lines[0] or start > lines[1])


def hits(finding: dict[str, Any], item: dict[str, Any]) -> bool:
    """True when ``finding`` points at the planted item or decoy ``item``."""
    if finding.get("family") != item.get("family"):
        return False
    path = item.get("path")
    lines = item.get("lines")
    ranged = isinstance(lines, list) and len(lines) == 2 and lines != [0, 0]
    for evidence in finding.get("evidence") or []:
        if evidence.get("file") != path:
            continue
        if path is None or not ranged:
            return True
        start = evidence.get("line_start")
        if start is None:
            return True
        end = evidence.get("line_end")
        end = start if end is None else end
        if _ranges_overlap(int(start), int(end), [int(lines[0]), int(lines[1])]):
            return True
    return False


def _ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 3) if whole else None


def evaluate(
    findings: list[dict[str, Any]],
    planted_doc: dict[str, Any],
    top_n: set[str],
    *,
    top: int = 5,
) -> dict[str, Any]:
    planted = [p for p in planted_doc.get("planted", []) if isinstance(p, dict)]
    decoys = [d for d in planted_doc.get("decoys", []) if isinstance(d, dict)]
    reported = [f for f in findings if f.get("tier") in REPORTED_TIERS]
    families = sorted(
        {str(p["family"]) for p in planted}
        | {str(d["family"]) for d in decoys}
        | {str(f.get("family")) for f in findings}
    )

    planted_report: list[dict[str, Any]] = []
    for item in planted:
        tiers = sorted(
            (str(f.get("tier")) for f in findings if hits(f, item)),
            key=lambda t: TIER_RANK.get(t, 9),
        )
        found = any(hits(f, item) for f in reported)
        expect = TIER_RANK.get(str(item.get("expect_tier", "A")), 0)
        best = TIER_RANK.get(tiers[0], 9) if tiers else 9
        planted_report.append({
            "id": item.get("id"), "family": item.get("family"), "found": found,
            "tiers": tiers, "tier_met": found and best <= expect,
        })
    decoy_report: list[dict[str, Any]] = []
    for item in decoys:
        hitting = [f for f in findings if hits(f, item)]
        decoy_report.append({
            "id": item.get("id"), "family": item.get("family"),
            "hit_tiers": sorted((str(f.get("tier")) for f in hitting),
                                key=lambda t: TIER_RANK.get(t, 9)),
            "in_top_n": any(str(f.get("fingerprint")) in top_n or f.get("in_top_n") is True
                            for f in hitting),
        })

    per_family: dict[str, dict[str, Any]] = {}
    for family in families:
        fam_planted = [p for p in planted if p.get("family") == family]
        fam_reported = [f for f in reported if f.get("family") == family]
        found = sum(1 for p in fam_planted if any(hits(f, p) for f in fam_reported))
        precise = sum(1 for f in fam_reported if any(hits(f, p) for p in fam_planted))
        decoy_hits = {tier: 0 for tier in ("A", "B", "C")}
        for f in findings:
            if f.get("family") != family:
                continue
            tier = str(f.get("tier"))
            if tier in decoy_hits and any(hits(f, d) for d in decoys):
                decoy_hits[tier] += 1
        per_family[family] = {
            "planted": len(fam_planted),
            "found": found,
            "recall": _ratio(found, len(fam_planted)),
            "reported": len(fam_reported),
            "precise": precise,
            "precision": _ratio(precise, len(fam_reported)),
            "decoy_hits": decoy_hits,
        }

    on_planted = sum(1 for f in reported if any(hits(f, p) for p in planted))
    on_decoys = sum(
        1 for f in reported
        if not any(hits(f, p) for p in planted) and any(hits(f, d) for d in decoys)
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "top": top,
        "families": per_family,
        "planted": planted_report,
        "decoys": decoy_report,
        "decoys_in_tier_a": sum(1 for d in decoy_report if "A" in d["hit_tiers"]),
        "decoys_in_top_n": sum(1 for d in decoy_report if d["in_top_n"]),
        "counts": {
            "reported": len(reported),
            "on_planted": on_planted,
            "on_decoys": on_decoys,
            "unplanted": len(reported) - on_planted - on_decoys,
        },
    }


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def render_table(report: dict[str, Any]) -> str:
    rows = [f"{'family':<18} {'planted':>7} {'found':>5} {'recall':>6} {'reported':>8} "
            f"{'precision':>9} {'decoy A/B/C':>11}"]
    for family, stats in report["families"].items():
        hits_by_tier = stats["decoy_hits"]
        rows.append(
            f"{family:<18} {stats['planted']:>7} {stats['found']:>5} {_fmt(stats['recall']):>6} "
            f"{stats['reported']:>8} {_fmt(stats['precision']):>9} "
            f"{hits_by_tier['A']}/{hits_by_tier['B']}/{hits_by_tier['C']:>9}"
        )
    counts = report["counts"]
    rows.append(
        f"reported {counts['reported']}, on planted {counts['on_planted']}, "
        f"on decoys {counts['on_decoys']}, unplanted {counts['unplanted']}"
    )
    rows.append(f"decoys in tier A: {report['decoys_in_tier_a']}")
    rows.append(f"decoys in top {report['top']}: {report['decoys_in_top_n']}")
    return "\n".join(rows)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score scan output against planted.json")
    parser.add_argument("--planted", required=True, help="path to the fixture's planted.json")
    parser.add_argument(
        "--workdir",
        default=".tech-debt",
        help="directory holding findings.json or verified.json and optionally ranked.json",
    )
    parser.add_argument("--top", type=int, default=5, help="top-N size used for the decoy check")
    parser.add_argument("--json", action="store_true", help="print the JSON report instead")
    args = parser.parse_args(argv)
    planted_path = Path(args.planted)
    workdir = Path(args.workdir)
    if not planted_path.is_file():
        print(f"error: {planted_path} not found", file=sys.stderr)
        return 2
    try:
        planted_doc = json.loads(planted_path.read_bytes())
        findings, source = load_findings(workdir)
        top_n = load_top_n(workdir)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    report = evaluate(findings, planted_doc, top_n, top=args.top)
    report["source"] = source
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_table(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest skills/tech-debt-scan/tests/test_evaluate.py -v`
Expected: 6 passed.

- [ ] **Step 5: Lint, type-check, commit**

Run: `ruff check . && mypy && pytest -q`
Expected: clean; every test passing.

```bash
git add skills/tech-debt-scan/scripts/evaluate.py skills/tech-debt-scan/tests/test_evaluate.py
git commit -m "feat(tech-debt-scan): evaluate.py scores findings against planted.json"
```

---

### Task 13: documentation, the full gate and the pull request

**Files:**
- Modify: `README.md:69-81` (Output formats table and the sentence after it), `README.md:92-94` (ignored directories sentence)
- Modify: `docs/architecture.md:10-26` (design principles), `docs/architecture.md:132-142` (CI and testing), plus a new section after "Two-command flow"
- Modify: `skills/tech-debt-scan/SKILL.md:96-99` (step 1 postcondition)
- No script changes; every module docstring was written in its own task ([[keep-docs-in-sync]]).

**Interfaces:**
- Consumes: the CLIs and output shapes of Tasks 9 to 12 (`inventory.py --workdir`, `patterns.py`, `rules.py`, `evaluate.py`), the corpus (Task 4) and `make_history.py` (Task 3).
- Produces: documentation that matches the code, a green gate, and the phase PR.

**Spec:** 0(c) (docs ship with code), 0(g) (one branch and PR per phase), 11 "Phase 1: signals" (gate: inventory, coupling, fan-in, pattern and rule tests over the synthetic history; the two-language rule per pattern; all v1 tests green), 5 (SKILL.md step 1 keeps `--out`; `skill_check.py` guards it).

**Confidence:** 95% (prose edits verified by `skill_check.py` and by re-reading each flag against argparse; the only risk is a stale claim, which the checklist below walks).

- [ ] **Step 1: Verify every documented flag against argparse before writing**

Run from the repository root:

```bash
python skills/tech-debt-scan/scripts/inventory.py --help
python skills/tech-debt-scan/scripts/patterns.py --help
python skills/tech-debt-scan/scripts/rules.py --help
python skills/tech-debt-scan/scripts/evaluate.py --help
python skills/tech-debt-scan/scripts/config.py --help
```

Expected: `inventory.py` lists `path`, `--workdir`, `--out`, `--churn-months`; `patterns.py` lists `path`, `--workdir`, `--no-blame`; `rules.py` lists `path`, `--workdir`; `evaluate.py` lists `--planted`, `--workdir`, `--top`, `--json`; `config.py` lists `root`. Only these flags may appear in the docs below.

- [ ] **Step 2: Update the README**

Replace the Output formats table and the paragraph after it (`README.md` lines 69 to 81) with:

```markdown
## Output formats

| Artefact | Written by | Shape |
| --- | --- | --- |
| `inventory.json` | `inventory.py` | `{schema_version: 2, root, total_files, total_loc, languages, git_available, churn_window_months, hotspots[], hotspot_band[], files[], artefacts{}, docs{}, tests{}, git{}, boundary_tooling[], lint_config[], signal_sources{}}`; each `files[]` entry carries `path_class`, `hotspot_score`, `inline_disables`, the git history fields (`last_touched`, `authors`, `top_author`, `top_author_share`, `top_author_line_share`, `bugfix_share`, `migration_commits`, `flaky_commits`, `untested_change_share`), `mapped_tests`, `fan_in_approx`, `fan_out_approx`, `fan_in_mode`, `coupling_degree` |
| `coupling.json` | `inventory.py` (with `--workdir`) | `{schema_version: 2, min_shared, min_ratio, bulk_threshold, fan_in_mode, pairs[], degree{}, cycles[], directories[], unstable_edges[]}` |
| `patterns.json` | `patterns.py` | `{schema_version: 2, leads{<family>: [{rule, file, line, quote, path_class, extra}]}, satd[], stats{}}`; also fills `files[].inline_disables` in `inventory.json` |
| `rule-findings.json` | `rules.py` | `{schema_version: 2, findings[], leads{migration[]}}`; each finding is a candidate with `source: "rule"`, `tier: "A"`, `confirmed_by: ["rule:<id>"]` |
| `raw-findings.json` | Claude (from scouts) | `[{title, severity, category, evidence, suggested_fix}]` |
| `top5.json` | synthesis Agent | `{top5: [{slug, title, severity, category, reasoning, evidence, suggested_fix}]}` (exactly 5) |
| `design.md` | `design_writer.py render` | frontmatter + one H2 section per finding, each with a `yaml` status anchor |
| `chore-<slug>-<date>/` | `promote.py` | a PBI bundle: `PBI.md`, `PLAN.md`, `HISTORY.md` |

All intermediate artefacts live under `.tech-debt/` in the scanned repo (gitignore
it). The v2 signal scripts (`inventory.py --workdir`, `patterns.py`, `rules.py`,
`evaluate.py`) run by hand for now; `/tech-debt-scan` still follows the v1 steps
until phase 3. Every threshold they use comes from an optional `.tech-debt.yaml`
at the repository root; `python scripts/config.py <repo>` prints the effective
values. See [`docs/architecture.md`](docs/architecture.md) for the full design,
the debt categories, and the validation rules.
```

Replace the ignored-directories sentence (`README.md` lines 92 to 94) with:

```markdown
Files in common build/dependency directories (`node_modules`, `obj`, `target`,
`.venv`, `venv`, `__pycache__`, `dist`, `.git`, IDE and tool caches, and
`.tech-debt`) are skipped; `bin` and `build` are skipped unless they contain a
package manifest. Manifests, lockfiles, CI, container, IaC, SQL, notebook,
model-binary, config and governance files are inventoried as artefacts rather
than as code.
```

- [ ] **Step 3: Update `docs/architecture.md`**

Change the first design-principle bullet to:

```markdown
- **Language-independent.** The only language-aware code is the inventory's
  extension→language map, which also supplies each language's comment syntax
  to `patterns.py`. Every rule in `inventory.py`, `patterns.py` and `rules.py`
  is a union of idioms across languages; a test greps the scripts for any
  branch on a language name. Scout prompts and synthesis are language-neutral.
```

Insert after the "Two-command flow" section:

```markdown
## Deterministic signals (v2 phase 1)

Phase 1 of the v2 design (`docs/superpowers/specs/2026-09-04-tech-debt-scan-v2-design.md`)
adds four scripts that run by hand until phase 3 wires them into the workflow:

| Script | Reads | Writes | What it computes |
| --- | --- | --- | --- |
| `inventory.py <repo> --workdir .tech-debt` | the tree, one `git log` pass, `.tech-debt.yaml` | `inventory.json`, `coupling.json` | path classes (tests, generated, vendored, docs, source), artefact classes, per-file churn and authorship (authors keyed by email, bots dropped, joined against HEAD), `hotspot_score` and the `hotspot_band` (top 10 percent of source files, 5 to 50), blame line share on the band, change-coupling pairs (`shared >= 3`, `ratio >= 0.30`, bulk commits over 50 files excluded), approximate fan-in and fan-out by identifier stems over import-like lines with the mechanical ambiguity rule, import-line cycles of size 2 to 5 as leads, directory instability, test mapping across seven naming conventions, the docs and tests blocks |
| `patterns.py <repo> --workdir .tech-debt [--no-blame]` | `inventory.json`, the files | `patterns.json`; fills `files[].inline_disables` | regex leads per family (half-finished stubs and skips and no-timeout calls, error-masking catches with the caught variable and carrier exclusion, dead-code commented-out runs, legacy names, deprecations and flag SDK calls, security credentials with four-character redaction, string SQL, dynamic evaluation, TLS off, weak hashes, permissive CORS and suppressions, test-quality signals, stdout writes where a logger exists) and the SATD table with blame age and ticket flags |
| `rules.py <repo> --workdir .tech-debt` | `inventory.json`, the artefacts | `rule-findings.json` | tier-A findings for CI jobs, Dockerfiles and compose images, Kubernetes manifests, manifests without lockfiles, release cadence and stale environment branches, and ownership (knowledge islands, inactive top authors, CODEOWNERS coverage); migration leads for `setup.py` beside `pyproject.toml` and `tslint` beside `eslint` |
| `evaluate.py --planted <planted.json> --workdir <dir>` | `findings.json` or `verified.json`, `ranked.json` | stdout | per-family precision, recall and decoy hits by tier, and decoys in tier A or the top N, against a fixture's `planted.json` |

`config.py` loads `.tech-debt.yaml` with the spec defaults; `git_history.py`
and `reference_graph.py` hold the git pass and the stem graph that
`inventory.py` uses. Without git, churn is 0, the history fields are null and
`coupling.json` holds empty lists. The v1 command
`inventory.py <repo> --out <path>` still writes only `inventory.json`.

The fixture corpus under `skills/tech-debt-scan/tests/fixtures/corpus/`
(`service-py`, `web-ts`, `mixed-decoys` in Go) keeps each tree in `files/`, its
commit history in `history.yaml` and its planted debt and decoys in
`planted.json`; `tests/helpers/make_history.py` replays a history into a
temporary git repository at test time, so churn, coupling, blame and branches
are exercised without committing a `.git` directory.
```

In the "CI and testing" section add a bullet:

```markdown
- The corpus fixtures are replayed into temporary git repositories once per
  test session (`conftest.py` session fixtures); tests that count churn pass an
  explicit window (`churn_months=240` or `1`) because fixture dates are fixed
  while the default 12-month window moves.
```

- [ ] **Step 4: Update SKILL.md step 1**

Replace the postcondition bullet of `### Step 1 — Inventory the repo` (`SKILL.md` lines 96 to 99) with:

```markdown
- Postcondition: `.tech-debt/inventory.json` exists (a JSON object with
  `schema_version`, `root`, `total_files`, `total_loc`, `languages`,
  `git_available`, `churn_window_months`, `hotspots`, `hotspot_band`, `files`,
  `artefacts`, `docs`, `tests`, `git`; each file entry carries `loc`,
  `complexity`, `max_indent`, `churn`, `path_class`, `hotspot_score`). If it is
  missing, abort with exit 5. When `inventory.py` is run with `--workdir
  .tech-debt` instead of `--out`, it also writes `.tech-debt/coupling.json`; the
  command above with `--out` is unchanged and writes only the inventory.
```

- [ ] **Step 5: Run the full gate and record the output**

Run from the repository root:

```bash
ruff check .
mypy
python skills/tech-debt-scan/scripts/skill_check.py
pytest -v
```

Expected:

- `ruff check .` prints `All checks passed!`
- `mypy` prints `Success: no issues found in 15 source files` (the nine v1 scripts plus `config.py`, `git_history.py`, `reference_graph.py`, `patterns.py`, `rules.py`, `evaluate.py`)
- `skill_check.py` prints `ok: all SKILL.md commands match their scripts (...\skills\tech-debt-scan\SKILL.md)`
- `pytest -v` ends with `N passed` and no failures, errors or skips on a machine with git (about 265: the 124 v1 tests plus the Task 1 to 12 tests); paste the exact line into the PR body.

Run once more with a 12-month window over the corpus to confirm no test depends on the moving window: `pytest -q skills/tech-debt-scan/tests/test_inventory_v2.py skills/tech-debt-scan/tests/test_patterns.py skills/tech-debt-scan/tests/test_rules.py`, expected all passed.

- [ ] **Step 6: Commit the docs**

```bash
git add README.md docs/architecture.md skills/tech-debt-scan/SKILL.md
git commit -m "docs(tech-debt-scan): describe the v2 phase 1 signal scripts and outputs"
```

- [ ] **Step 7: Open the pull request**

Write the body to the scratchpad (`pr-body.md`) with this content, filling in the pytest line from Step 5:

```markdown
## tech-debt-scan v2 phase 1: signals

Implements spec section 11 "Phase 1: signals" from
`docs/superpowers/specs/2026-09-04-tech-debt-scan-v2-design.md`, following
`docs/superpowers/plans/2026-09-04-tech-debt-scan-v2-phase-1.md`.

- `config.py`: `.tech-debt.yaml` loader with the spec defaults and unknown-key warnings.
- `validation.py` / `promote.py`: `accepted` status, four new debt types, `type_id` and tier validators, `accepted` counted separately.
- `inventory.py` v2 (+ `git_history.py`, `reference_graph.py`): path and artefact classes, one git pass with authors keyed by email, change coupling and `coupling.json`, approximate fan-in with the mechanical ambiguity rule, import-line cycles, hotspot band with blame share, test mapping, docs and tests blocks, `--workdir`; `--out` unchanged.
- `patterns.py`: regex lead table with two-language positives per rule, SATD table with blame ages, credential redaction, inline-disable write-back.
- `rules.py`: tier-A findings for CI, containers, IaC, manifests, release and ownership; migration leads.
- `evaluate.py`: precision, recall and decoy tiers against `planted.json`.
- Corpus: `service-py`, `web-ts`, `mixed-decoys` (Go) with replayable histories and `planted.json`; `tests/helpers/make_history.py`.

Gate: `ruff check .`, `mypy`, `skill_check.py` and `pytest -v` all green (`<paste the pytest summary line>`). All v1 tests pass unchanged; `/tech-debt-scan` is unchanged.

Docs updated: README output formats table, `docs/architecture.md` signals section, SKILL.md step 1 postcondition, and every new module's docstring.

Decisions flagged for review: `rule-findings.json` is an object with `findings` and `leads`; manifest findings are tier A with family `dependency-debt`; `files[].top_author` added for the former-contributor rule; the two indent thresholds behind `deep_indent_lines` and `longest_indented_run` are constants in `inventory.py`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01MmhTCQKG5RSWjmpVSkirTU
```

Then:

```bash
git push -u origin feat/tech-debt-scan-v2-phase-1
gh pr create --base main --head feat/tech-debt-scan-v2-phase-1 --title "feat(tech-debt-scan): v2 phase 1 signals" --body-file "<scratchpad>/pr-body.md"
```

Expected: `gh` prints the PR URL. Record it in the final report.

---

## Assumptions (spec 0(a) buckets)

**Real concerns, each with a decision and residual risk.**

1. Corpus facts move with the clock: the default 12-month churn window, SATD ages, branch staleness and author inactivity all depend on "now". Decision: tests pass `churn_months=240` or `1`, `rules.run_rules` takes an injectable `now` pinned to 2026-09-04, age assertions are lower bounds, and ownership assertions test membership. Residual: the former-contributor rule starts firing on the corpus after 2026-12-19 and the `test_ownership_island...` rule sets stay membership-based for that reason.
2. `rule-findings.json` shape: spec 4.4 said "a list" and also put migration leads in "the leads block", while spec 9 allows only one cross-script write-back. Decision: an object `{schema_version, findings, leads}`; spec 4.4 was amended on 2026-09-04 to this shape, so phase 2's `merge_findings.py` reads `findings` and `plan_scan.py` reads `leads`. Residual: none.
3. Manifest findings at tier A (4.4) versus the tier-B cap on structural dependency facts (2.3). Decision: tier A per 4.4, family `dependency-debt`. Residual: the lead decides; changing it is a one-line edit in `GROUP_META`.
4. Approximate fan-in was measured on Python only. Decision: hand-counted TypeScript and Go expectations in Task 8 derived from the fixture imports; edges from tests count; a class-name import that equals a module stem is counted (documented in the service-py test). Residual: real repositories will differ; fan-in stays a lead and corroborator.
5. Regex rules across three languages (Task 10 at 86 percent). Decision: leads never findings, positive and decoy tests per rule, synthetic two-language positives where the corpus has none. Residual: unmeasured precision on real code until the phase 5 live run.
6. `files[].top_author` was not in the spec 4.2 schema. Decision: added because the former-contributor rule needs the top author's identity; additive and checked by key presence only. Spec 4.2 was amended on 2026-09-04 to carry the key. Residual: none.
7. Spec 0(g) said the PR is created "at task start"; the plan opens it in Task 13. Spec 0(g) was amended on 2026-09-04 to "branch before the first task, PR in the final gate task". Residual: none.

**Verified safe, with evidence.**

- Git output formats used by Tasks 3, 6 and 10 were run on this machine before drafting: `\x1e`-prefixed log records with a blank line before file names, `%aI` rendering `+00:00` as `Z`, empty `%(symref)` for ordinary refs, `merge-base --is-ancestor` exit 1 versus 128, lightweight-tag `creatordate` equal to the commit date, `blame --line-porcelain` `author` and `author-mail` lines, `rev-parse --verify -q` exit 1 for a missing ref, and UTF-8 bytes for a non-ASCII path under `core.quotePath=false`.
- `yaml.compose` gives `MappingNode.value` pairs whose key `start_mark.line` is zero-based, and returns `None` for an empty document.
- The v1 pins survive: artefacts never enter `files`, `bin` and `build` stay ignored without a manifest, the `hotspots` key set is untouched, and the no-git path leaves churn at 0.
- SKILL.md step 1 lints because `--out` and `--churn-months` remain in `inventory.py --help`.
- LF-only outputs use `write_bytes`, the `design_writer.py` pattern.
- The corpus is excluded from ruff, so its deliberate `except Exception: pass`, string SQL and 100-plus-character lines cannot fail the gate; mypy never sees it.

**Minor or accepted.**

- `DEEP_INDENT_UNITS = 3` and `RUN_INDENT_UNITS = 2` are this plan's calibration for two spec-named fields.
- The 62-entry SATD marker list is a stand-in for the Potdar and Shihab list the research cites but does not reproduce.
- `ci_retry_config`, the logger-present test, the CLI exclusion, the dangling-reference heuristic and the CODEOWNERS matcher are defined here because the spec names the outputs but not the mechanics.
- Stem matching counts a class import whose name equals a module stem (`Refund` for `refund.py`); fan-in is labelled approximate.
- `--` is a default line-comment marker for non-code artefacts, so a shell flag can produce comment text; the SATD list contains no flag-like words.
- Blame is capped at 50 band files and 200 SATD files; `commits_since` costs one `git rev-list` per distinct blamed commit and file.

## Self-review

**1. Spec coverage.**

| Spec section | Task |
|---|---|
| 0(b) confidence per task | every task header |
| 0(c) docs ship with code | Task 13 (README, architecture.md, SKILL.md) and each task's module docstring |
| 0(d), 3.3 language-agnostic rule and two languages per rule | Task 5 (`LANG_COMMENT`), Task 10 (union tables, grep test, two-language positives) |
| 0(e) no live LLM in tests | no task dispatches an agent |
| 0(g) branch and PR per phase | Global Constraints (branch exists), Task 13 Step 7 |
| 3.3 `--workdir`, no file lists, timeouts, LF-only | Tasks 9 to 12 CLIs; `run_git` and `_run` timeouts; `write_json` |
| 4.1 config defaults, merge, unknown key, four `enabled` forms | Task 1 |
| 4.2 artefact classes, `DEFAULT_IGNORE`, path classes | Task 5 |
| 4.2 git pass, authors, HEAD join, branches, tags, blame | Task 6 (blame wired in Task 9) |
| 4.2 change coupling, `coupling.json` | Task 7 |
| 4.2 fan-in, ambiguity, anywhere fallback, cycles, directories | Task 8 |
| 4.2 hotspots, band, test mapping, docs and tests blocks, `inline_disables` 0, no-git shape | Task 9 (no-git shape also Task 6) |
| 4.3 rule table, SATD with blame, redaction, write-back, cap, stats, tests | Task 10 |
| 4.4 rule groups, severities, thresholds, output schema | Task 11 |
| 4.7 fingerprint and candidate schema (as far as rules need them) | Task 11 |
| 4.12 `accepted` counted separately | Task 2 |
| 4.13 validators | Task 2 |
| 6 corpus, `planted.json`, `make_history.py`, `evaluate.py` | Tasks 3, 4, 12 |
| 9 single cross-script write-back | Task 10 |
| 11 phase 1 gate | Task 13 |

Not placed, by design of the phase: 4.5 to 4.11 and the chunking, verifier, ranking, baseline and rendering work belong to phases 2 to 5. Spec 6's "one cross-cutting test additionally greps that no script outside the extension map and `tools_probe.py` branches on a language name" is Task 10's grep test with `tools_probe.py` allow-listed.

**2. Placeholder scan.** The plan was grepped for `TBD`, `TODO`, `implement later`, `fill in`, `add error handling`, `add validation`, `handle edge cases`, `similar to Task` and `as in Task`. The only hits are fixture content (`# TODO(#42)` in `legacy_export.py`), the SATD marker list and the SATD tests, which are data, not instructions. Every code step carries complete code; every RED step names its failure.

**3. Type consistency across tasks.**

| Symbol | Defined in | Used in |
|---|---|---|
| `DEFAULTS`, `CONFIG_FILENAME`, `FAMILY_SETS`, `ConfigError`, `deep_merge`, `load_config`, `enabled_families` | Task 1 | Tasks 5 to 12 |
| `VALID_TIERS`, `validate_type_id`, `validate_tier`, `PromoteResult.accepted_count` | Task 2 | phase 2 and 3 |
| `CORPUS_ROOT`, `FINAL`, `HistoryError`, `replay_history`, `replay_fixture`, `git_output` | Task 3 | Tasks 4, 6, 12 |
| `service_py_repo`, `web_ts_repo`, `mixed_decoys_repo` fixtures | Task 4 | Tasks 5 to 12 |
| `LANG_COMMENT`, `DEFAULT_COMMENT`, `MANIFEST_NAMES`, `PATH_CLASS_GLOBS`, `ARTEFACT_CLASSES`, `_classify_path`, `_walk_artefacts`, `_line_metrics` (5-tuple), `FileEntry` v2 fields, `walk_inventory(..., config=None)` | Task 5 | Tasks 6 to 11 |
| `Commit`, `FileHistory`, `run_git`, `parse_log`, `git_log_pass`, `is_bot`, `derive_file_history`, `repo_authors`, `parse_branch_refs`, `list_branches`, `list_tags`, `mailmap_present`, `blame_top_share` | Task 6 | Tasks 7, 9, 10 |
| `change_coupling`, `build_all`, coupling document keys | Task 7 | Tasks 8, 9, 10, 11, 12 |
| `GraphFile`, `GraphResult`, `file_stem`, `numbered_logical_lines`, `logical_lines`, `is_import_line`, `import_lines`, `identifier_tokens`, `tarjan_scc`, `build_reference_graph`, `IMPORT_LINE_RE`, `MAX_CONTINUATION` | Task 8 | Tasks 9, 10 |
| `HOTSPOT_BLAME_CAP`, `_score_entries`, `_hotspot_band`, `_map_tests`, `_tests_block`, `_docs_block`, `_tooling_blocks`, `write_json`, `write_outputs`, `_main` with `--workdir` | Task 9 | Tasks 10, 11, 12, 13 |
| `Rule`, `RULES`, `Lead`, `comment_text`, `is_comment_line`, `strip_markers`, `redact`, `run_patterns`, `capped_leads`, `SATD_MARKERS` | Task 10 | Task 13, phase 2 |
| `Hit`, `GROUP_META`, `fingerprint`, `run_rules` | Task 11 | Task 12 (shape), phase 2 |
| `load_findings`, `load_top_n`, `hits`, `evaluate`, `render_table` | Task 12 | phase 5 |

The `_write_json` name used while drafting was renamed to `write_json` in Task 9 before any later task referenced it; Tasks 10, 11 and 12 import `write_json`. `numbered_logical_lines` is defined in Task 8 and consumed by Task 10's no-timeout scanner. The `catch` rule scans `SOURCE` only (Task 10 decision), while spec 4.3's error-masking row lists `source, ci, config`; the `ci, config` scope applies to the assertion-switch rule.
