"""Build a language-agnostic file inventory and coupling document (spec 4.2).

``python scripts/inventory.py <repo> --workdir .tech-debt`` writes
``inventory.json`` and ``coupling.json``; ``--out <path>`` keeps the v1
behaviour of writing only ``inventory.json`` to that path. ``.tech-debt.yaml``
at the repository root (``config.py``) supplies every threshold.

LOC is counted by tallying ``\\n`` occurrences in the opened file iterator,
never via ``Path.read_text()`` (which translates line endings on Windows), so
counts are platform-independent.

Beyond the raw file walk, the inventory now carries the two signals behind
hotspot analysis (Tornhill, "Your Code as a Crime Scene"):

  - ``complexity``: an indentation-based complexity proxy (total logical
    indent units across the file, tab = one unit, 4 spaces = one unit). It is
    language-agnostic and correlates well with cyclomatic complexity without
    needing a parser per language.
  - ``churn`` and the history fields (``last_touched``, ``authors``,
    ``top_author``, ``top_author_share``, ``bugfix_share``,
    ``migration_commits``, ``flaky_commits``, ``untested_change_share``)
    come from one ``git log`` pass in ``git_history.py`` over the churn window
    (default 12 months), joined against the files present at HEAD. Without
    git ``churn`` is 0 and the history fields are null (``git_available``
    records which). The top-level ``git`` block carries authors, branches,
    tags and the window counts; ``signal_sources.git`` is the pass timestamp.

``hotspots`` ranks files by normalised churn x complexity (0-100). Hotspots
are where debt accrues the highest interest: complex code the team keeps
having to change. Scouts and the synthesis step use this list to prioritise.

v2 (spec 4.2) adds path classes on every entry (tests, generated, vendored,
docs, source), an ``artefacts`` block for the files the extension map skips
(manifests, lockfiles, CI, containers, IaC, SQL, notebooks, model binaries,
config, governance), and a conditional ignore: a ``bin/`` or ``build/``
directory is skipped only when it holds no manifest of its own *and* its
parent directory is the repository root or itself holds a manifest — a
nested package directory that merely happens to be named ``build`` (a
package name in Go's own standard library) is walked. ``.tech-debt.yaml`` at
the root is never an artefact. ``LANG_COMMENT`` is the comment-syntax half
of the extension map that ``patterns.py`` reads; nothing else in the skill
is language-aware.

``coupling.json`` (spec 4.2) comes from the same pass: pairs of source-class
files co-committed at least ``coupling.min_shared`` times with
``shared / mean(commits_a, commits_b) >= coupling.min_ratio``, bulk commits
excluded, plus per-file ``coupling_degree``. ``build_all`` returns both
documents; ``walk_inventory`` keeps the v1 signature and returns the first.

Approximate fan-in and fan-out (``reference_graph.py``): identifier-stem
matching over import-like lines by default, whole-file matching as the
labelled ``anywhere`` fallback, mechanical ambiguity (shared, short, package,
harness and stoplist stems give ``fan_in_approx`` null). Import-line SCCs of
size 2 to 5 are the ``cycles`` leads in ``coupling.json``, with directory
aggregates and ``unstable_edges``.

``hotspots`` keeps its v1 shape and key set; every ``files[]`` entry carries
``hotspot_score`` and the top-level ``hotspot_band`` lists the top fraction
of source-class files (``hotspot_band`` in config: 0.10, at least 5, at most
50). Blame runs only for band files (cap 50) to give ``top_author_line_share``.
``mapped_tests`` reads a test file name back to its source stem through
``_test_stem_keys``, one union of the seven naming conventions; the
``tests`` block reports the test-to-source ratio, coverage gates and CI retry
configuration; the ``docs`` block reports README, CONTRIBUTING, ADR and
CHANGELOG presence, the latest tag, dangling references in docs and doc
staleness versus code. ``inline_disables`` is emitted as 0 and filled in
place by ``patterns.py``.

Every artefact entry carries ``path_class`` from the same classifier the code
entries use, so a later stage can apply path-class disables to a workflow,
Dockerfile or config that lives under a tests or fixtures tree.

A file over ``MAX_SCAN_BYTES`` (2 MB), or with a NUL byte in its first
``NUL_SNIFF_BYTES``, is never read: its entry keeps ``loc`` 0 and
``complexity`` 0 with ``skipped_large`` true, the reference graph and the docs
block see it as empty text, and the top-level ``skipped_large_files`` counts
it. ``patterns.py`` imports the same limit so both walks skip the same files.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import re
import sys
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, cast

from config import CONFIG_FILENAME, DEFAULTS, ConfigError, load_config
from docs_signals import docs_block, read_head
from git_history import (
    Commit,
    FileHistory,
    blame_top_share,
    change_coupling,
    derive_file_history,
    git_log_pass,
    list_branches,
    list_tags,
    mailmap_present,
    repo_authors,
)
from reference_graph import GraphFile, build_reference_graph, file_stem

EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".cs": "csharp",
    ".java": "java",
    ".kt": "kotlin",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".md": "markdown",
}

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

# Skipped only when the directory itself holds no manifest *and* its parent is
# the repository root or itself holds a manifest (spec 4.2, amended): a `bin/`
# that is a CLI package or a `build/` that is a Gradle module is real source,
# and so is a `build/` nested arbitrarily deep under an ordinary source
# directory (e.g. a Go `internal/build` package, `build` being a stdlib name).
CONDITIONAL_IGNORE: tuple[str, ...] = ("bin", "build")

# Size guard (spec 4.2). A file over MAX_SCAN_BYTES, or with a NUL byte in its
# first NUL_SNIFF_BYTES, is never read: its entry keeps loc 0 and complexity 0
# with `skipped_large` true and the top-level `skipped_large_files` counts it.
# `patterns.py` imports MAX_SCAN_BYTES from here so both walks skip the same
# files. Text artefacts are counted a chunk at a time so a file just under the
# limit is never decoded whole.
MAX_SCAN_BYTES = 2_000_000
NUL_SNIFF_BYTES = 1024
_LOC_CHUNK_BYTES = 1024 * 1024

# Indent thresholds behind the complex-units leads (spec 2.3, 4.2). The spec
# names the fields; these values are the calibration point.
DEEP_INDENT_UNITS = 3
RUN_INDENT_UNITS = 2

# One logical indent unit = one tab or this many spaces.
_INDENT_SPACES = 4

DEFAULT_CHURN_MONTHS = 12

# How many files the hotspots summary carries (the full per-file data stays in
# ``files`` regardless).
HOTSPOT_LIMIT = 20

# Blame runs only for hotspot-band files (spec 4.2), at most this many.
HOTSPOT_BLAME_CAP = 50

_COVERAGE_GATE_RE = re.compile(r"fail_under|coverageThreshold|check-coverage")
_COVERAGE_GATE_NAMES = ("codecov.yml", ".codecov.yml")
_CI_RETRY_RE = re.compile(r"retry|rerun|retries|max_attempts", re.IGNORECASE)

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


class InventoryError(Exception):
    """Raised when the inventory walk fails."""


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
    skipped_large: bool = False  # the size guard tripped; the file was never read


def _skips_read(path: Path, size: int) -> bool:
    """True when the size guard forbids reading ``path`` at all (spec 4.2)."""
    if size > MAX_SCAN_BYTES:
        return True
    try:
        with path.open("rb") as handle:
            return b"\x00" in handle.read(NUL_SNIFF_BYTES)
    except OSError:
        return False  # let the caller's own read report the failure


def _count_newlines(path: Path) -> int:
    """LOC of a text file, counted in chunks so it is never decoded whole."""
    total = 0
    tail = b""
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(_LOC_CHUNK_BYTES):
                total += chunk.count(b"\n")
                tail = chunk
    except OSError:
        return 0
    return total + (1 if tail and not tail.endswith(b"\n") else 0)


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
                if index == 0:
                    return True  # the directory's parent is the repository root
                parent = root.joinpath(*parts[:index])
                if parent not in manifest_dirs:
                    manifest_dirs[parent] = _has_manifest(parent)
                if manifest_dirs[parent]:
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


def _build_hotspots(entries: list[FileEntry]) -> list[dict[str, object]]:
    """Rank files by normalised churn x complexity (score 0-100, top N only)."""
    max_churn = max((e.churn for e in entries), default=0)
    max_cx = max((e.complexity for e in entries), default=0)
    if max_churn == 0 or max_cx == 0:
        return []
    scored: list[tuple[float, dict[str, object]]] = []
    for e in entries:
        score = round((e.churn / max_churn) * (e.complexity / max_cx) * 100, 1)
        if score > 0:
            scored.append(
                (
                    score,
                    {
                        "path": e.path,
                        "churn": e.churn,
                        "complexity": e.complexity,
                        "loc": e.loc,
                        "score": score,
                    },
                )
            )
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [hotspot for _, hotspot in scored[:HOTSPOT_LIMIT]]


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


def _artefact_entry(
    path: Path,
    rel: str,
    cls: str,
    history: FileHistory | None,
    extra_classes: dict[str, list[str]] | None,
) -> dict[str, Any]:
    size = path.stat().st_size
    skipped = _skips_read(path, size)
    entry: dict[str, Any] = {
        "path": rel,
        "path_class": _classify_path(rel, extra_classes),
        "loc": 0,
        "churn": history.churn if history else 0,
        "last_touched": history.last_touched if history else None,
        "size_bytes": size,
        "skipped_large": skipped,
    }
    if cls == "model_binary":  # size and LFS pointer only; never opened further
        try:
            with path.open("rb") as handle:
                entry["lfs_pointer"] = handle.read(64).startswith(_LFS_POINTER_PREFIX)
        except OSError:
            entry["lfs_pointer"] = False
        return entry
    if skipped:
        return entry
    entry["loc"] = _count_newlines(path)
    if cls == "notebook":  # bounded by the guard, so the cell facts need the text
        try:
            text = path.read_bytes().decode("utf-8", errors="ignore")
        except OSError:
            return entry
        entry["cells"], entry["monotonic_execution"] = _notebook_facts(text)
    return entry


def _walk_artefacts(
    root: Path,
    candidates: list[tuple[Path, str]],
    histories: dict[str, FileHistory],
    extra_classes: dict[str, list[str]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Classify the files the extension map skipped (spec 4.2 artefact classes)."""
    out: dict[str, list[dict[str, Any]]] = {cls: [] for cls, _ in ARTEFACT_CLASSES}
    for path, rel in candidates:
        cls = _artefact_class(path, rel)
        if cls is None:
            continue
        out[cls].append(_artefact_entry(path, rel, cls, histories.get(rel), extra_classes))
    return out


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
            text = read_head(root / rel)
            if name in _COVERAGE_GATE_NAMES or _COVERAGE_GATE_RE.search(text):
                gate.add(rel)
            if cls == "ci" and _CI_RETRY_RE.search(text):
                retry.add(rel)
    return {
        "test_to_source_ratio": round(n_tests / n_source, 3) if n_source else 0.0,
        "coverage_gate": sorted(gate),
        "ci_retry_config": sorted(retry),
    }


