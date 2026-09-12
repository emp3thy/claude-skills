"""Definition-name index for the concerns scout (spec 2026-09-12, section 4).

A deterministic map of the repository the concerns scout reads instead of file
leads: per-directory aggregates (copied from ``coupling.json``, where the
reference graph already writes them), and the definition names that recur
across directories. A name defined in at least two source files across at
least two directories is a candidate for scattered or duplicated
functionality; the scout reads to confirm candidates, not to discover them,
which is what bounds its cost on a large repository -- by candidate count, not
by file count.

Names are extracted with a per-language regex table over definition lines and
normalised so ``computeTotal``, ``compute_total`` and ``ComputeTotal`` are one
key. A stoplist removes language idioms and per-adapter verbs (one
``parse_<format>`` per format is a pattern, not scatter). At most 40
candidates are kept, ranked by directory count then hotspot share.

Reads ``inventory.json`` and ``coupling.json``; writes ``concern-index.json``.
Exit 2 when ``coupling.json`` carries no ``edges`` -- that document was written
by an older ``inventory.py`` and the chain must be re-run from step 1.

Direct-path invocable: ``python scripts/concern_index.py <repo> --workdir .tech-debt``.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Final

from inventory import write_json

SCHEMA_VERSION: Final[int] = 1
MAX_CANDIDATES: Final[int] = 40
MIN_FILES: Final[int] = 2
MIN_DIRECTORIES: Final[int] = 2

# Language idioms that recur everywhere, and per-adapter verbs that name one
# implementation per backend by design. Compared against the normalised key.
STOPLIST: Final[frozenset[str]] = frozenset({
    "main", "init", "new", "run", "setup", "teardown", "test", "str", "repr",
    "normalise", "normalize", "parse", "load", "render", "handle", "build",
})

_PY: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\("),
    re.compile(r"^\s*class\s+(\w+)\b"),
)
_JS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w+)\s*\("),
    re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+(\w+)\b"),
    re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*(?::[^=]+)?=\s*(?:async\s*)?\("),
)
_GO: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?(\w+)\s*\("),
)
_RUST: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+(\w+)\s*[<(]"),
    re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:struct|enum|trait)\s+(\w+)\b"),
    re.compile(r"^\s*impl(?:<[^>]*>)?\s+(?:\w+\s+for\s+)?(\w+)\b"),
)
_CLIKE: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(
        r"^\s*(?:public|private|protected|internal)\s+(?:static\s+)?(?:async\s+)?"
        r"(?:[\w<>\[\],.?]+\s+)+(\w+)\s*\("
    ),
)
DEFINITION_TABLE: Final[dict[str, tuple[re.Pattern[str], ...]]] = {
    "python": _PY,
    "javascript": _JS,
    "typescript": _JS,
    "go": _GO,
    "rust": _RUST,
    "java": _CLIKE,
    "csharp": _CLIKE,
}

_CAMEL_RE: Final[re.Pattern[str]] = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def definition_names(language: str, text: str) -> list[str]:
    """Every definition name in ``text`` for ``language``, in order; [] for unknown languages."""
    patterns = DEFINITION_TABLE.get(language)
    if not patterns:
        return []
    out: list[str] = []
    for line in text.splitlines():
        for pattern in patterns:
            match = pattern.match(line)
            if match:
                out.append(match.group(1))
                break
    return out


def normalise_name(raw: str) -> str:
    """``computeTotal``, ``compute_total`` and ``ComputeTotal`` all become ``compute_total``."""
    parts: list[str] = []
    for chunk in raw.strip("_").split("_"):
        if chunk:
            parts.extend(p.lower() for p in _CAMEL_RE.split(chunk) if p)
    return "_".join(parts)


def _dirname(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else ""


def build_concern_index(
    root: Path, inventory: dict[str, Any], coupling: dict[str, Any]
) -> dict[str, Any]:
    """The index document (see the module docstring)."""
    band = {str(p) for p in inventory.get("hotspot_band") or []}
    coupled_pairs = {
        frozenset((str(p.get("a")), str(p.get("b")))) for p in coupling.get("pairs") or []
    }
    by_key: dict[str, dict[str, Any]] = {}
    scanned = 0
    for entry in inventory.get("files") or []:
        if entry.get("path_class") != "source" or entry.get("skipped_large"):
            continue
        language = str(entry.get("language") or "")
        if language not in DEFINITION_TABLE:
            continue
        rel = str(entry["path"])
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        for raw in definition_names(language, text):
            key = normalise_name(raw)
            if not key or key in STOPLIST:
                continue
            slot = by_key.setdefault(key, {"raw": set(), "files": set()})
            slot["raw"].add(raw)
            slot["files"].add(rel)

    candidates: list[dict[str, Any]] = []
    for key, slot in by_key.items():
        files = sorted(slot["files"])
        directories = sorted({_dirname(f) for f in files})
        if len(files) < MIN_FILES or len(directories) < MIN_DIRECTORIES:
            continue
        hotspot_share = sum(1 for f in files if f in band) / len(files)
        coupled = any(
            frozenset((x, y)) in coupled_pairs
            for i, x in enumerate(files) for y in files[i + 1:]
        )
        candidates.append({
            "name": key,
            "tokens": sorted(slot["raw"]),
            "files": files,
            "directories": directories,
            "hotspot_touch": hotspot_share > 0,
            "hotspot_share": round(hotspot_share, 3),
            "coupled": coupled,
        })
    candidates.sort(key=lambda c: (-len(c["directories"]), -c["hotspot_share"], c["name"]))
    kept = candidates[:MAX_CANDIDATES]
    return {
        "schema_version": SCHEMA_VERSION,
        "directories": list(coupling.get("directories") or []),
        "candidates": kept,
        "stats": {"files_scanned": scanned, "names_seen": len(by_key), "candidates": len(kept)},
    }


def _read(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_bytes())
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} is not a JSON object")
    return loaded


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Index recurring definition names for the concerns scout"
    )
    parser.add_argument("repo", type=Path, help="repository root")
    parser.add_argument("--workdir", type=Path, default=Path(".tech-debt"))
    args = parser.parse_args(argv)
    try:
        inventory = _read(args.workdir / "inventory.json")
        coupling = _read(args.workdir / "coupling.json")
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if "edges" not in coupling:
        print(
            f"error: {args.workdir / 'coupling.json'} has no edges; it was written by an "
            "older inventory.py -- re-run the chain from step 1",
            file=sys.stderr,
        )
        return 2
    doc = build_concern_index(args.repo.resolve(), inventory, coupling)
    out = args.workdir / "concern-index.json"
    write_json(out, doc)
    print(f"wrote {out} ({doc['stats']['candidates']} candidate(s) from "
          f"{doc['stats']['files_scanned']} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
