"""Docs-block signals for ``inventory.py`` (spec 4.2 "Docs block").

``docs_block`` is the sole public entry point, called once per scan from
``inventory.build_all``: README/CONTRIBUTING/ADR/CHANGELOG presence, the
latest git tag, dangling references in docs-class files, and doc staleness
versus the newest source file's ``last_touched``.

A doc reference is a backtick-quoted or path-like token that either carries a
known code or config extension or starts with an existing top-level
directory; it is dangling when no walked path equals it, ends with it, or
lives under it and its stem is not a source stem (capped at
``MAX_DANGLING_REFS``). Staleness is how many whole calendar days a doc lags
the newest source file (time-of-day ignored), and 0 when the doc is the newer
of the two: a document written after the last code change is not stale.

Extracted out of ``inventory.py`` (which stays under the plan's ~700-line
split guidance) since these helpers have exactly one caller, ``build_all``,
via ``docs_block``. ``read_head`` is kept public because ``inventory.py``'s
own ``_tests_block``/``_tooling_blocks`` reuse the same small file-head
reader; everything else here is private. ``inventory.EXT_TO_LANG`` is the
skill's one language-aware table (spec 0(d)), so its key set is never
duplicated here: ``docs_block`` takes the code-extension set as the
keyword-only ``code_exts`` parameter, and ``inventory.build_all`` passes
``frozenset(EXT_TO_LANG)`` at its single call site. ``FileEntry`` is only
imported under ``TYPE_CHECKING`` (to avoid an ``inventory`` <->
``docs_signals`` import cycle: ``inventory.py`` imports ``docs_block`` at
module load time, before ``FileEntry`` would be defined if the import ran
the other way): these functions never construct or isinstance-check it,
only read attributes duck-typed at runtime.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

from reference_graph import file_stem

if TYPE_CHECKING:
    from pathlib import Path

    from inventory import FileEntry

_README_NAMES = ("readme.md", "readme.rst", "readme.adoc", "readme.txt", "readme")
_CONTRIBUTING_NAMES = ("contributing.md", "contributing.rst", "docs/contributing.md")
_CHANGELOG_NAMES = ("changelog.md", "changes.md", "history.md", "changelog.rst", "changelog")
_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
_PATHLIKE_RE = re.compile(r"(?<![\w./-])[\w.-]+(?:/[\w.-]+)+")

# Non-code extensions a doc reference may also carry, added to the caller's
# ``code_exts`` (inventory.EXT_TO_LANG's keys) to build the full set.
_EXTRA_DOC_REF_EXTS = frozenset(
    {".yml", ".yaml", ".json", ".toml", ".ini", ".cfg", ".sh", ".ps1", ".sql", ".txt"}
)
MAX_DANGLING_REFS = 200


def read_head(path: Path, limit: int = 65536) -> str:
    """Decode up to ``limit`` bytes of ``path`` as UTF-8 (best-effort, never raises)."""
    try:
        with path.open("rb") as handle:
            return handle.read(limit).decode("utf-8", errors="ignore")
    except OSError:
        return ""


def _doc_lag_days(doc: str | None, newest_source: str | None) -> int | None:
    """Whole calendar days ``doc`` lags ``newest_source``; 0 when the doc is the newer."""
    if not doc or not newest_source:
        return None
    try:
        doc_at = datetime.fromisoformat(doc)
        source_at = datetime.fromisoformat(newest_source)
    except ValueError:
        return None
    return max(0, (source_at.date() - doc_at.date()).days)


def _looks_like_ref(token: str, top_level: set[str], doc_ref_exts: frozenset[str]) -> bool:
    if "://" in token or token.startswith(("http:", "https:")):
        return False
    lowered = token.lower()
    if lowered.endswith(tuple(doc_ref_exts)):
        return True
    return "/" in token and token.split("/", 1)[0] in top_level


def _ref_exists(token: str, all_paths: set[str], source_stems: set[str]) -> bool:
    clean = token.removeprefix("./").rstrip("/")
    if clean in all_paths or file_stem(clean) in source_stems:
        return True
    return any(p.endswith("/" + clean) or p.startswith(clean + "/") for p in all_paths)


def docs_block(
    entries: list[FileEntry],
    artefacts: dict[str, list[dict[str, Any]]],
    texts: dict[str, str],
    git_block: dict[str, Any],
    git_available: bool,
    *,
    code_exts: frozenset[str],
) -> dict[str, Any]:
    doc_ref_exts = code_exts | _EXTRA_DOC_REF_EXTS
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
                if not token or not _looks_like_ref(token, top_level, doc_ref_exts):
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
                _doc_lag_days(entry.last_touched, newest_source) if git_available else None
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