def _tooling_blocks(root: Path) -> tuple[list[str], list[str]]:
    """(boundary_tooling, lint_config) by root file names and pyproject tables."""
    boundary = [n for n in _BOUNDARY_TOOLING_NAMES if (root / n).is_file()]
    lint = [n for n in _LINT_CONFIG_NAMES if (root / n).is_file()]
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        text = read_head(pyproject)
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
        stat = path.stat()
        skipped = _skips_read(path, stat.st_size)
        if skipped:
            text = ""  # the graph and the docs block see an empty file, not a guess
        else:
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
                mtime=stat.st_mtime,
                complexity=indent_total,
                max_indent=max_indent,
                churn=0,
                language=lang,
                path_class=_classify_path(rel_str, extra_classes),
                deep_indent_lines=deep,
                longest_indented_run=longest,
                skipped_large=skipped,
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
    artefacts = _walk_artefacts(
        root, artefact_candidates, histories if git_available else {}, extra_classes
    )

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
        "skipped_large_files": sum(1 for e in entries if e.skipped_large) + sum(
            1 for items in artefacts.values() for a in items if a["skipped_large"]
        ),
        "docs": docs_block(
            entries, artefacts, texts, git_block, git_available,
            code_exts=frozenset(EXT_TO_LANG),
        ),
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


def walk_inventory(
    root: Path,
    ignore: tuple[str, ...] = DEFAULT_IGNORE,
    churn_months: int = DEFAULT_CHURN_MONTHS,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """v1 entry point: the inventory document only (see ``build_all``)."""
    inventory, _coupling = build_all(root, ignore=ignore, churn_months=churn_months, config=config)
    return inventory


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


if __name__ == "__main__":
    raise SystemExit(_main())
