"""Pure normalisers turning one tool's output into signals (spec 4.5).

Every function here takes an already-parsed payload and the repository root
and returns a list of ``Signal`` dicts. Nothing in this module runs a
subprocess, reads a file or touches config, so each normaliser is testable
from a captured payload with nothing mocked; ``tools_probe.py`` owns every
side effect.

Signals are the probe's whole vocabulary. ``fact`` marks a signal a human
would accept without a second opinion -- a published vulnerability, a
committed secret, a Dockerfile rule -- and only fact-class signals may
become candidates in phase 4b. Everything else is a lead or corroboration.

No field that can carry source text or a credential is ever copied into a
signal. gitleaks reports the matched secret in ``Secret`` and ``Match`` and
jscpd reports the duplicated source in ``fragment``; both are dropped rather
than redacted, because a redacted secret is still its own first four
characters while a dropped one is nothing (spec 4.5).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final, TypedDict


class Signal(TypedDict):
    """One normalised observation from one tool."""

    tool: str
    family: str
    kind: str
    file: str | None
    line_start: int | None
    line_end: int | None
    message: str
    fact: bool
    extra: dict[str, Any]


# Every family a normaliser may assign. Checked against categories.FAMILIES by
# a test: a family name the skill does not know would reach candidates in 4b
# and match nothing there.
SIGNAL_FAMILIES: Final[frozenset[str]] = frozenset(
    {
        "complex-units", "dead-code", "dependency-debt", "duplication",
        "error-masking", "architecture", "security", "pipeline-infra",
    }
)

KINDS: Final[frozenset[str]] = frozenset(
    {
        "vuln", "secret", "clone", "cycle", "unused", "deprecated",
        "complexity", "error-masking", "dockerfile", "workflow",
    }
)


def rel_path(root: Path, raw: Any) -> str | None:
    """``raw`` as a root-relative forward-slashed path, or None if unusable.

    Tools disagree about path shape and ruff reports an absolute path with
    backslashes even for relative input, so an absolute path under ``root``
    is relativised rather than rejected. This is the one deliberate
    difference from ``merge_findings._normalise_path``, which rejects every
    absolute path because a scout must never cite one.

    A colon in *any* segment is rejected, not just in the first. The first-
    segment rule existed to reject a Windows drive letter, and a legitimate
    Windows absolute path under ``root`` never reaches it because the
    relativisation above has already removed the drive prefix. What the
    narrower rule let through was a pseudo-path: jscpd names a code block
    embedded in a document ``<path>.md:<format>``, and 1,879 of 3,267 signals
    from a scan of this repository -- 57% -- cited such a path, which no
    consumer can open. The chosen rule is "reject what cannot be a real file"
    rather than "check the file exists", because this module reads nothing
    from disk: every normaliser stays testable from a captured payload, and a
    path that is valid today can be deleted tomorrow without the signal
    becoming retrospectively malformed.

    One known consequence, recorded here for phase 4b rather than papered
    over: osv-scanner reports a docker image or a git remote in
    ``results[].source.path``, and those carry colons. They are dropped by
    this rule, which is correct for a field that is supposed to name a file
    on disk -- but when 4b consumes osv-scanner's output, a non-file source
    needs its own labelled route rather than a widened path rule here.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.replace("\\", "/").strip()
    root_text = str(root).replace("\\", "/").rstrip("/")
    if root_text and (text == root_text or text.lower().startswith(root_text.lower() + "/")):
        text = text[len(root_text) + 1 :]
    while text.startswith("./"):
        text = text[2:]
    if not text:
        return None
    segments = text.split("/")
    if text.startswith("/") or ".." in segments or any(":" in part for part in segments):
        return None
    return text


def signal(
    tool: str,
    family: str,
    kind: str,
    *,
    file: str | None,
    line_start: int | None = None,
    line_end: int | None = None,
    message: str,
    fact: bool,
    extra: dict[str, Any] | None = None,
) -> Signal:
    """A ``Signal`` with its kind checked against the spec's closed set."""
    if kind not in KINDS:
        raise ValueError(f"unknown signal kind {kind!r}; spec 4.5 fixes the set")
    if family not in SIGNAL_FAMILIES:
        raise ValueError(f"unknown family {family!r}; categories.FAMILIES fixes the set")
    return Signal(
        tool=tool,
        family=family,
        kind=kind,
        file=file,
        line_start=line_start,
        line_end=line_end,
        message=message,
        fact=fact,
        extra=extra or {},
    )


