"""Doc inventory: which tracked markdown files are in scope, and why the rest are not.

Writes ``inventory.json``: ``docs`` (in scope), ``excluded`` and ``skipped`` (both
``{"path", "reason"}`` sorted by path), ``files`` (every tracked path) and ``never_edit_re``.
Exclusions are checked in the order of spec section 4; the first match is the recorded reason.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from dd_common import EXIT_OK, EXIT_REFUSED, MAX_DOC_BYTES, StepError, run_git, write_json
from dd_config import load_config
from dd_extract import parse_marker
from dd_md_scan import scan

DEFAULT_NEVER_EDIT = (
    r"(?i)\b(why|rationale|decision|decisions|history|roadmap|deprecated|deprecation"
    r"|migration|changelog|release notes|license|licence)\b"
)

# Copied verbatim from tech-debt-scan scripts/inventory.py (PATH_CLASS_GLOBS); the "docs"
# tuple is not used here. Matched with fnmatchcase against the relative path and the basename.
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
}
PATH_CLASS_ORDER: tuple[str, ...] = ("vendored", "generated", "tests")

EXCLUDED_PATH_GLOBS: tuple[str, ...] = (
    "docs/superpowers/**",
    ".superpowers/**",
    "docs/research/**",
    "**/research_notes/**",
    "**/archive/**",
    "**/adr/**",
    "**/adrs/**",
    "**/decisions/**",
    "**/rfcs/**",
    "**/rfc/**",
)
LIBRARY_DIRS: frozenset[str] = frozenset(
    {"libraries", "extern", "external", "third_party", "deps"}
)
LIBRARY_MANIFESTS: tuple[str, ...] = (
    "package.json", "pyproject.toml", "setup.py", "Cargo.toml", "go.mod", "library.json",
    "library.properties", "CMakeLists.txt",
)
IGNORED_DIRS: frozenset[str] = frozenset(
    {"node_modules", ".venv", "venv", "site-packages", "dist", "target", ".tox", "__pycache__"}
)
CONDITIONAL_IGNORED_DIRS: frozenset[str] = frozenset({"build", "bin"})
# Copied from tech-debt-scan scripts/inventory.py MANIFEST_NAMES.
MANIFEST_NAMES: tuple[str, ...] = (
    "package.json", "pyproject.toml", "requirements*.txt", "go.mod", "Cargo.toml",
    "Gemfile", "*.csproj", "pom.xml", "build.gradle*",
)
# Exact conventional stems (before the first dot) match case-insensitively; the reason uses
# the spec glob, or the bare name for the hyphen variants the spec does not list.
BASENAME_STEMS: dict[str, str] = {
    "CHANGELOG": "CHANGELOG*", "CHANGES": "CHANGES*", "HISTORY": "HISTORY*",
    "RELEASE_NOTES": "RELEASE_NOTES*", "RELEASE-NOTES": "RELEASE-NOTES",
    "LICENSE": "LICENSE*", "LICENCE": "LICENCE*", "NOTICE": "NOTICE*", "COPYING": "COPYING*",
    "CODE_OF_CONDUCT": "CODE_OF_CONDUCT*", "CODE-OF-CONDUCT": "CODE-OF-CONDUCT",
    "SECURITY": "SECURITY*", "AUTHORS": "AUTHORS*", "CONTRIBUTORS": "CONTRIBUTORS*",
    "MAINTAINERS": "MAINTAINERS*",
}
EXCLUDED_BASENAMES: tuple[str, ...] = (
    "CHANGELOG*", "CHANGES*", "HISTORY*", "RELEASE_NOTES*", "LICENSE*", "LICENCE*", "NOTICE*",
    "COPYING*", "CODE_OF_CONDUCT*", "SECURITY*", "AUTHORS*", "CONTRIBUTORS*", "MAINTAINERS*",
    "CODEOWNERS",
)
TEMPLATE_DIRS: frozenset[str] = frozenset({"templates", "template", "skeleton"})
HEADER_MARKERS: tuple[str, ...] = ("DO NOT EDIT", "Code generated")

MODE_GITLINK = "160000"
MODE_SYMLINK = "120000"
BINARY_SNIFF_BYTES = 1024


def _glob_regex(pattern: str) -> re.Pattern[str]:
    """Translate a gitignore-style glob (``*``, ``?``, ``**``, ``[...]``) to a regex."""
    out: list[str] = []
    i, n = 0, len(pattern)
    while i < n:
        ch = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("/**", i) and i + 3 == n:
            out.append("/.*")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif ch == "*":
            out.append("[^/]*")
            i += 1
        elif ch == "?":
            out.append("[^/]")
            i += 1
        elif ch == "[":
            end = pattern.find("]", i + 2)
            if end == -1:
                out.append(re.escape(ch))
                i += 1
            else:
                body = pattern[i + 1 : end]
                if body.startswith("!"):
                    body = "^" + body[1:]
                out.append("[" + body.replace("\\", "\\\\") + "]")
                i = end + 1
        else:
            out.append(re.escape(ch))
            i += 1
    return re.compile("".join(out), re.DOTALL)


def _glob_matches(pattern: str, rel: str) -> bool:
    """Git's rule: no ``/`` matches the basename at any depth, else anchored at the root."""
    pat = pattern.rstrip("/") if pattern != "/" else pattern
    if "/" not in pat:
        return _glob_regex(pat).fullmatch(rel.rsplit("/", 1)[-1]) is not None
    return _glob_regex(pat.lstrip("/")).fullmatch(rel) is not None


