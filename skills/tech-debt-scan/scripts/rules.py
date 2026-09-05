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

An artefact's ``path_class`` (spec 4.2) decides whether it is scanned at all:
a Dockerfile, workflow, manifest or config under a tests, vendored or
generated tree is fixture material and never becomes a finding, and an
artefact the inventory marked ``skipped_large`` is never read at all, so
``rules.py`` reads only what the inventory would have read. Every finding
copies the artefact's path class into ``signals.path_class`` for the merge
to weigh.

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
from inventory import MAX_SCAN_BYTES, NUL_SNIFF_BYTES, write_json
from redaction import redact

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
# Path classes on which every family is disabled (spec 4.2): a Dockerfile or
# workflow under a tests, vendored or generated tree is fixture material, not
# the repository's own pipeline, so it never becomes a finding.
DISABLED_PATH_CLASSES: Final[frozenset[str]] = frozenset({"tests", "vendored", "generated"})
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
    """Read ``rel`` under the inventory's own size guard (spec 4.2).

    A file over ``MAX_SCAN_BYTES``, or with a NUL byte in its first
    ``NUL_SNIFF_BYTES``, is never decoded: it reads as empty text, exactly as
    ``inventory.py`` saw it.
    """
    path = root / rel
    try:
        if path.stat().st_size > MAX_SCAN_BYTES:
            return ""
        with path.open("rb") as handle:
            head = handle.read(NUL_SNIFF_BYTES)
            if b"\x00" in head:
                return ""
            return (head + handle.read()).decode("utf-8", errors="replace")
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


def _disabled(artefact: dict[str, Any]) -> bool:
    """True when rules.py must not look at this artefact at all (spec 4.2).

    Either its path class disables every family on it, or the inventory's size
    guard marked it ``skipped_large`` and never read it.
    """
    if artefact.get("skipped_large"):
        return True
    return str(artefact.get("path_class")) in DISABLED_PATH_CLASSES


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
    raw_steps = job.get("steps")
    steps: list[Any] = raw_steps if isinstance(raw_steps, list) else []
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
    manifests = [str(a["path"]) for a in artefacts.get("manifest", []) if not _disabled(a)]
    config_entries = {
        str(a["path"]): a for a in artefacts.get("config", []) if not _disabled(a)
    }
    configs = set(config_entries)
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
                "quote": redact(_first_line(_read(root, setup))),
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
                "quote": redact(_first_line(_read(root, rel))),
                "path_class": str(config_entries[rel]["path_class"]),
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
        gaps = [(b - a).days for a, b in zip(dates, dates[1:], strict=False) if a and b]
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
    for entries in (inventory.get("artefacts") or {}).values():
        for artefact in entries:
            if artefact["path"] == path:
                signals["churn"] = artefact["churn"]
                signals["path_class"] = artefact.get("path_class")
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
        "title": redact(title)[:80],
        "severity": max(h.severity for h in hits),
        "effort": effort,
        "source": "rule",
        "rule_id": primary.rule_id,
        "note": redact("; ".join(h.note for h in hits))[:300],
        "evidence": [
            {"file": h.file, "line_start": h.line, "line_end": h.line, "quote": redact(h.quote),
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
            if _disabled(artefact):
                continue
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