# ruff rule code -> (family, kind). Codes outside this map are not debt
# signals for our purposes and are dropped rather than guessed at.
RUFF_KINDS: Final[dict[str, tuple[str, str]]] = {
    "E722": ("error-masking", "error-masking"),
    "BLE001": ("error-masking", "error-masking"),
    "S110": ("error-masking", "error-masking"),
    "S112": ("error-masking", "error-masking"),
    "C901": ("complex-units", "complexity"),
    "PLR0911": ("complex-units", "complexity"),
    "PLR0912": ("complex-units", "complexity"),
    "PLR0913": ("complex-units", "complexity"),
    "PLR0915": ("complex-units", "complexity"),
    "F401": ("dead-code", "unused"),
    "UP035": ("dependency-debt", "deprecated"),
}

_VULTURE_LINE: Final[re.Pattern[str]] = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+): (?P<message>.+) \((?P<confidence>\d+)% confidence\)$"
)

# The sub-shape of a vulture message that names a symbol, e.g.
# "unused function 'export_v1'". vulture's reachability messages (unreachable
# code, unsatisfiable conditions) share the outer path:line:...(N% confidence)
# grammar but never match this -- there is no symbol to report, so none is
# invented for them.
_VULTURE_UNUSED: Final[re.Pattern[str]] = re.compile(
    r"^unused (?P<kind>\w+) '(?P<symbol>[^']+)'$"
)


def normalise_ruff(payload: Any, root: Path) -> list[Signal]:
    """ruff's JSON diagnostics as signals.

    ruff reports ``filename`` as an absolute path with backslashes even when
    given a relative one, so every record goes through ``rel_path``. Rule
    codes outside ``RUFF_KINDS`` are dropped: ruff reports far more than debt.
    """
    if not isinstance(payload, list):
        return []
    out: list[Signal] = []
    for record in payload:
        if not isinstance(record, dict):
            continue
        mapping = RUFF_KINDS.get(str(record.get("code")))
        if mapping is None:
            continue
        family, kind = mapping
        rel = rel_path(root, record.get("filename"))
        location = record.get("location") or {}
        end = record.get("end_location") or {}
        start_row, end_row = location.get("row"), end.get("row")
        if rel is None or not isinstance(start_row, int):
            continue
        out.append(
            signal(
                "ruff", family, kind,
                file=rel,
                line_start=start_row,
                line_end=end_row if isinstance(end_row, int) else start_row,
                message=str(record.get("message", "")),
                fact=False,
                extra={"code": str(record["code"])},
            )
        )
    return out


def normalise_vulture(payload: Any, root: Path) -> list[Signal]:
    """vulture's plain-text lines as dead-code signals.

    vulture has no JSON mode. Every finding, regardless of shape, is one line
    of the form ``path:line: <message> (<n>% confidence)``. Most messages are
    ``unused <kind> '<symbol>'``, but vulture also reports unreachable code
    this way -- after a ``return``/``break``/``continue``/``raise``, or an
    always-true ``if``/``while`` branch -- with a message that carries no
    quoted symbol at all (e.g. ``unreachable code after 'return'`` or
    ``unreachable 'else' block``; see vulture's ``reachability.py``). Every
    line matching the outer ``path:line: ...(N% confidence)`` grammar becomes
    a signal; ``symbol``/``symbol_kind`` are added to ``extra`` only when the
    message itself matches the ``unused <kind> '<symbol>'`` shape, so a
    symbol is never invented for a message that never named one. A line that
    does not match the outer grammar at all is still dropped, since there is
    nothing to report. The confidence is carried through as a number so 4b
    can weight a 60% hint below a 100% one.
    """
    if not isinstance(payload, list):
        return []
    out: list[Signal] = []
    for line in payload:
        if not isinstance(line, str):
            continue
        match = _VULTURE_LINE.match(line.strip())
        if match is None:
            continue
        rel = rel_path(root, match.group("file"))
        if rel is None:
            continue
        row = int(match.group("line"))
        message = match.group("message")
        extra: dict[str, Any] = {"confidence": int(match.group("confidence"))}
        unused = _VULTURE_UNUSED.match(message)
        if unused is not None:
            extra["symbol_kind"] = unused.group("kind")
            extra["symbol"] = unused.group("symbol")
        out.append(
            signal(
                "vulture", "dead-code", "unused",
                file=rel, line_start=row, line_end=row,
                message=message,
                fact=False,
                extra=extra,
            )
        )
    return out


# A unit is worth a signal when it is genuinely hard to hold in the head.
# lizard reports every function it parses, so without a threshold a
# medium repository would fill the lead cap with two-line constructors.
LIZARD_MIN_CCN: Final[int] = 10
LIZARD_MIN_NLOC: Final[int] = 60

