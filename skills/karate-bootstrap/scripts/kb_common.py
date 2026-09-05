"""Shared helpers for karate-bootstrap scripts.

Exit codes (spec section 9): 0 ok, 2 validation failure, 3 unsupported
stack, 4 no schema source, 5 missing expected output, 6 stopped by a stop
condition, 7 container runtime or JDK missing.

Every script is direct-path invocable and imports this module flatly
(``from kb_common import ...``). Tests resolve the import through
``tests/conftest.py``; mypy through ``mypy_path`` in ``pyproject.toml``.
"""
from __future__ import annotations

import json
import sys
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any, Final, cast

import yaml

EXIT_OK: Final[int] = 0
EXIT_VALIDATION: Final[int] = 2
EXIT_UNSUPPORTED_STACK: Final[int] = 3
EXIT_NO_SCHEMA: Final[int] = 4
EXIT_MISSING_OUTPUT: Final[int] = 5
EXIT_STOPPED: Final[int] = 6
EXIT_TOOLCHAIN: Final[int] = 7

LEDGER_VERSION: Final[int] = 1

DEFAULT_IGNORE: Final[tuple[str, ...]] = (
    ".git",
    ".idea",
    ".vscode",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "bin",
    "obj",
    "target",
    "build",
    "dist",
    "karate-tests",
)

# Directories that hold a project's own tests. Skipped by ``iter_files`` when
# ``skip_test_trees=True`` so test fixtures never win over production config.
TEST_TREE_NAMES: Final[tuple[str, ...]] = ("test", "tests", "src/test", "__tests__", "spec")
_TEST_TREE_SUFFIXES: Final[tuple[str, ...]] = ("Tests", ".Tests")


class KbError(Exception):
    """A user-facing failure with a defined process exit code."""

    def __init__(self, message: str, exit_code: int = EXIT_VALIDATION) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(read_text(path))
    except json.JSONDecodeError as err:
        raise KbError(f"{path}: invalid JSON: {err}") from err
    if not isinstance(data, dict):
        raise KbError(f"{path}: expected a JSON object at top level")
    return cast(dict[str, Any], data)


def write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(data), indent=2) + "\n", encoding="utf-8")


def read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(read_text(path))
    except yaml.YAMLError as err:
        raise KbError(f"{path}: invalid YAML: {err}") from err
    if not isinstance(data, dict):
        raise KbError(f"{path}: expected a YAML mapping at top level")
    return cast(dict[str, Any], data)


def read_yaml_docs(path: Path) -> list[dict[str, Any]]:
    try:
        docs = list(yaml.safe_load_all(read_text(path)))
    except yaml.YAMLError as err:
        raise KbError(f"{path}: invalid YAML: {err}") from err
    return [cast(dict[str, Any], d) for d in docs if isinstance(d, dict)]


def write_yaml(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(dict(data), sort_keys=False, allow_unicode=True, width=100)
    path.write_text(text, encoding="utf-8")


def require_file(path: Path, what: str) -> Path:
    if not path.is_file():
        raise KbError(f"expected {what} at {path}; it does not exist", EXIT_MISSING_OUTPUT)
    return path


def rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def is_test_tree(directory: Path, root: Path) -> bool:
    """True when ``directory`` holds the project's own tests rather than its sources."""
    name = directory.name
    if name in TEST_TREE_NAMES or name.endswith(_TEST_TREE_SUFFIXES):
        return True
    try:
        relative = directory.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return False
    return relative in TEST_TREE_NAMES


def iter_files(root: Path, suffixes: tuple[str, ...], *,
               skip_test_trees: bool = False) -> Iterator[Path]:
    """Yield files under ``root`` with one of ``suffixes``, skipping DEFAULT_IGNORE dirs.

    Traversal is depth-first in alphabetical order, so the first file seen for a
    given name is stable across platforms. With ``skip_test_trees`` the project's
    own test directories (``src/test``, ``tests``, ``*.Tests``, ...) are not
    descended into, so test fixtures never shadow production sources or config.
    """
    stack = [root]
    while stack:
        current = stack.pop()
        directories: list[Path] = []
        for child in sorted(current.iterdir()):
            if child.is_dir():
                if child.name in DEFAULT_IGNORE:
                    continue
                if skip_test_trees and is_test_tree(child, root):
                    continue
                directories.append(child)
            elif child.suffix in suffixes:
                yield child
        stack.extend(reversed(directories))


def run_cli(main: Callable[[list[str] | None], int], argv: list[str] | None = None) -> int:
    try:
        return main(argv)
    except KbError as err:
        print(f"error: {err}", file=sys.stderr)
        return err.exit_code
