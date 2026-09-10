"""The baseline: what the last scan found, and what a human decided (spec 4.10).

``diff`` classifies every current finding against the committed baseline --
UNCHANGED, UNCHANGED (moved), UNCHANGED (edited), NEW -- and every baseline
entry no current finding matched as RESOLVED, writing ``diff.json`` for
``design_writer`` to render. ``record`` is called in process by ``promote.py``
and writes each finding's status, reason and expiry back, so a
``rejected`` finding stops recurring and an ``accepted`` one returns when its
expiry passes.

Three classifications are exact and one is a heuristic. A fingerprint match
is UNCHANGED, or UNCHANGED (moved) when the baseline recorded a different
line -- the fingerprint carries no line, so a quote that moved keeps it. An
edited match is the heuristic: same family and file, within ``EDIT_WINDOW``
lines, a title sharing at least half the baseline title's tokens. It can be
wrong in both directions, so a suppression that rests on it is noted.

The baseline lives inside the ignored workdir and is re-included by three
``.gitignore`` lines appended once by ``record``; see ``ensure_gitignore_triple``.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Final

import yaml
from config import ConfigError, load_config
from design_parser import DesignParseError, parse_design
from evidence import find_quote
from inventory import write_json
from redaction import redact

SCHEMA_VERSION: Final[int] = 2
STATUSES: Final[tuple[str, ...]] = ("pending", "approved", "rejected", "accepted", "promoted")
SUPPRESSING: Final[frozenset[str]] = frozenset({"rejected", "accepted"})
EDIT_WINDOW: Final[int] = 40
_TOKEN: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")


class BaselineError(Exception):
    """A baseline that cannot be read or written."""


@dataclass(frozen=True)
class Classification:
    diff: str  # NEW | UNCHANGED | UNCHANGED (moved) | UNCHANGED (edited)
    matched: str | None  # baseline fingerprint, if any
    note: str | None
    suppressed_as: str | None  # "rejected" | "accepted" | None


def load_baseline(path: Path) -> dict[str, Any] | None:
    """The baseline document, or None when the file does not exist."""
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise BaselineError(f"{path}: {exc}") from exc
    if not isinstance(doc, dict) or doc.get("schema_version") != SCHEMA_VERSION:
        raise BaselineError(f"{path}: schema_version must be {SCHEMA_VERSION}")
    if not isinstance(doc.get("findings"), dict):
        raise BaselineError(f"{path}: findings must be an object")
    return doc


def title_tokens(title: str) -> set[str]:
    """Lower-cased tokens split on non-alphanumerics; stop-words are kept (spec 4.10)."""
    return {t for t in _TOKEN.split(title.lower()) if t}


def _primary(finding: dict[str, Any]) -> tuple[str | None, int | None]:
    evidence = finding.get("evidence") or []
    if not evidence or not isinstance(evidence[0], dict):
        return None, None
    file = evidence[0].get("file")
    line = evidence[0].get("line_start")
    return (file if isinstance(file, str) else None,
            line if isinstance(line, int) and not isinstance(line, bool) else None)


def _until_is_malformed(entry: dict[str, Any]) -> bool:
    """True when `until` is present but not a parseable ISO date."""
    until = entry.get("until")
    if until is None:
        return False
    if isinstance(until, str):
        try:
            date.fromisoformat(until)
            return False
        except ValueError:
            return True
    return True


def _expired(entry: dict[str, Any], today: str) -> bool:
    """True when `until` has passed, or is present but malformed.

    A missing `until` (None) means "no expiry" and is never expired. A
    malformed `until` fails safe -- treated as expired so the finding
    returns and `classify` can say why, rather than suppressing silently
    forever.
    """
    until = entry.get("until")
    if until is None:
        return False
    if isinstance(until, str):
        try:
            return date.fromisoformat(until) < date.fromisoformat(today)
        except ValueError:
            pass
    return True


def _suppressed_as(entry: dict[str, Any], today: str) -> str | None:
    status = entry.get("status")
    if status == "rejected":
        return "rejected"
    if status == "accepted" and not _expired(entry, today):
        return "accepted"
    return None


def _edited_match(
    finding: dict[str, Any], baseline: dict[str, Any], file: str, line: int | None
) -> str | None:
    """The fingerprint of a baseline entry this finding is an edit of, if any.

    Requires an integer line on both sides. A finding whose primary evidence
    has no ``line_start`` (an osv-scanner advisory, spec 4.6, always has
    none), or a baseline entry whose recorded ``line_start`` is not an
    integer, can never match here: the heuristic exists for code that moved
    or was retitled near its old location, and a manifest-level fact has no
    "near" to check. Such findings fall through to fingerprint matching, or
    NEW, instead of matching on title overlap alone at any distance.
    """
    if not isinstance(line, int):
        return None
    wanted = title_tokens(str(finding.get("title", "")))
    family = finding.get("family")
    best: tuple[int, str] | None = None
    for fp, entry in baseline["findings"].items():
        if entry.get("family") != family or entry.get("file") != file:
            continue
        base_line = entry.get("line_start")
        if not isinstance(base_line, int) or abs(base_line - line) > EDIT_WINDOW:
            continue
        base_tokens = title_tokens(str(entry.get("title", "")))
        shared = len(wanted & base_tokens)
        if base_tokens and shared * 2 >= len(base_tokens):
            distance = abs(base_line - line)
            if best is None or distance < best[0]:
                best = (distance, fp)
    return best[1] if best else None


def _expiry_note(entry: dict[str, Any], suppressed: str | None) -> str | None:
    """The expiry note for a matched entry, or None when none applies.

    An entry only carries an expiry note when its `status` is `accepted` and
    it is not currently suppressing (`suppressed` is None) -- a rejected or
    pending entry, or an accepted one still within `until`, has nothing to
    report here. Shared by both match branches so a match on the edited
    heuristic reports an expired acceptance exactly as a direct fingerprint
    match does (ruling 23).
    """
    if entry.get("status") == "accepted" and suppressed is None:
        return "until is not a date" if _until_is_malformed(entry) else "acceptance expired"
    return None


def classify(
    finding: dict[str, Any], baseline: dict[str, Any] | None, root: Path, today: str
) -> Classification:
    """One current finding against the baseline (spec 4.10)."""
    if baseline is None:
        return Classification("NEW", None, None, None)
    fp = str(finding.get("fingerprint", ""))
    file, line = _primary(finding)
    entry = baseline["findings"].get(fp)
    if entry is not None:
        suppressed = _suppressed_as(entry, today)
        note = _expiry_note(entry, suppressed)
        moved = isinstance(line, int) and isinstance(entry.get("line_start"), int) \
            and entry["line_start"] != line
        return Classification("UNCHANGED (moved)" if moved else "UNCHANGED", fp, note, suppressed)
    if file is not None:
        edited = _edited_match(finding, baseline, file, line)
        if edited is not None:
            entry = baseline["findings"][edited]
            suppressed = _suppressed_as(entry, today)
            note = "suppressed by edited match" if suppressed else _expiry_note(entry, suppressed)
            return Classification("UNCHANGED (edited)", edited, note, suppressed)
    return Classification("NEW", None, None, None)


def _resolved(entry: dict[str, Any], root: Path) -> tuple[bool, str | None]:
    """Whether an unmatched baseline entry's debt is gone, and why.

    Spec 4.10's baseline schema lists ``quote_hash`` only, but a hash cannot be
    searched for; ``record`` (Task 3) writes an optional ``quote`` alongside it
    so RESOLVED has text to look for. Resolving means the code that carried
    the debt is gone, not that we simply cannot look: an entry with no usable
    quote is resolved only when its file is absent or is now a directory;
    otherwise it stays open, with ``note`` saying why, so a suppressed entry
    never loses its suppression just because a scan failed to reproduce its
    fingerprint.

    The two missing fields are treated differently on purpose. An entry with
    no ``file`` resolves (``file unknown``): it records a repository-level
    fact -- a dependency advisory, a missing pipeline step -- which has no
    file to look in, so the only evidence available is that this scan did not
    reproduce it, and that is taken as the debt being gone. An entry with no
    ``quote`` does not resolve (``quote unavailable``): it still names a file,
    that file may well hold the code, and nothing has been read to say
    otherwise -- so it stays open and says why.
    """
    file = entry.get("file")
    if not isinstance(file, str):
        return True, "file unknown"
    path = root / file
    if path.is_dir():
        return True, "file is a directory"
    if not path.is_file():
        return True, "file absent"
    quote = entry.get("quote")
    if not isinstance(quote, str) or not quote:
        return False, "quote unavailable"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return True, "file unreadable"
    line = entry.get("line_start") if isinstance(entry.get("line_start"), int) else None
    return find_quote(lines, quote, line, line) is None, None


def diff(
    verified: dict[str, Any], baseline: dict[str, Any] | None, root: Path, today: str
) -> dict[str, Any]:
    """The ``diff.json`` document of spec 4.10.

    Every current finding is classified against the baseline; every baseline
    entry no finding matched is checked on disk and marked RESOLVED when its
    quote or its file is gone. A suppressed finding (``rejected`` or an
    unexpired ``accepted``) is listed under ``suppressed`` instead of statused,
    so it never appears twice. An expired acceptance is counted under
    ``expired`` whether its ``until`` passed cleanly or was malformed --
    ``classify`` returns the finding either way, for the same underlying
    reason, so both notes (``acceptance expired`` and ``until is not a date``)
    count there.
    """
    status: dict[str, dict[str, Any]] = {}
    suppressed: list[dict[str, Any]] = []
    counts = {"new": 0, "unchanged": 0, "moved": 0, "edited": 0,
              "resolved": 0, "suppressed": 0, "expired": 0}
    matched: set[str] = set()
    for finding in verified.get("findings") or []:
        if not isinstance(finding, dict):
            continue
        fp = str(finding.get("fingerprint", ""))
        out = classify(finding, baseline, root, today)
        if out.matched:
            matched.add(out.matched)
        if out.suppressed_as:
            entry = baseline["findings"][out.matched] if baseline and out.matched else {}
            suppressed.append({"fingerprint": fp, "status": out.suppressed_as,
                               "reason": entry.get("reason") or ""})
            counts["suppressed"] += 1
            continue
        status[fp] = {"diff": out.diff, "note": out.note, "matched": out.matched}
        if out.note in ("acceptance expired", "until is not a date"):
            counts["expired"] += 1
        counts[{"NEW": "new", "UNCHANGED": "unchanged", "UNCHANGED (moved)": "moved",
                "UNCHANGED (edited)": "edited"}[out.diff]] += 1
    if baseline is not None:
        for fp, entry in baseline["findings"].items():
            if fp in matched:
                continue
            gone, note = _resolved(entry, root)
            if gone:
                status[fp] = {"diff": "RESOLVED", "note": note, "matched": None}
                counts["resolved"] += 1
    return {"schema_version": SCHEMA_VERSION, "baseline_found": baseline is not None,
            "status": status, "suppressed": suppressed, "counts": counts}


# The triple at the default baseline location. ``ensure_gitignore_triple`` derives
# the real triple from wherever the baseline actually lives (see ``_triple``); at
# the default path the two are byte for byte identical, which is what the tests
# below assert. Kept as the documented default-path value.
TRIPLE: Final[tuple[str, ...]] = ("!.tech-debt/", ".tech-debt/*", "!.tech-debt/baseline.json")
TRIPLE_COMMENT: Final[str] = "# tech-debt-scan: track the baseline, ignore the rest of the workdir"


def _entry_fields(finding: dict[str, Any], *, family: Any, title: Any, tier: Any) -> dict[str, Any]:
    """The finding-derived fields common to every baseline entry.

    Shared by ``record``'s decisions loop and its fill-in loop so the two
    cannot drift: ``family``, ``title`` and ``tier`` are supplied by the
    caller (the decision's when a decision exists, the finding's own
    otherwise), and everything else -- file, line, quote hash and redacted
    quote and title -- always comes from ``finding`` itself.
    """
    file, line = _primary(finding)
    quote = None
    evidence = finding.get("evidence") or []
    if evidence and isinstance(evidence[0], dict):
        quote = evidence[0].get("quote")
    return {
        "family": family,
        "file": file,
        "line_start": line,
        "quote_hash": finding.get("quote_hash"),
        "quote": redact(quote) if isinstance(quote, str) else None,
        "title": redact(str(title))[:120],
        "tier": tier,
    }


def _entry_for(
    finding: dict[str, Any],
    fp: str,
    out: dict[str, Any],
    by_fp: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """The baseline entry this finding already has, direct or across an edit.

    A direct fingerprint match wins, and is left in place for the caller to
    overwrite. Failing that, the same edited-match heuristic ``diff``
    classifies with is run over the whole of ``out``, exactly as ``classify``
    runs it, so ``record`` and ``diff`` always agree on which entry a finding
    is an edit of. Only the result is checked for ownership, not the
    candidates: a match already owned by a current finding (a key present in
    ``by_fp``) is left alone -- an entry another finding matches directly can
    never be taken by a neighbouring one -- and the finding gets a fresh
    entry instead; only an unowned match is popped from ``out``, which is
    what migrates the entry to this finding's current fingerprint and
    removes the old key (ruling 29). Returns an empty dict when the finding
    has no entry by either route, or its only match is already owned.
    """
    if fp in out:
        return dict(out[fp])
    file, line = _primary(finding)
    if file is None:
        return {}
    old_key = _edited_match(finding, {"findings": out}, file, line)
    if old_key is None or old_key in by_fp:
        return {}
    return dict(out.pop(old_key))


def record(
    baseline_path: Path,
    *,
    decisions: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    today: str,
    preset: str,
) -> dict[str, Any]:
    """Write every decision into the baseline, and remember every finding shown (spec 4.10).

    ``decisions`` are the parsed design.md findings; ``findings`` the matching
    ``verified.json`` entries, which carry the file, line and quote the design
    document does not. Entries absent from this scan are kept: the baseline
    remembers decisions across scans. The write is atomic so a crash mid-write
    leaves the previous baseline intact.

    A decision with no fingerprint raises: the baseline is keyed by
    fingerprint, so an empty key would collide every fingerprint-less
    decision in one call onto the same entry, silently discarding all but the
    last.

    Every element of ``findings`` with no matching decision is remembered too
    (ruling 25): a suppressed finding is hidden from the design document and
    so absent from ``decisions`` by design, but its recorded decision must
    survive. A finding with no baseline entry by either route below is
    written fresh as ``pending``, with both dates set to ``today``, so it
    reads UNCHANGED rather than NEW on the next scan. A finding with no
    fingerprint is skipped silently here -- unlike a fingerprint-less
    decision, which raises. A decision always wins: any fingerprint
    ``decisions`` already handled is left to that loop.

    Both loops find a finding's existing entry the same way (``_entry_for``,
    ruling 29): its own fingerprint first, and failing that ``_edited_match``
    over the whole baseline, exactly as ``diff`` matches it, with the result
    kept only when no current finding already owns it -- so an entry whose
    code was edited since the last scan migrates to the finding's new
    fingerprint and the old key is removed, while an entry another finding
    matches directly is never taken from it. Otherwise the decision would be
    orphaned under a key nothing matches again, reported RESOLVED, while the
    edited finding started over as ``pending``. Only four fields of an entry
    found either way are preserved: ``status``, ``reason``, ``until`` and
    ``first_seen``. Everything ``_entry_fields`` builds -- family, file,
    line, quote hash, quote, title and tier -- is refreshed from this scan,
    along with ``last_seen``, so a long-lived suppression's recorded line
    keeps up with the code it suppresses and the 40-line edited window is
    measured from where that code is now.
    """
    existing = load_baseline(baseline_path) or {"findings": {}}
    by_fp = {str(f.get("fingerprint")): f for f in findings if isinstance(f, dict)}
    out = dict(existing["findings"])
    decision_fps: set[str] = set()
    for decision in decisions:
        fp = str(decision.get("fingerprint") or "")
        if not fp:
            title = decision.get("title") or "<untitled>"
            raise BaselineError(f"{title!r}: missing fingerprint")
        status = str(decision.get("status", ""))
        if status not in STATUSES:
            raise BaselineError(f"{fp}: unknown status {status!r}")
        finding = by_fp.get(fp, {})
        previous = _entry_for(finding, fp, out, by_fp)
        fields = _entry_fields(
            finding,
            family=decision.get("family") or finding.get("family"),
            title=decision.get("title") or finding.get("title") or "",
            tier=decision.get("tier") or finding.get("tier"),
        )
        out[fp] = {
            **fields,
            "status": status,
            "first_seen": previous.get("first_seen") or today,
            "last_seen": today,
            "reason": redact(str(decision["reason"])) if decision.get("reason") else None,
            "until": decision.get("until"),
        }
        decision_fps.add(fp)
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        fp = str(finding.get("fingerprint") or "")
        if not fp or fp in decision_fps:
            continue
        previous = _entry_for(finding, fp, out, by_fp)
        fields = _entry_fields(
            finding, family=finding.get("family"),
            title=finding.get("title") or "", tier=finding.get("tier"),
        )
        out[fp] = {
            **fields,
            "status": previous.get("status") or "pending",
            "first_seen": previous.get("first_seen") or today,
            "last_seen": today,
            "reason": previous.get("reason"),
            "until": previous.get("until"),
        }
    doc = {"schema_version": SCHEMA_VERSION, "last_scan": today, "preset": preset,
           "findings": dict(sorted(out.items()))}
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    temp = baseline_path.with_suffix(".json.tmp")
    try:
        write_json(temp, doc)
        os.replace(temp, baseline_path)
    except OSError as exc:
        temp.unlink(missing_ok=True)
        raise BaselineError(f"{baseline_path}: {exc}") from exc
    return doc


_GITIGNORE_METACHAR: Final[re.Pattern[str]] = re.compile(r"[#!\[\]*?]")


def _escape_gitignore(segment: str) -> str:
    """Backslash-escape gitignore metacharacters in one path segment.

    ``#`` and ``!`` are only special as a line's first character, but the
    derived lines place a directory or file name right after the leading
    ``!`` (or, for the middle line, at the very start), so an unescaped
    ``#hash`` or ``!important`` name would turn that line into a comment or
    a negation instead of matching the literal name. ``[``, ``]``, ``*`` and
    ``?`` are glob wildcards wherever they appear. Escaping any of the six
    where they are not actually special is harmless: gitignore's own escape
    rule always yields the literal character.
    """
    return _GITIGNORE_METACHAR.sub(lambda m: "\\" + m.group(), segment)


def _triple(rel: str) -> tuple[str, ...]:
    """The three gitignore lines for a baseline at ``rel`` (posix, root-relative).

    At the default location (``.tech-debt/baseline.json``) this reproduces
    ``TRIPLE`` byte for byte; at any other location under some directory it
    is the same three-line pattern derived from that directory and file
    name (each path segment escaped, see ``_escape_gitignore``), so a
    baseline configured elsewhere is tracked correctly too.
    """
    dir_part, sep, name = rel.rpartition("/")
    if not sep:
        raise BaselineError(f"{rel}: baseline must live inside a directory to be tracked")
    dir_escaped = "/".join(_escape_gitignore(seg) for seg in dir_part.split("/"))
    name_escaped = _escape_gitignore(name)
    return (f"!{dir_escaped}/", f"{dir_escaped}/*", f"!{dir_escaped}/{name_escaped}")


def ensure_gitignore_triple(root: Path, baseline_path: Path) -> str:
    """Append the triple once when git ignores the baseline (spec 4.10).

    Returns ``"appended"``, ``"still-ignored"`` (the triple was appended --
    it is the correct pattern for this baseline's location -- but the
    baseline remains ignored, typically because an ancestor directory is
    itself wholly ignored and no per-child ``!`` rule can undo that),
    ``"present"`` (already tracked, or the triple is already there) or
    ``"no-git"``.
    """
    if shutil.which("git") is None:
        return "no-git"
    rel = baseline_path.resolve().relative_to(root.resolve()).as_posix()
    check = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", rel],
                           capture_output=True, check=False)
    if check.returncode != 0:
        return "present"
    triple = _triple(rel)
    gitignore = root / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    lines = existing.splitlines()
    if all(line in lines for line in triple):
        return "present"
    block = "\n".join((TRIPLE_COMMENT, *triple)) + "\n"
    prefix = existing if existing.endswith("\n") or not existing else existing + "\n"
    gitignore.write_text(prefix + block, encoding="utf-8")
    recheck = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", rel],
                             capture_output=True, check=False)
    return "still-ignored" if recheck.returncode == 0 else "appended"


def _scanned_root(args: argparse.Namespace) -> Path:
    """The repository the baseline and its entries are relative to.

    An explicit ``--root`` is always the answer. With none, the scanned
    repository is read from the ``root`` ``inventory.py`` recorded in the
    workdir's own ``inventory.json``, because SKILL.md runs every chain
    command from the skill's directory and the workdir may name any path:
    resolving an entry's ``file`` against the process working directory would
    find nothing and report every unmatched entry RESOLVED with the note
    ``file absent``. An absent inventory, one that is not JSON, or one whose
    ``root`` is not a string leaves the working directory as the fallback --
    the value this flag defaulted to before, and the right answer when the
    chain really is being run from inside the scanned repository.
    """
    if args.root is not None:
        return Path(args.root)
    try:
        inventory = json.loads((Path(args.workdir) / "inventory.json").read_bytes())
    except (OSError, ValueError):
        return Path(".")
    root = inventory.get("root") if isinstance(inventory, dict) else None
    return Path(root) if isinstance(root, str) else Path(".")


def _run_record(args: argparse.Namespace) -> int:
    root = _scanned_root(args)
    workdir = Path(args.workdir)
    verified_path = workdir / "verified.json"
    if not verified_path.is_file():
        print(f"error: {verified_path} not found; run the chain first", file=sys.stderr)
        return 2
    try:
        parsed = parse_design(Path(args.design))
        verified = json.loads(verified_path.read_bytes())
        if not isinstance(verified, dict):
            raise ValueError(f"{verified_path} is not a JSON object")
        config = load_config(root)
        baseline_path = Path(args.baseline) if args.baseline else root / str(config["baseline"])
        today = args.today or date.today().isoformat()
        doc = record(
            baseline_path,
            decisions=parsed["findings"],
            findings=verified.get("findings") or [],
            today=today,
            preset=str(config["ranking"]["preset"]),
        )
        outcome = ensure_gitignore_triple(root, baseline_path)
    except (BaselineError, DesignParseError, ConfigError, OSError, ValueError,
            yaml.YAMLError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {baseline_path}; {len(doc['findings'])} findings recorded")
    if outcome == "appended":
        print("appended the gitignore triple")
    elif outcome == "still-ignored":
        print("appended the gitignore triple, but the baseline is still ignored; "
              "an ancestor directory is ignored and you must un-ignore it by hand")
    return 0


def _run_diff(args: argparse.Namespace) -> int:
    root = _scanned_root(args)
    workdir = Path(args.workdir)
    verified_path = workdir / "verified.json"
    if not verified_path.is_file():
        print(f"error: {verified_path} not found; run the chain first", file=sys.stderr)
        return 2
    try:
        verified = json.loads(verified_path.read_bytes())
        if not isinstance(verified, dict):
            raise ValueError(f"{verified_path} is not a JSON object")
        baseline_path = (
            Path(args.baseline) if args.baseline
            else root / str(load_config(root)["baseline"])
        )
        baseline = load_baseline(baseline_path)
    except (BaselineError, ConfigError, OSError, ValueError, yaml.YAMLError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    today = args.today or date.today().isoformat()
    doc = diff(verified, baseline, root, today)
    write_json(workdir / "diff.json", doc)
    print(f"wrote {workdir / 'diff.json'}; counts: {doc['counts']}")
    return 0


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="The baseline: classify verified findings, diff, and record (spec 4.10)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_diff = sub.add_parser("diff", help="classify verified.json against the baseline")
    p_diff.add_argument("--workdir", default=".tech-debt", help="directory holding verified.json")
    p_diff.add_argument(
        "--root", default=None,
        help="repository root the baseline and its entries are relative to "
             "(default: the scanned root recorded in the workdir's inventory.json, else '.')",
    )
    p_diff.add_argument(
        "--baseline", default=None,
        help="baseline path (default: config's baseline, resolved against --root)",
    )
    p_diff.add_argument("--today", default=None, help="ISO date (default: today)")

    p_record = sub.add_parser("record", help="write design.md decisions back into the baseline")
    p_record.add_argument("--workdir", default=".tech-debt", help="directory holding verified.json")
    p_record.add_argument("--design", required=True, help="path to the edited design.md")
    p_record.add_argument(
        "--root", default=None,
        help="repository root the baseline and its entries are relative to "
             "(default: the scanned root recorded in the workdir's inventory.json, else '.')",
    )
    p_record.add_argument(
        "--baseline", default=None,
        help="baseline path (default: config's baseline, resolved against --root)",
    )
    p_record.add_argument("--today", default=None, help="ISO date (default: today)")

    args = parser.parse_args(argv)
    if args.cmd == "diff":
        return _run_diff(args)
    if args.cmd == "record":
        return _run_record(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