# lizard --csv writes no header. Columns, in order: NLOC, CCN, token count,
# parameter count, length, "name@start-end@file", file, name, signature,
# start line, end line.
_LIZARD_COLUMNS: Final[int] = 11


def normalise_lizard(payload: Any, root: Path) -> list[Signal]:
    """lizard's CSV rows as complexity signals.

    lizard has no JSON mode and always exits 0, so the rows themselves are
    the only signal that it ran. Only units at or above ``LIZARD_MIN_CCN``
    cyclomatic complexity or ``LIZARD_MIN_NLOC`` lines are reported.
    """
    if not isinstance(payload, list):
        return []
    out: list[Signal] = []
    for row in payload:
        if not isinstance(row, list) or len(row) < _LIZARD_COLUMNS:
            continue
        try:
            nloc, ccn, _tokens, parameters = (int(row[0]), int(row[1]), int(row[2]), int(row[3]))
            start, end = int(row[9]), int(row[10])
        except (TypeError, ValueError):
            continue
        if ccn < LIZARD_MIN_CCN and nloc < LIZARD_MIN_NLOC:
            continue
        rel = rel_path(root, row[6])
        if rel is None:
            continue
        name = str(row[7])
        out.append(
            signal(
                "lizard", "complex-units", "complexity",
                file=rel, line_start=start, line_end=end,
                message=f"{name} has cyclomatic complexity {ccn} over {nloc} lines",
                fact=False,
                extra={"name": name, "ccn": ccn, "nloc": nloc, "parameters": parameters},
            )
        )
    return out


# knip issue category -> (family, kind, singular label for the message).
# Categories outside this map are real knip output but not debt families we
# act on.
#
# ``binaries`` (an npm-script binary knip cannot resolve to an installed
# package) and ``unlisted`` (an import with no corresponding package.json
# dependency) are deliberately absent, even though both are real and
# non-trivial knip output -- confirmed non-empty for ``binaries`` on the
# web-ts corpus fixture itself. Both mean "referenced but never declared",
# the opposite of "unused". Spec 4.5 fixes a closed `kind` vocabulary (vuln,
# secret, clone, cycle, unused, deprecated, complexity, error-masking,
# dockerfile, workflow) with no term for that idea, and phase 4b filters on
# `kind` -- mapping either category to `unused` would be a wrong label, not
# a missing finding, and a wrong label gets acted on. Do not add them back
# without first adding a `kind` for "referenced but undeclared".
KNIP_CATEGORIES: Final[dict[str, tuple[str, str, str]]] = {
    "files": ("dead-code", "unused", "file"),
    "exports": ("dead-code", "unused", "export"),
    "types": ("dead-code", "unused", "type"),
    "enumMembers": ("dead-code", "unused", "enum member"),
    "namespaceMembers": ("dead-code", "unused", "namespace member"),
    "dependencies": ("dependency-debt", "unused", "dependency"),
    "devDependencies": ("dependency-debt", "unused", "devDependency"),
}


def normalise_madge(payload: Any, root: Path) -> list[Signal]:
    """madge's circular-dependency list as architecture signals.

    ``argv_for`` points madge at the repository root, so its paths are
    already root-relative. A cycle is a property of the
    import graph rather than of any line, so the signal carries no line
    range and names the cycle's first file.
    """
    if not isinstance(payload, list):
        return []
    out: list[Signal] = []
    for cycle in payload:
        if not isinstance(cycle, list) or not cycle:
            continue
        members = [rel_path(root, str(item)) for item in cycle]
        kept = [member for member in members if member is not None]
        if not kept:
            continue
        out.append(
            signal(
                "madge", "architecture", "cycle",
                file=kept[0], line_start=None, line_end=None,
                message=f"import cycle through {len(kept)} modules: {' -> '.join(kept)}",
                fact=False,
                extra={"cycle": kept},
            )
        )
    return out


