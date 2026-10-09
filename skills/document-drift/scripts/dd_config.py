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
    "lead_cap": 25,
    "recent_change_days": 14,
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


_VALIDATORS: dict[str, tuple[Any, str]] = {
    "exclude": (_is_str_list, "a list of strings"),
    "never_edit_heading": (_is_optional_regex, "a valid regular expression string"),
    "branch": (lambda v: isinstance(v, str) and bool(v), "a non-empty string"),
    "commit_trailers": (_is_str_list, "a list of strings"),
    "lead_cap": (lambda v: _is_int(v) and v >= 0, "a non-negative integer"),
    "recent_change_days": (lambda v: _is_int(v) and v >= 0, "a non-negative integer"),
}


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
        check, expected = _VALIDATORS[key]
        if check(value):
            config[key] = copy.deepcopy(value)
        else:
            warnings.append(f"{CONFIG_FILENAME}: {key} must be {expected}; using the default")
    return config, warnings
