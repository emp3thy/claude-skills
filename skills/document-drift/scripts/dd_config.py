"""Loading of ``.document-drift.yaml``: defaults, type checks, and warnings."""
from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import yaml

CONFIG_FILENAME = ".document-drift.yaml"

DEFAULTS: dict[str, Any] = {
    "exclude": [],
    "never_edit_heading": None,
    "branch": "docs/drift-{date}",
    "commit_trailers": [],
    "unit_lines": 6000,
    "max_delete_lines": 15,
    "max_section_lines": 40,
    "min_anchor_ratio": 0.25,
    "undocumented_ok": [],
    "readme": True,
    "area_lines": 5000,
    "readme_lines": 300,
    "caps": {
        "review": 40,
        "gaps": 15,
        "verify": 25,
        "sheet_agents": 12,
        "readme_batch": 15,
    },
    "models": {
        "review": "sonnet",
        "gap": "sonnet",
        "verify": "opus",
        "sheet": "sonnet",
        "readme": "opus",
    },
}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_str_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _is_regex(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        re.compile(value)
    except re.error:
        return False
    return True


def _is_optional_regex(value: Any) -> bool:
    return value is None or _is_regex(value)


def _is_non_negative_int(value: Any) -> bool:
    return _is_int(value) and value >= 0


def _is_ratio(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1


def _is_non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


# Nested mappings: per sub-key (validator, expectation); unknown sub-keys are ignored.
_NESTED_VALIDATORS: dict[str, dict[str, tuple[Any, str]]] = {
    "caps": {
        **{name: (_is_non_negative_int, "a non-negative integer")
           for name in ("review", "gaps", "verify", "sheet_agents")},
        # the size of a README verifier batch: 0 would batch nothing
        "readme_batch": (lambda v: _is_int(v) and v > 0, "a positive integer"),
    },
    "models": {
        name: (_is_non_empty_str, "a non-empty string")
        for name in ("review", "gap", "verify", "sheet", "readme")
    },
}

_VALIDATORS: dict[str, tuple[Any, str]] = {
    "exclude": (_is_str_list, "a list of strings"),
    "never_edit_heading": (_is_optional_regex, "a valid regular expression string"),
    "branch": (lambda v: isinstance(v, str) and bool(v), "a non-empty string"),
    "commit_trailers": (_is_str_list, "a list of strings"),
    "unit_lines": (lambda v: _is_int(v) and v > 0, "a positive integer"),
    "max_delete_lines": (_is_non_negative_int, "a non-negative integer"),
    "max_section_lines": (_is_non_negative_int, "a non-negative integer"),
    "min_anchor_ratio": (_is_ratio, "a number between 0 and 1"),
    "undocumented_ok": (_is_str_list, "a list of strings"),
    "readme": (lambda v: isinstance(v, bool), "a boolean"),
    "area_lines": (lambda v: _is_int(v) and v > 0, "a positive integer"),
    "readme_lines": (lambda v: _is_int(v) and v > 0, "a positive integer"),
}


def _merge_nested(
    key: str, value: Any, config: dict[str, Any], warnings: list[str]
) -> None:
    """Validate a nested mapping per sub-key; bad sub-keys warn and keep their default."""
    if not isinstance(value, dict):
        warnings.append(f"{CONFIG_FILENAME}: {key} must be a mapping; using the default")
        return
    for sub, sub_value in value.items():
        if sub not in _NESTED_VALIDATORS[key]:
            warnings.append(f"{CONFIG_FILENAME}: unknown key '{key}.{sub}' ignored")
            continue
        check, expected = _NESTED_VALIDATORS[key][sub]
        if check(sub_value):
            config[key][sub] = sub_value
        else:
            warnings.append(
                f"{CONFIG_FILENAME}: {key}.{sub} must be {expected}; using the default"
            )


def load_config(root: Path) -> tuple[dict[str, Any], list[str]]:
    """Return ``(config, warnings)``; unknown keys and wrong types warn and fall back."""
    config = copy.deepcopy(DEFAULTS)
    warnings: list[str] = []
    path = root / CONFIG_FILENAME
    if not path.is_file():
        return config, warnings
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        warnings.append(f"{CONFIG_FILENAME}: unreadable ({type(exc).__name__}); using defaults")
        return config, warnings
    if raw is None:
        return config, warnings
    if not isinstance(raw, dict):
        warnings.append(f"{CONFIG_FILENAME}: top level must be a mapping; using defaults")
        return config, warnings
    for key, value in raw.items():
        if key not in DEFAULTS:
            warnings.append(f"{CONFIG_FILENAME}: unknown key {key!r} ignored")
            continue
        if key in _NESTED_VALIDATORS:
            _merge_nested(key, value, config, warnings)
            continue
        check, expected = _VALIDATORS[key]
        if check(value):
            config[key] = copy.deepcopy(value)
        else:
            warnings.append(f"{CONFIG_FILENAME}: {key} must be {expected}; using the default")
    return config, warnings