def normalise_jscpd(payload: Any, root: Path) -> list[Signal]:
    """jscpd's duplicate list as duplication signals.

    ``fragment`` holds the duplicated source itself and is never copied into
    a signal, for the same reason gitleaks' ``Secret`` is not: this file is
    read into prompts. ``statistics.detectionDate`` is a wall-clock stamp and
    is likewise never propagated, so a golden of these signals is stable.
    """
    if not isinstance(payload, dict):
        return []
    out: list[Signal] = []
    for duplicate in payload.get("duplicates") or []:
        if not isinstance(duplicate, dict):
            continue
        first, second = duplicate.get("firstFile") or {}, duplicate.get("secondFile") or {}
        first_rel = rel_path(root, first.get("name"))
        second_rel = rel_path(root, second.get("name"))
        if first_rel is None or second_rel is None:
            continue
        first_start, first_end = first.get("start"), first.get("end")
        second_start, second_end = second.get("start"), second.get("end")
        out.append(
            signal(
                "jscpd", "duplication", "clone",
                file=first_rel,
                line_start=first_start if isinstance(first_start, int) else None,
                line_end=first_end if isinstance(first_end, int) else None,
                message=(
                    f"{duplicate.get('lines', 0)} duplicated lines shared with {second_rel}"
                ),
                fact=False,
                extra={
                    "other_file": second_rel,
                    "other_line_start": second_start if isinstance(second_start, int) else None,
                    "other_line_end": second_end if isinstance(second_end, int) else None,
                    "tokens": duplicate.get("tokens"),
                    "format": duplicate.get("format"),
                },
            )
        )
    return out


def normalise_knip(payload: Any, root: Path) -> list[Signal]:
    """knip's issue list as dead-code and dependency signals.

    knip reports per file, with one array per issue category. Without
    ``node_modules`` it reports whole unused files and no exports; with them
    it reports both. Each entry in a mapped category becomes one signal.
    """
    if not isinstance(payload, dict):
        return []
    out: list[Signal] = []
    for issue in payload.get("issues") or []:
        if not isinstance(issue, dict):
            continue
        rel = rel_path(root, issue.get("file"))
        if rel is None:
            continue
        for category, mapping in KNIP_CATEGORIES.items():
            family, kind, singular = mapping
            for entry in issue.get(category) or []:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("name", ""))
                line = entry.get("line")
                row = line if isinstance(line, int) else None
                whole_file = category == "files"
                out.append(
                    signal(
                        "knip", family, kind,
                        file=rel,
                        line_start=None if whole_file else row,
                        line_end=None if whole_file else row,
                        message=(
                            f"unused file {rel}" if whole_file
                            else f"unused {singular} '{name}'"
                        ),
                        fact=False,
                        extra={"issue": category, "symbol": name},
                    )
                )
    return out


# osv-scanner ``source.type`` values that name something other than a file under
# the scanned root: a container image reference or a git remote URL. Both are
# real 4b input (a base-image or a submodule dependency can carry a real
# advisory) but neither is a path ``rel_path`` should ever be asked to resolve.
_OSV_NON_FILE_SOURCE_TYPES: Final[frozenset[str]] = frozenset({"docker", "git"})


def normalise_osv_scanner(payload: Any, root: Path) -> list[Signal]:
    """osv-scanner's results as fact-class dependency signals.

    The JSON carries no line numbers, so the evidence is the manifest or
    lockfile path with a null line range (spec 4.5). One signal per
    vulnerability per package, not one per package, so two advisories against
    one dependency stay separately actionable.

    ``source.path`` is a real repository path when ``source.type`` says it is
    one ("lockfile", "sbom", "directory") -- resolved with ``rel_path`` as
    before, dropped when that fails, exactly as it always was. A "docker"
    (``alpine:3.18``) or "git" (a URL) source is not a path at all -- both
    carry a colon ``rel_path`` correctly rejects (its own docstring records
    this as a known 4b consequence) -- so it is never sent through ``rel_path``
    to begin with; instead it is carried as a fact about the image or
    repository: the signal's ``file`` stays null (the shape 4b's merge already
    gives a path-less rule fact) and the raw source string moves into
    ``extra["source_path"]`` (with ``extra["source_type"]``) so the candidate
    that reads it can still say what was scanned. Any other or missing
    ``source.type`` falls back to the original file-path handling, so a real
    payload nobody here has seen (osv-scanner's ``source.type`` set is not
    contractually closed) degrades to the pre-existing behaviour rather than a
    new one.
    """
    if not isinstance(payload, dict):
        return []
    out: list[Signal] = []
    for result in payload.get("results") or []:
        if not isinstance(result, dict):
            continue
        # isinstance rather than ``or {}``: a truthy non-dict (a bare string
        # source path, which is a shape nobody here has seen osv-scanner emit)
        # passes ``or {}`` and then raises AttributeError on .get. This is one
        # of the four normalisers whose real payload has never been observed,
        # so the unexpected shape is likelier here than anywhere else.
        source = result.get("source")
        if not isinstance(source, dict):
            continue
        raw_path = source.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        source_type = str(source.get("type", ""))
        non_file_extra: dict[str, Any] = {}
        if source_type in _OSV_NON_FILE_SOURCE_TYPES:
            rel = None
            non_file_extra = {"source_type": source_type, "source_path": raw_path}
        else:
            rel = rel_path(root, raw_path)
            if rel is None:
                continue
        for entry in result.get("packages") or []:
            if not isinstance(entry, dict):
                continue
            raw_package = entry.get("package")
            package: dict[str, Any] = raw_package if isinstance(raw_package, dict) else {}
            name = str(package.get("name", ""))
            version = str(package.get("version", ""))
            ecosystem = str(package.get("ecosystem", ""))
            for vulnerability in entry.get("vulnerabilities") or []:
                if not isinstance(vulnerability, dict):
                    continue
                identifier = str(vulnerability.get("id", ""))
                # A truthy non-list ``aliases`` -- a single id as a bare string
                # -- would otherwise be iterated one character at a time into
                # extra["aliases"].
                raw_aliases = vulnerability.get("aliases")
                aliases = [str(alias) for alias in raw_aliases] if isinstance(
                    raw_aliases, list
                ) else []
                out.append(
                    signal(
                        "osv-scanner", "dependency-debt", "vuln",
                        file=rel, line_start=None, line_end=None,
                        message=(
                            f"{name} {version} ({ecosystem}) is affected by "
                            f"{identifier}: {vulnerability.get('summary', '')}"
                        ),
                        fact=True,
                        extra={
                            "package": name, "version": version,
                            "ecosystem": ecosystem, "id": identifier,
                            "aliases": aliases,
                            **non_file_extra,
                        },
                    )
                )
    return out