def _config_glob_matches(pattern: str, rel: str) -> bool:
    if _glob_matches(pattern, rel):
        return True
    pat = pattern.rstrip("/")
    if "/" in pat:  # a directory pattern covers its contents
        return any(_glob_matches(pat, ancestor) for ancestor in _ancestors(rel))
    if pat:  # a bare directory name excludes everything beneath it
        regex = _glob_regex(pat)
        return any(regex.fullmatch(part) for part in rel.split("/")[:-1])
    return False


def _classify(rel: str) -> str | None:
    name = rel.rsplit("/", 1)[-1]
    for cls in PATH_CLASS_ORDER:
        for glob in PATH_CLASS_GLOBS[cls]:
            if fnmatchcase(rel, glob) or fnmatchcase(name, glob):
                return cls
    return None


def _parse_gitattributes(text: str) -> list[tuple[str, dict[str, bool | None]]]:
    rules: list[tuple[str, dict[str, bool | None]]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        pattern, attrs = parts[0], parts[1:]
        if pattern.endswith("/"):  # attributes never apply to directories
            continue
        state: dict[str, bool | None] = {}
        for attr in attrs:
            name, _, value = attr.partition("=")
            if name.startswith("-") and not value:
                state[name[1:]] = False
            elif name.startswith("!") and not value:
                state[name[1:]] = None
            elif value:
                state[name] = value.lower() not in ("false", "0", "unset")
            else:
                state[name] = True
        rules.append((pattern, state))
    return rules


def _linguist_reason(rules: list[tuple[str, dict[str, bool | None]]], rel: str) -> str | None:
    """Return ``gitattributes:linguist-generated`` or ``...-vendored`` for ``rel``, if set."""
    final: dict[str, bool | None] = {}
    for pattern, state in rules:
        if _glob_matches(pattern, rel):
            final.update(state)
    for attr in ("linguist-generated", "linguist-vendored"):
        if final.get(attr):
            return f"gitattributes:{attr}"
    return None


def _toml_name(text: str, sections: tuple[str, ...]) -> str | None:
    current = ""
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("["):
            current = line.strip("[] ")
            continue
        if current in sections:
            match = re.match(r"""name\s*=\s*["']([^"']+)["']""", line)
            if match:
                return match.group(1)
    return None


def _manifest_name(manifest: str, text: str) -> str | None:
    """The project name a manifest declares, or None when it cannot be read."""
    if manifest in ("package.json", "library.json"):
        try:
            data = json.loads(text)
        except ValueError:
            return None
        name = data.get("name") if isinstance(data, dict) else None
        return name if isinstance(name, str) else None
    if manifest == "pyproject.toml":
        return _toml_name(text, ("project", "tool.poetry"))
    if manifest == "Cargo.toml":
        return _toml_name(text, ("package",))
    if manifest == "go.mod":
        match = re.search(r"^module\s+(\S+)", text, re.MULTILINE)
        return match.group(1) if match else None
    if manifest == "library.properties":
        match = re.search(r"^name\s*=\s*(.+?)\s*$", text, re.MULTILINE)
        return match.group(1) if match else None
    if manifest == "setup.py":
        match = re.search(r"""\bname\s*=\s*["']([^"']+)["']""", text)
        return match.group(1) if match else None
    if manifest == "CMakeLists.txt":
        match = re.search(r"^\s*project\s*\(\s*([^\s)]+)", text, re.MULTILINE | re.IGNORECASE)
        return match.group(1) if match else None
    return None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _is_license_name(name: str) -> bool:
    return name.upper().startswith(("LICENSE", "LICENCE"))


def _has_cmake_project(text: str) -> bool:
    return re.search(r"^\s*project\s*\(", text, re.MULTILINE | re.IGNORECASE) is not None


def _nested_libraries(root: Path, files: list[str]) -> set[str]:
    """Directories below the root holding a LICENSE* and a manifest naming another project."""
    by_dir: dict[str, set[str]] = {}
    for rel in files:
        directory, _, name = rel.rpartition("/")
        by_dir.setdefault(directory, set()).add(name)
    root_name: str | None = None
    for manifest in LIBRARY_MANIFESTS:
        if manifest in by_dir.get("", set()):
            root_name = _manifest_name(manifest, _read_text(root / manifest))
            if root_name:
                break
    found: set[str] = set()
    for directory, names in by_dir.items():
        if not directory or not any(_is_license_name(n) for n in names):
            continue
        for manifest in LIBRARY_MANIFESTS:
            if manifest not in names:
                continue
            text = _read_text(root / directory / manifest)
            if manifest == "CMakeLists.txt" and not _has_cmake_project(text):
                continue
            declared = _manifest_name(manifest, text)
            if declared is None or declared != root_name:
                found.add(directory)
            break
    return found


def _ancestors(rel: str) -> list[str]:
    parts = rel.split("/")[:-1]
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


def _ls_files(root: Path) -> tuple[list[str], set[str], set[str]]:
    """Return (tracked paths, gitlink paths, symlink paths) from ``git ls-files -s -z``."""
    out = run_git(root, ["ls-files", "-s", "-z"])
    if out is None:
        raise StepError(f"{root}: not a git repository or git ls-files failed", EXIT_REFUSED)
    paths: set[str] = set()
    gitlinks: set[str] = set()
    symlinks: set[str] = set()
    for entry in out.split("\0"):
        if not entry:
            continue
        meta, _, path = entry.partition("\t")
        mode = meta.split(" ", 1)[0]
        paths.add(path)
        if mode == MODE_GITLINK:
            gitlinks.add(path)
        elif mode == MODE_SYMLINK:
            symlinks.add(path)
    return sorted(paths), gitlinks, symlinks


def _gitmodules_paths(root: Path) -> set[str]:
    text = _read_text(root / ".gitmodules")
    return {m.group(1).strip() for m in re.finditer(r"^\s*path\s*=\s*(.+)$", text, re.MULTILINE)}


def _combine_never_edit(extra: str | None) -> str:
    """OR the config regex onto the default, keeping each part's own leading flags scoped."""
    if not extra:
        return DEFAULT_NEVER_EDIT

    def scoped(pattern: str) -> str:
        match = re.match(r"\(\?([aiLmsux]+)\)", pattern)
        if match:  # a global flag group is illegal mid-pattern since Python 3.11
            return f"(?{match.group(1)}:{pattern[match.end():]})"
        return pattern

    return f"(?:{scoped(DEFAULT_NEVER_EDIT)})|(?:{scoped(extra)})"


class _Inventory:
    def __init__(self, root: Path, files: list[str], gitlinks: set[str], config: dict[str, Any]):
        self.root = root
        self.config = config
        self.submodules = gitlinks | _gitmodules_paths(root)
        self.dir_files: dict[str, set[str]] = {}
        for rel in files:
            directory, _, base = rel.rpartition("/")
            self.dir_files.setdefault(directory, set()).add(base)
        self.libraries = _nested_libraries(root, files)
        self.attrs = _parse_gitattributes(_read_text(root / ".gitattributes"))
        self._text: dict[str, str | None] = {}

    def _content(self, rel: str) -> str | None:
        if rel not in self._text:
            self._text[rel] = self._decode(rel)[0]
        return self._text[rel]

    def _decode(self, rel: str) -> tuple[str | None, str | None]:
        """Return (text, skip_reason)."""
        path = self.root / rel
        try:
            size = path.stat().st_size
            if size > MAX_DOC_BYTES:
                return None, "too-large"
            data = path.read_bytes()
        except OSError:
            return None, "unreadable"
        if b"\0" in data[:BINARY_SNIFF_BYTES]:
            return None, "binary"
        try:
            return data.decode("utf-8"), None
        except UnicodeDecodeError:
            return None, "not-utf8"

    def skip_reason(self, rel: str) -> str | None:
        return self._decode(rel)[1]

    # Each check returns a reason string or None. Order follows spec section 4.
    def _paths(self, rel: str) -> str | None:
        for glob in EXCLUDED_PATH_GLOBS:
            if _glob_matches(glob, rel):
                return f"path:{glob}"
        return None

    def _ignored_dir(self, rel: str) -> str | None:
        for directory in _ancestors(rel):
            name = directory.rsplit("/", 1)[-1]
            if name in IGNORED_DIRS:
                return f"ignored-dir:{name}"
            if name in CONDITIONAL_IGNORED_DIRS:
                names = self.dir_files.get(directory, set())
                if not any(fnmatchcase(n, m) for n in names for m in MANIFEST_NAMES):
                    return f"ignored-dir:{name}"
        return None

    def _vendored_library(self, rel: str) -> str | None:
        ancestors = _ancestors(rel)
        for directory in ancestors:
            if directory in self.libraries:
                return f"vendored-library:{directory}"
            if directory.rsplit("/", 1)[-1] in LIBRARY_DIRS:
                return f"vendored-library:{directory}"
        return None

    def _basename(self, rel: str) -> str | None:
        name = rel.rsplit("/", 1)[-1]
        stem = BASENAME_STEMS.get(name.split(".", 1)[0].upper())
        if stem:
            return f"basename:{stem}"
        for glob in EXCLUDED_BASENAMES:
            if fnmatchcase(name, glob):
                return f"basename:{glob}"
        return None

    def _class(self, rel: str) -> str | None:
        cls = _classify(rel)
        return f"class:{cls}" if cls else None

    def _gitattributes(self, rel: str) -> str | None:
        return _linguist_reason(self.attrs, rel)

    def _header(self, rel: str) -> str | None:
        text = self._content(rel)
        if text is None:
            return None
        head = "\n".join(text.splitlines()[:5])
        return "header:do-not-edit" if any(m in head for m in HEADER_MARKERS) else None

    def _submodule(self, rel: str) -> str | None:
        for sub in sorted(self.submodules):
            if rel == sub or rel.startswith(sub + "/"):
                return f"submodule:{sub}"
        return None

    def _template(self, rel: str) -> str | None:
        parts = rel.split("/")
        for part in parts[:-1]:
            if part in TEMPLATE_DIRS or part.startswith("cookiecutter"):
                return "template"
        return "template" if parts[-1].lower().endswith(".tmpl.md") else None

    def _marker(self, rel: str) -> str | None:
        """The file marker is read from the body of a real HTML comment (dd_md_scan's Comment
        list), so a marker quoted in inline code or a fence, as docs about the marker do, is
        not one (ruling R55). Ruling R66: only a file marker with a reason excludes the doc;
        one with no colon or an empty reason is reported by extraction as a marker without a
        reason."""
        text = self._content(rel)
        if text is None:
            return None
        for comment in scan(text).comments:
            parsed = parse_marker(comment.body)
            if parsed is not None and parsed[0] == "drift-ignore-file" and parsed[1]:
                return f"marker:{parsed[1]}"
        return None

    def _config(self, rel: str) -> str | None:
        for glob in self.config.get("exclude") or []:
            if _config_glob_matches(glob, rel):
                return f"config:{glob}"
        return None

    def exclusion(self, rel: str) -> str | None:
        checks: tuple[Callable[[str], str | None], ...] = (
            self._paths,
            self._ignored_dir,
            self._vendored_library,
            self._basename,
            self._class,
            self._gitattributes,
            self._header,
            self._submodule,
            self._template,
            self._marker,
            self._config,
        )
        for check in checks:
            reason = check(rel)
            if reason:
                return reason
        return None


def run(root: Path, workdir: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Build the inventory for ``root``, write ``workdir/inventory.json`` and return it."""
    files, gitlinks, symlinks = _ls_files(root)
    inv = _Inventory(root, files, gitlinks, config)
    docs: list[str] = []
    excluded: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    for rel in files:
        if not rel.lower().endswith(".md"):
            continue
        if rel in symlinks:
            skipped.append({"path": rel, "reason": "symlink"})
            continue
        reason = inv.exclusion(rel)
        if reason:
            excluded.append({"path": rel, "reason": reason})
            continue
        skip = inv.skip_reason(rel)
        if skip:
            skipped.append({"path": rel, "reason": skip})
        else:
            docs.append(rel)
    result = {
        "docs": sorted(docs),
        "excluded": sorted(excluded, key=lambda e: e["path"]),
        "skipped": sorted(skipped, key=lambda e: e["path"]),
        "files": files,
        "never_edit_re": _combine_never_edit(config.get("never_edit_heading")),
    }
    write_json(workdir / "inventory.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory the markdown docs in scope.")
    parser.add_argument("repo", type=Path)
    parser.add_argument("--workdir", type=Path, required=True)
    args = parser.parse_args(argv)
    root: Path = args.repo
    config, warnings = load_config(root)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    try:
        run(root, args.workdir, config)
    except StepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
