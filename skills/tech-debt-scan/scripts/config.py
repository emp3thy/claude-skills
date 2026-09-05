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
