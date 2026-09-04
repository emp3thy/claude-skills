"""Build a language-agnostic file inventory of a directory tree.

LOC is counted by tallying ``\\n`` occurrences in the opened file iterator,
never via ``Path.read_text()`` (which translates line endings on Windows), so
counts are platform-independent.

Beyond the raw file walk, the inventory now carries the two signals behind
hotspot analysis (Tornhill, "Your Code as a Crime Scene"):

  - ``complexity``: an indentation-based complexity proxy (total logical
    indent units across the file, tab = one unit, 4 spaces = one unit). It is
    language-agnostic and correlates well with cyclomatic complexity without
    needing a parser per language.
  - ``churn``: how many commits touched the file inside the churn window
    (default 12 months), mined from ``git log``. Zero when git is unavailable
    or the tree is not a repository (``git_available`` records which).

``hotspots`` ranks files by normalised churn x complexity (0-100). Hotspots
are where debt accrues the highest interest: complex code the team keeps
having to change. Scouts and the synthesis step use this list to prioritise.

v2 (spec 4.2) adds path classes on every entry (tests, generated, vendored,
docs, source), an ``artefacts`` block for the files the extension map skips
(manifests, lockfiles, CI, containers, IaC, SQL, notebooks, model binaries,
config, governance), and a conditional ignore: ``bin/`` and ``build/`` are
skipped unless they hold a manifest. ``.tech-debt.yaml`` at the root is never
an artefact. ``LANG_COMMENT`` is the comment-syntax half of the extension map
that ``patterns.py`` reads; nothing else in the skill is language-aware.
"""
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

# Skipped unless the directory itself holds a manifest (spec 4.2): a `bin/`
# that is a CLI package or a `build/` that is a Gradle module is real source.
CONDITIONAL_IGNORE: tuple[str, ...] = ("bin", "build")

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


def _git_churn(root: Path, months: int) -> dict[str, int] | None:
    """Mine per-file commit counts from git history inside the window.

    Returns None when git is missing, the tree is not a repository, or the
    command fails for any other reason — churn is best-effort, never fatal.
    Paths in the result are relative to ``root`` (forward-slash), matching
    FileEntry.path, even when ``root`` is a subdirectory of the repository.
    """
    cmd = [
        "git",
        "-C",
        str(root),
        "log",
        f"--since={months} months ago",
        "--name-only",
        "--relative",
        "--pretty=format:",
        "--",
        ".",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    counts: dict[str, int] = {}
    for raw in proc.stdout.splitlines():
        path = raw.strip()
        if path:
            counts[path] = counts.get(path, 0) + 1
    return counts


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


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a file inventory for tech-debt-scan")
    parser.add_argument("path", help="repo root to scan")
    parser.add_argument("--out", default=".tech-debt/inventory.json", help="output JSON path")
    parser.add_argument(
        "--churn-months",
        type=int,
        default=DEFAULT_CHURN_MONTHS,
        help="git-history window (months) for per-file churn counts",
    )
    args = parser.parse_args(argv)

    try:
        inv = walk_inventory(Path(args.path), churn_months=args.churn_months)
    except InventoryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(inv, indent=2), encoding="utf-8")
    hot = len(cast("list[dict[str, object]]", inv["hotspots"]))
    git_note = "git churn on" if inv["git_available"] else "no git history"
    print(
        f"wrote {out_path} ({inv['total_files']} files, {inv['total_loc']} LOC, "
        f"{hot} hotspots, {git_note})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