def normalise_gitleaks(payload: Any, root: Path) -> list[Signal]:
    """gitleaks' findings as fact-class secret signals.

    ``Secret`` and ``Match`` hold the credential gitleaks matched and are
    dropped outright rather than redacted (spec 4.5): this file is read into
    prompts, and a redacted secret is still its own first four characters.
    The rule id, file, line range and entropy that remain are what the
    verifier needs to tell a real leak from a fixture.
    """
    if not isinstance(payload, list):
        return []
    out: list[Signal] = []
    for record in payload:
        if not isinstance(record, dict):
            continue
        rel = rel_path(root, record.get("File"))
        start = record.get("StartLine")
        if rel is None or not isinstance(start, int):
            continue
        end = record.get("EndLine")
        rule = str(record.get("RuleID", ""))
        out.append(
            signal(
                "gitleaks", "security", "secret",
                file=rel, line_start=start,
                line_end=end if isinstance(end, int) else start,
                message=f"{rule}: {record.get('Description', 'possible committed secret')}",
                fact=True,
                extra={"rule": rule, "entropy": record.get("Entropy")},
            )
        )
    return out


# hadolint's level names as the severity scale the rest of the skill uses.
HADOLINT_SEVERITY: Final[dict[str, int]] = {
    "error": 4, "warning": 3, "info": 2, "style": 1,
}


def normalise_hadolint(payload: Any, root: Path) -> list[Signal]:
    """hadolint's diagnostics as fact-class Dockerfile signals.

    A hadolint hit is a fact about a file on disk, so it is fact-class and
    merges in 4b with a same-file rule finding rather than becoming a
    separate candidate. An unrecognised level falls back to the lowest
    severity rather than raising, so a new hadolint level cannot fail a scan.
    """
    if not isinstance(payload, list):
        return []
    out: list[Signal] = []
    for record in payload:
        if not isinstance(record, dict):
            continue
        rel = rel_path(root, record.get("file"))
        line = record.get("line")
        if rel is None or not isinstance(line, int):
            continue
        code = str(record.get("code", ""))
        level = str(record.get("level", "")).lower()
        out.append(
            signal(
                "hadolint", "pipeline-infra", "dockerfile",
                file=rel, line_start=line, line_end=line,
                message=f"{code}: {record.get('message', '')}",
                fact=True,
                extra={"code": code, "level": level,
                       "severity": HADOLINT_SEVERITY.get(level, 1)},
            )
        )
    return out


def normalise_actionlint(payload: Any, root: Path) -> list[Signal]:
    """actionlint's diagnostics as fact-class workflow signals.

    ``snippet`` is a line of the workflow itself, which may carry a token or
    an inline secret reference, and is never copied into a signal; the file
    and line are enough to find it.
    """
    if not isinstance(payload, list):
        return []
    out: list[Signal] = []
    for record in payload:
        if not isinstance(record, dict):
            continue
        rel = rel_path(root, record.get("filepath"))
        line = record.get("line")
        if rel is None or not isinstance(line, int):
            continue
        out.append(
            signal(
                "actionlint", "pipeline-infra", "workflow",
                file=rel, line_start=line, line_end=line,
                message=str(record.get("message", "")),
                fact=True,
                extra={"check": str(record.get("kind", ""))},
            )
        )
    return out
