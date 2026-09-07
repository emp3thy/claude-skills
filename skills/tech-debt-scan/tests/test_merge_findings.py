"""merge_findings.py: validation, quote verification, clustering, corroboration (spec 4.7)."""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from config import DEFAULTS
from evidence import fingerprint
from inventory import build_all, write_json, write_outputs
from make_history import replay_fixture
from merge_findings import (
    CLUSTER_WINDOW,
    NOTE_MAX,
    TITLE_MAX,
    _main,
    _normalise_path,
    merge,
)
from patterns import run_patterns
from rules import run_rules

SECRET = "sk_live_51H8f2kL9mN3pQ7rS4tU6vW"
SWALLOW = "except Exception:\n        pass"
AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
CORPUS = Path(__file__).parent / "fixtures" / "corpus"
CANNED_SIGNALS = Path(__file__).parent / "fixtures" / "tool-signals" / "producer-invariant.json"
# A fixed clock for the corpus chain, the same reason test_chain_goldens pins one:
# rules.py derives day counts (and so fingerprints) from "now", and an unpinned
# clock would make TestTierProducerInvariant's candidate count drift by the day.
RULES_NOW = datetime(2026, 9, 5, tzinfo=UTC)
# The key starts at character 62 and ends at 82, so a cut at TITLE_MAX (80) lands
# inside it. Every branch of SECRET_TOKEN_RE is length-gated -- the AWS branch
# needs 16 characters after the four-letter prefix -- so the surviving fragment
# no longer matches its own pattern and a later redact() is a no-op on it.
STRADDLING_TITLE = (
    f"Long-lived AWS access key committed in src/config/settings.py {AWS_KEY} and never rotated"
)
# The same shape against NOTE_MAX (300): the key spans characters 282 to 302.
STRADDLING_NOTE = ("The key below is committed in plain text. " * 7)[: NOTE_MAX - 18] + AWS_KEY


def _repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "pay.py").write_text(
        "import logging\n"
        "log = logging.getLogger(__name__)\n"
        "\n"
        "def refund(order):\n"
        "    try:\n"
        "        order.refund()\n"
        "    except Exception:\n"
        "        pass\n"
        "\n"
        "def charge(order):\n"
        "    # TODO: retry on timeout\n"
        f'    token = "{SECRET}"\n'
        "    return order.charge(token)\n",
        encoding="utf-8",
    )
    (repo / "src" / "util.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    workdir = tmp_path / "wd"
    inventory, coupling = build_all(repo, config=DEFAULTS)
    write_outputs(inventory, coupling, workdir)
    patterns, _ = run_patterns(repo, inventory, DEFAULTS, blame=False)
    write_json(workdir / "patterns.json", patterns)
    findings, leads = run_rules(repo, inventory, DEFAULTS)
    write_json(
        workdir / "rule-findings.json",
        {"schema_version": 2, "findings": findings, "leads": leads},
    )
    write_json(
        workdir / "scan-plan.json",
        {
            "schema_version": 2,
            "set": "explicit",
            "top": 5,
            "chunked": False,
            "thresholds": DEFAULTS["chunking"],
            "entries": [
                {
                    "family": "error-masking",
                    "module": None,
                    "prompt": "prompts/scout-error-masking.md",
                    "output": "scouts/error-masking.json",
                    "leads": 1,
                },
                {
                    "family": "security",
                    "module": None,
                    "prompt": "prompts/scout-security.md",
                    "output": "scouts/security.json",
                    "leads": 1,
                },
            ],
            "families_run": ["error-masking", "security"],
            "families_skipped": [],
        },
    )
    return repo, workdir


def _finding(
    family: str, title: str, file: str, start: int, end: int, quote: str, **extra: Any
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "title": title,
        "family": family,
        "debt_type": "code",
        "type_id": None,
        "severity": 3,
        "effort": "M",
        "signals_cited": [],
        "evidence": [{"file": file, "line_start": start, "line_end": end, "quote": quote}],
        "note": "n",
    }
    item.update(extra)
    return item


def _scout(
    workdir: Path, family: str, findings: list[dict[str, Any]], **channels: Any
) -> None:
    doc = {
        "family": family,
        "module": None,
        "findings": findings,
        "open_questions": channels.get("open_questions", []),
        "looks_bad_but_fine": channels.get("looks_bad_but_fine", []),
        "not_assessed": [],
    }
    write_json(workdir / "scouts" / f"{family}.json", doc)


def merge_over_corpus_fixture(
    tmp_path: Path, name: str, *, signals: list[Any] | None = None
) -> dict[str, Any]:
    """``merge``'s document for a real corpus fixture, replayed and chain-built up to
    that step (inventory, patterns, rules), over an empty scan plan.

    No scout runs and no golden scout output is copied in: every test that uses this
    helper cares only about the tier a candidate carries, which rule findings and
    fact-class tool signals supply without a scout ever running: dispatching one and
    reading its golden reply here would only slow the test down for no assertion it
    makes.

    ``signals`` is written to the workdir as ``tool-signals.json`` so ``merge`` reads it
    from disk exactly as a real scan does. No corpus fixture carries one of its own --
    which is why the chain goldens do not move for any of this -- so a caller that
    wants tool candidates over a corpus has to supply them here.
    """
    repo = replay_fixture(name, tmp_path / "repo")
    workdir = tmp_path / "wd"
    planted = json.loads((CORPUS / name / "planted.json").read_bytes())
    inventory, coupling = build_all(
        repo, churn_months=int(planted["churn_months"]), config=DEFAULTS
    )
    write_outputs(inventory, coupling, workdir)
    patterns, _inline = run_patterns(repo, inventory, DEFAULTS, blame=False)
    write_json(workdir / "patterns.json", patterns)
    findings, leads = run_rules(repo, inventory, DEFAULTS, now=RULES_NOW)
    write_json(
        workdir / "rule-findings.json",
        {"schema_version": 2, "findings": findings, "leads": leads},
    )
    write_json(workdir / "scan-plan.json", {"schema_version": 2, "entries": []})
    if signals is not None:
        write_json(workdir / "tool-signals.json", {"schema_version": 2, "signals": signals})
    return merge(workdir, repo, DEFAULTS)


def canned_signals() -> list[Any]:
    """Spec 4.7's canned signals file: every fact route, and every route that might
    forge a tier. Loaded from disk rather than built inline so the corpus half of the
    invariant and its direct-dispatch half assert over exactly the same input."""
    doc = json.loads(CANNED_SIGNALS.read_bytes())
    signals: list[Any] = doc["signals"]
    return signals


def test_invented_quote_becomes_an_open_question_and_moved_quote_gets_real_range(
    tmp_path: Path,
) -> None:
    repo, workdir = _repo(tmp_path)
    _scout(
        workdir,
        "error-masking",
        [
            _finding("error-masking", "swallowed", "src/pay.py", 7, 8, SWALLOW),
            _finding("error-masking", "moved", "src/pay.py", 1, 2, "except   Exception:  pass"),
            _finding("error-masking", "invented", "src/pay.py", 3, 3, "this line does not exist"),
        ],
    )
    _scout(workdir, "security", [])
    doc = merge(workdir, repo, DEFAULTS)
    assert list(doc) == ["schema_version", "candidates", "open_questions",
                         "looks_bad_but_fine", "stats"]
    scout_candidates = [c for c in doc["candidates"] if c["source"] == "scout"]
    assert len(scout_candidates) == 1, "the two verified findings cluster (same range)"
    cand = scout_candidates[0]
    assert cand["evidence"][0] == {
        "file": "src/pay.py",
        "line_start": 7,
        "line_end": 8,
        "quote": SWALLOW,
        "quote_verified": True,
    }
    assert cand["tier"] is None
    assert doc["open_questions"] == [
        {"file": "src/pay.py", "line_start": 3, "question": "invented", "reason": "quote not found"}
    ]
    stats = doc["stats"]["error-masking"]
    assert list(stats) == ["raw", "dropped", "quote_failed", "clustered", "suppressed", "disabled"]
    assert stats["raw"] == 3 and stats["quote_failed"] == 1 and stats["clustered"] == 1


def test_fingerprint_cluster_and_corroboration(tmp_path: Path) -> None:
    repo, workdir = _repo(tmp_path)
    _scout(
        workdir,
        "error-masking",
        [
            _finding(
                "error-masking", "a", "src/pay.py", 7, 8, SWALLOW, severity=2, effort="L"
            ),
            _finding(
                "error-masking",
                "b",
                "src/pay.py",
                5,
                6,
                "try:\n        order.refund()",
                severity=4,
                effort="S",
                signals_cited=["pattern:error-masking:swallowed-catch"],
            ),
        ],
    )
    _scout(workdir, "security", [])
    doc = merge(workdir, repo, DEFAULTS)
    assert "dropped_reasons" not in doc["stats"]["security"], "nothing dropped, key must be absent"
    cand = next(c for c in doc["candidates"] if c["source"] == "scout")
    assert cand["severity"] == 4 and cand["effort"] == "S" and cand["title"] == "b"
    assert len(cand["evidence"]) == 2
    fp = fingerprint("error-masking", "src/pay.py", "try:\n        order.refund()")[0]
    alt = fingerprint("error-masking", "src/pay.py", SWALLOW)[0]
    assert cand["fingerprint"] in {fp, alt}
    assert "scout:error-masking" in cand["confirmed_by"]
    assert any(c.startswith("pattern:") for c in cand["confirmed_by"])
    assert cand["signals_cited"] == ["pattern:error-masking:swallowed-catch"]
    assert list(cand) == ["fingerprint", "quote_hash", "family", "debt_type", "type_id", "title",
                          "severity", "effort", "source", "rule_id", "note", "evidence",
                          "confirmed_by", "signals_cited", "signals", "tier"]
    assert list(cand["signals"]) == ["hotspot_score", "churn", "coupling_degree", "fan_in_approx",
                                     "path_class", "in_hotspot_band"]


def test_far_apart_findings_do_not_cluster_and_satd_corroborates(tmp_path: Path) -> None:
    repo, workdir = _repo(tmp_path)
    lines = [f"x = {i}" for i in range(1, 40)]
    (repo / "src" / "long.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
    far = 1 + CLUSTER_WINDOW + 1
    _scout(
        workdir,
        "error-masking",
        [
            _finding("error-masking", "top", "src/long.py", 1, 1, "x = 1"),
            _finding("error-masking", "bottom", "src/long.py", far, far, f"x = {far}"),
        ],
    )
    _scout(
        workdir,
        "security",
        [_finding("security", "todo-site", "src/pay.py", 11, 11, "# TODO: retry on timeout")],
    )
    doc = merge(workdir, repo, DEFAULTS)
    masking = [c for c in doc["candidates"] if c["family"] == "error-masking"]
    assert len(masking) == 2
    todo = next(c for c in doc["candidates"] if c["title"] == "todo-site")
    assert "satd" in todo["confirmed_by"]


def test_malformed_items_are_dropped_and_counted(tmp_path: Path) -> None:
    repo, workdir = _repo(tmp_path)
    wrong_family = _finding("security", "wrong family", "src/pay.py", 12, 12, "token")
    wrong_family["family"] = "dead-code"
    bad = [
        {"title": "no evidence", "family": "security", "debt_type": "code", "severity": 3,
         "effort": "M", "signals_cited": [], "evidence": [], "note": ""},
        wrong_family,
        _finding("security", "bad severity", "src/pay.py", 12, 12, "token", severity=9),
        _finding("security", "bad type", "src/pay.py", 12, 12, "token", type_id="TD-99"),
        "not a dict",
    ]
    _scout(workdir, "security", bad)  # type: ignore[arg-type]
    _scout(workdir, "error-masking", [])
    doc = merge(workdir, repo, DEFAULTS)
    assert [c for c in doc["candidates"] if c["source"] == "scout"] == []
    stats = doc["stats"]["security"]
    assert stats["dropped"] == 5
    assert list(stats) == [
        "raw", "dropped", "quote_failed", "clustered", "suppressed", "disabled", "dropped_reasons",
    ]
    reasons = stats["dropped_reasons"]
    assert len(reasons) == 5
    joined = " | ".join(reasons)
    assert "no evidence" in joined, "the item with an empty evidence list"
    assert "dead-code" in joined, "the wrong family value"
    assert "severity 9" in joined, "the out-of-range severity"
    assert "TD-99" in joined, "the invalid type_id"
    assert "not an object" in joined, "the bare string item"


def test_a_corrupt_scout_file_is_counted_not_fatal(tmp_path: Path) -> None:
    """One malformed scout document must not discard thirteen good ones."""
    repo, workdir = _repo(tmp_path)
    _scout(workdir, "error-masking", [
        _finding("error-masking", "swallowed", "src/pay.py", 7, 8, SWALLOW),
    ])
    (workdir / "scouts" / "security.json").write_bytes(b'{"family": "security", "findings": [')
    doc = merge(workdir, repo, DEFAULTS)
    assert [c["title"] for c in doc["candidates"] if c["source"] == "scout"] == ["swallowed"]
    assert doc["stats"]["security"]["read_failed"] == 1
    assert doc["stats"]["security"]["raw"] == 0


def test_dropped_reason_is_redacted_before_recording(tmp_path: Path) -> None:
    repo, workdir = _repo(tmp_path)
    credential_debt_type = 'token = "abcdefghijkl0123"'
    _scout(workdir, "security", [
        _finding("security", "bad debt_type", "src/pay.py", 12, 12, "token",
                 debt_type=credential_debt_type),
    ])
    _scout(workdir, "error-masking", [])
    doc = merge(workdir, repo, DEFAULTS)
    text = json.dumps(doc)
    assert "abcdefghijkl0123" not in text
    assert "abcd***" in " | ".join(doc["stats"]["security"]["dropped_reasons"])


def test_suppression_with_expiry_and_path_class_disable(tmp_path: Path) -> None:
    repo, workdir = _repo(tmp_path)
    fp, _ = fingerprint("error-masking", "src/pay.py", SWALLOW)
    _scout(workdir, "error-masking", [_finding("error-masking", "a", "src/pay.py", 7, 8, SWALLOW)])
    _scout(workdir, "security", [])
    cfg = deepcopy(DEFAULTS)
    cfg["suppressions"] = [{"fingerprint": fp, "reason": "known", "until": "2026-12-31"}]
    live = merge(workdir, repo, cfg, today=date(2026, 9, 5))
    assert [c for c in live["candidates"] if c["source"] == "scout"] == []
    assert live["stats"]["error-masking"]["suppressed"] == 1
    expired = merge(workdir, repo, cfg, today=date(2027, 1, 1))
    assert len([c for c in expired["candidates"] if c["source"] == "scout"]) == 1
    cfg2 = deepcopy(DEFAULTS)
    cfg2["families"]["per_path_class"]["source"] = {"disable": ["error-masking"]}
    off = merge(workdir, repo, cfg2)
    assert [c for c in off["candidates"] if c["source"] == "scout"] == []
    assert off["stats"]["error-masking"]["disabled"] == 1


def test_secret_is_redacted_everywhere_and_rule_candidates_pass_through(tmp_path: Path) -> None:
    repo, workdir = _repo(tmp_path)
    (repo / "Dockerfile").write_text("FROM alpine:3.20\nRUN apk add curl\n", encoding="utf-8")
    inventory, coupling = build_all(repo, config=DEFAULTS)
    write_outputs(inventory, coupling, workdir)
    findings, leads = run_rules(repo, inventory, DEFAULTS)
    write_json(
        workdir / "rule-findings.json",
        {"schema_version": 2, "findings": findings, "leads": leads},
    )
    _scout(
        workdir,
        "security",
        [
            _finding(
                "security",
                f'hard-coded token = "{SECRET}"',
                "src/pay.py",
                12,
                12,
                f'token = "{SECRET}"',
                note=f'token = "{SECRET}" assigned in charge()',
            )
        ],
        looks_bad_but_fine=[{"file": "src/util.py", "line_start": 1, "why": "helper by design"}],
    )
    _scout(workdir, "error-masking", [])
    doc = merge(workdir, repo, DEFAULTS)
    text = json.dumps(doc)
    assert SECRET not in text and "sk_l***" in text
    rule = [c for c in doc["candidates"] if c["source"] == "rule"]
    assert rule and all(c["tier"] == "A" for c in rule)
    assert doc["candidates"][-1]["source"] == "rule"
    assert doc["looks_bad_but_fine"] == [
        {"file": "src/util.py", "line_start": 1, "why": "helper by design"}
    ]


def test_a_secret_straddling_the_title_or_note_cut_is_redacted_before_truncation(
    tmp_path: Path,
) -> None:
    """Redaction must run before the length cap, or truncation is a redaction bypass.

    ``_validate`` used to cut the title to ``TITLE_MAX`` and the note to
    ``NOTE_MAX`` and leave the redaction to ``_redact_candidate``, which runs
    three steps later. Every branch of ``SECRET_TOKEN_RE`` is length-gated, so a
    token cut in half no longer matches its own pattern: the fragment reached
    ``candidates.json`` verbatim, and then ``design.md``, ``findings.json`` and a
    promoted ``PBI.md``, whose own write-time ``redact`` is gated identically and
    misses it too. ``rules.py`` has always done it the other way round.
    """
    repo, workdir = _repo(tmp_path)
    for value, cap in ((STRADDLING_TITLE, TITLE_MAX), (STRADDLING_NOTE, NOTE_MAX)):
        start = value.index(AWS_KEY)
        assert start < cap < start + len(AWS_KEY), "the fixture must straddle its own cut"
    _scout(
        workdir,
        "error-masking",
        [
            _finding(
                "error-masking", STRADDLING_TITLE, "src/pay.py", 7, 8, SWALLOW,
                note=STRADDLING_NOTE,
            )
        ],
    )
    _scout(workdir, "security", [])
    doc = merge(workdir, repo, DEFAULTS)
    text = json.dumps(doc)
    # 16 characters is the shortest fragment that still identifies the key.
    assert AWS_KEY[:16] not in text, "a truncated fragment of the key reached candidates.json"
    cand = next(c for c in doc["candidates"] if c["source"] == "scout")
    assert "AKIA***" in cand["title"] and "AKIA***" in cand["note"]
    assert len(cand["title"]) <= TITLE_MAX and len(cand["note"]) <= NOTE_MAX


def test_a_title_is_collapsed_to_one_line(tmp_path: Path) -> None:
    """``strip()`` alone let an embedded newline through to every title consumer.

    The verifier prompt's ``title:`` line, ``design.md``'s ``## <title>`` and the
    notes prompt's ``## <n>. <title>`` each render the title on a line they own,
    so a newline in it is a structural break rather than content -- a
    ``# ``-shaped continuation used to abort the whole design render. Collapsing
    here also makes the 80-character cap count characters a reader will see.
    """
    repo, workdir = _repo(tmp_path)
    _scout(
        workdir,
        "error-masking",
        [
            _finding(
                "error-masking",
                "  Refund fails\n# Considered and rejected\t\tsilently  ",
                "src/pay.py", 7, 8, SWALLOW,
            )
        ],
    )
    _scout(workdir, "security", [])
    doc = merge(workdir, repo, DEFAULTS)
    cand = next(c for c in doc["candidates"] if c["source"] == "scout")
    assert cand["title"] == "Refund fails # Considered and rejected silently"


def test_cli(tmp_path: Path) -> None:
    _repo(tmp_path)
    workdir = tmp_path / "wd"
    _scout(workdir, "error-masking", [])
    _scout(workdir, "security", [])
    assert _main(["--workdir", str(workdir)]) == 0
    raw = (workdir / "candidates.json").read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    assert _main(["--workdir", str(tmp_path / "nowhere")]) == 2


def test_normalise_path_converts_backslashes_and_rejects_escapes() -> None:
    """A live scout run on Windows records ``vendor\\x.js``; merge must treat it as
    ``vendor/x.js`` so quote verification and the byte-compared candidates.json
    behave the same on both platforms (spec 4.7)."""
    assert _normalise_path("vendor\\tiny-emitter.js") == "vendor/tiny-emitter.js"
    assert _normalise_path("./src/pay.py") == "src/pay.py"
    assert _normalise_path("src/../secret.py") is None
    assert _normalise_path("/etc/passwd") is None
    assert _normalise_path("C:\\repo\\src\\pay.py") is None
    assert _normalise_path("") is None
    assert _normalise_path(None) is None


def test_pattern_lead_corroborates_only_a_candidate_of_its_own_family(tmp_path: Path) -> None:
    """A lead of another family is no corroboration; the candidate's own family is (spec 4.7)."""
    repo, workdir = _repo(tmp_path)
    write_json(
        workdir / "patterns.json",
        {
            "schema_version": 2,
            "leads": {
                "dead-code": [
                    {"rule": "dead-code:flag-sdk", "file": "src/pay.py", "line": 7,
                     "quote": "q", "path_class": "source", "extra": {}}
                ],
                "error-masking": [
                    {"rule": "error-masking:swallowed-catch", "file": "src/pay.py", "line": 8,
                     "quote": "q", "path_class": "source", "extra": {}}
                ],
            },
            "satd": [],
            "stats": {},
        },
    )
    _scout(
        workdir,
        "error-masking",
        [_finding("error-masking", "swallowed", "src/pay.py", 7, 8, SWALLOW)],
    )
    _scout(workdir, "security", [])
    doc = merge(workdir, repo, DEFAULTS)
    cand = next(c for c in doc["candidates"] if c["source"] == "scout")
    assert "pattern:error-masking:swallowed-catch" in cand["confirmed_by"]
    assert "pattern:dead-code:flag-sdk" not in cand["confirmed_by"]
    assert not any(c.startswith("pattern:dead-code") for c in cand["confirmed_by"])


def test_tool_signal_on_disk_corroborates_a_merged_candidate(tmp_path: Path) -> None:
    """Drives ``merge`` itself with a ``tool-signals.json`` fixture on disk, rather than
    hand-constructing candidates: this is the only test that exercises the disk-read
    path (reading the file, pulling out ``signals``, and wiring the call site into
    ``merge``), so a broken read or an unwired call site cannot hide behind tests that
    call ``corroborate_with_tools`` directly."""
    repo, workdir = _repo(tmp_path)
    _scout(
        workdir,
        "error-masking",
        [_finding("error-masking", "swallowed", "src/pay.py", 7, 8, SWALLOW)],
    )
    _scout(workdir, "security", [])
    write_json(
        workdir / "tool-signals.json",
        {
            "schema_version": 1,
            "tools": [],
            "signals": [
                {
                    "tool": "flake8", "family": "error-masking", "kind": "lint",
                    "file": "src/pay.py", "line_start": 7, "line_end": 8,
                    "message": "bare except", "fact": False, "extra": {},
                },
                {
                    "tool": "vulture", "family": "dead-code", "kind": "unused",
                    "file": "src/pay.py", "line_start": 7, "line_end": 8,
                    "message": "unreachable", "fact": False, "extra": {},
                },
            ],
        },
    )
    doc = merge(workdir, repo, DEFAULTS)
    cand = next(c for c in doc["candidates"] if c["source"] == "scout")
    assert "tool:flake8" in cand["confirmed_by"]
    assert not any(c.startswith("tool:vulture") for c in cand["confirmed_by"]), (
        "a different family's signal must not corroborate"
    )


def _clone_repo(tmp_path: Path) -> tuple[Path, Path]:
    """A repo with one source file and one identical fixture file under ``tests/``,
    a plan holding only ``duplication``, and a jscpd signal on the fixture."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir(parents=True)
    body = "def one():\n    return 1\n"
    (repo / "src" / "a.py").write_text(body, encoding="utf-8")
    (repo / "tests" / "b.py").write_text(body, encoding="utf-8")
    workdir = tmp_path / "wd"
    inventory, coupling = build_all(repo, config=DEFAULTS)
    write_outputs(inventory, coupling, workdir)
    write_json(workdir / "scan-plan.json", {
        "schema_version": 2, "set": "explicit", "top": 5, "chunked": False,
        "thresholds": DEFAULTS["chunking"],
        "entries": [{"family": "duplication", "module": None,
                     "prompt": "prompts/scout-duplication.md",
                     "output": "scouts/duplication.json", "leads": 1}],
        "families_run": ["duplication"], "families_skipped": [],
    })
    _scout(workdir, "duplication", [_finding(
        "duplication", "the same helper twice", "src/a.py", 1, 1, "def one():",
        evidence=[
            {"file": "src/a.py", "line_start": 1, "line_end": 1, "quote": "def one():"},
            {"file": "tests/b.py", "line_start": 1, "line_end": 1, "quote": "def one():"},
        ],
    )])
    write_json(workdir / "tool-signals.json", {
        "schema_version": 2, "tools": {},
        "signals": [{"tool": "jscpd", "family": "duplication", "kind": "clone",
                     "file": "tests/b.py", "line_start": 1, "line_end": 2,
                     "message": "2 duplicated lines", "fact": False, "extra": {}}],
    })
    return repo, workdir


def test_merge_drops_a_tool_signal_the_users_path_class_disables(tmp_path: Path) -> None:
    """The disk path, with the real inventory's classes: DEFAULTS disables duplication
    on ``tests``, so the jscpd signal on the fixture half of the clone pair must not
    lift the source-file candidate's cap. ``plan_scan`` already drops it as a lead."""
    repo, workdir = _clone_repo(tmp_path)
    cand = next(c for c in merge(workdir, repo, DEFAULTS)["candidates"]
                if c["source"] == "scout")
    assert cand["confirmed_by"] == ["scout:duplication"]


def test_merge_keeps_that_signal_when_the_user_has_not_disabled_the_family(
    tmp_path: Path,
) -> None:
    """The control on the same disk inputs: it is the config, read against the real
    path classes, that decides -- so both arguments are wired, not just present."""
    repo, workdir = _clone_repo(tmp_path)
    config = deepcopy(DEFAULTS)
    config["families"]["per_path_class"]["tests"]["disable"] = []
    cand = next(c for c in merge(workdir, repo, config)["candidates"]
                if c["source"] == "scout")
    assert "tool:jscpd" in cand["confirmed_by"]


class TestToolCorroboration:
    def _signal(self, **over) -> dict:
        base = {
            "tool": "jscpd", "family": "duplication", "kind": "clone",
            "file": "src/util/format.ts", "line_start": 1, "line_end": 8,
            "message": "8 duplicated lines", "fact": False, "extra": {},
        }
        base.update(over)
        return base

    def _candidate(self, **over) -> dict:
        base = {
            "fingerprint": "f" * 16, "family": "duplication",
            "evidence": [{"file": "src/util/format.ts", "line_start": 2, "line_end": 6,
                          "quote": "x", "quote_verified": True}],
            "confirmed_by": ["scout:duplication"],
            "signals": {}, "source": "scout",
        }
        base.update(over)
        return base

    def test_a_same_family_same_file_signal_adds_its_token(self) -> None:
        from merge_findings import corroborate_with_tools

        cand = self._candidate()
        corroborate_with_tools([cand], [self._signal()], {}, DEFAULTS)
        assert "tool:jscpd" in cand["confirmed_by"]

    def test_a_different_family_does_not_corroborate(self) -> None:
        from merge_findings import corroborate_with_tools

        cand = self._candidate()
        corroborate_with_tools(
            [cand], [self._signal(family="dead-code", tool="vulture")], {}, DEFAULTS
        )
        assert cand["confirmed_by"] == ["scout:duplication"]

    def test_a_different_file_does_not_corroborate(self) -> None:
        from merge_findings import corroborate_with_tools

        cand = self._candidate()
        corroborate_with_tools([cand], [self._signal(file="src/other.ts")], {}, DEFAULTS)
        assert cand["confirmed_by"] == ["scout:duplication"]

    def test_a_signal_matching_a_later_evidence_file_still_corroborates(self) -> None:
        """A tool that flags any evidence file the candidate cites is a second
        opinion, not only the first: jscpd emits one signal per clone pair naming
        only its own ``firstFile``, and a scout's evidence order need not agree
        with jscpd's, so the match must not depend on which side either producer
        happened to list first."""
        from merge_findings import corroborate_with_tools

        cand = self._candidate(
            evidence=[
                {"file": "src/other.ts", "line_start": 2, "line_end": 6,
                 "quote": "x", "quote_verified": True},
                {"file": "src/util/format.ts", "line_start": 20, "line_end": 24,
                 "quote": "y", "quote_verified": True},
            ]
        )
        corroborate_with_tools([cand], [self._signal()], {}, DEFAULTS)
        assert "tool:jscpd" in cand["confirmed_by"]

    def test_a_candidate_with_no_evidence_corroborates_nothing(self) -> None:
        """Every candidate reaching ``corroborate_with_tools`` via ``merge()`` has
        already passed ``_verify``'s non-empty-evidence gate, so an empty list is
        dead code on that path. It stays as a defensive guard for this function's
        directly-tested unit surface, where an empty list is trivial to construct
        by hand; pinned here so that guard cannot silently regress into an
        ``IndexError``."""
        from merge_findings import corroborate_with_tools

        cand = self._candidate(evidence=[])
        corroborate_with_tools([cand], [self._signal()], {}, DEFAULTS)
        assert cand["confirmed_by"] == ["scout:duplication"]

    def test_a_fact_class_signal_does_not_corroborate_here(self) -> None:
        """Fact-class signals become candidates; corroborating as well would let
        one signal both raise a finding and vouch for it."""
        from merge_findings import corroborate_with_tools

        cand = self._candidate()
        corroborate_with_tools([cand], [self._signal(fact=True)], {}, DEFAULTS)
        assert cand["confirmed_by"] == ["scout:duplication"]

    def test_a_signal_whose_path_class_disables_its_family_does_not_corroborate(self) -> None:
        """``per_path_class: {tests: {disable: [duplication]}}`` is DEFAULTS, and it is the
        documented way to say "clones inside fixtures are not debt". ``plan_scan`` drops
        that signal as a lead; corroboration must drop it too, or the same signal lifts a
        source-file candidate's cap to tier A instead. Not hypothetical: this repository's
        only real jscpd signal is on a fixture path."""
        from merge_findings import corroborate_with_tools

        cand = self._candidate(
            evidence=[
                {"file": "src/a.ts", "line_start": 1, "line_end": 4,
                 "quote": "x", "quote_verified": True},
                {"file": "tests/fixtures/b.ts", "line_start": 1, "line_end": 4,
                 "quote": "y", "quote_verified": True},
            ]
        )
        signal = self._signal(file="tests/fixtures/b.ts")
        corroborate_with_tools(
            [cand], [signal], {"tests/fixtures/b.ts": "tests"}, DEFAULTS
        )
        assert cand["confirmed_by"] == ["scout:duplication"]

    def test_the_same_signal_on_a_source_path_still_corroborates(self) -> None:
        """The control: it is the path class that disables it, not the file's name."""
        from merge_findings import corroborate_with_tools

        cand = self._candidate(
            evidence=[{"file": "tests/fixtures/b.ts", "line_start": 1, "line_end": 4,
                       "quote": "y", "quote_verified": True}]
        )
        corroborate_with_tools(
            [cand], [self._signal(file="tests/fixtures/b.ts")],
            {"tests/fixtures/b.ts": "source"}, DEFAULTS,
        )
        assert "tool:jscpd" in cand["confirmed_by"]

    def test_a_family_the_class_does_not_disable_still_corroborates(self) -> None:
        """DEFAULTS disables duplication, complex-units and god-classes on tests -- not
        dead-code, so a vulture signal on a test file is still a second opinion."""
        from merge_findings import corroborate_with_tools

        cand = self._candidate(
            family="dead-code", confirmed_by=["scout:dead-code"],
            evidence=[{"file": "tests/helpers.ts", "line_start": 1, "line_end": 4,
                       "quote": "y", "quote_verified": True}],
        )
        corroborate_with_tools(
            [cand], [self._signal(family="dead-code", tool="vulture", file="tests/helpers.ts")],
            {"tests/helpers.ts": "tests"}, DEFAULTS,
        )
        assert "tool:vulture" in cand["confirmed_by"]

    def test_the_token_is_added_once_for_two_signals_from_one_tool(self) -> None:
        from merge_findings import corroborate_with_tools

        cand = self._candidate()
        corroborate_with_tools(
            [cand], [self._signal(), self._signal(line_start=20)], {}, DEFAULTS
        )
        assert cand["confirmed_by"].count("tool:jscpd") == 1

    def test_confirmed_by_stays_sorted(self) -> None:
        from merge_findings import corroborate_with_tools

        cand = self._candidate(confirmed_by=["scout:duplication", "rule:ci.pinning"])
        corroborate_with_tools([cand], [self._signal()], {}, DEFAULTS)
        assert cand["confirmed_by"] == sorted(cand["confirmed_by"])

    # No test asserts that a signal with ``file: None`` corroborates nothing: it can't
    # be made to discriminate. The candidate-side lookup always runs its evidence file
    # through ``str(...)`` (so a null file reads as the literal string ``"None"``) while
    # the signal-side path is stored unstringified in ``by_family`` (so a null file is
    # the key ``None``, not ``"None"``). ``None != "None"``, so a None-file signal can
    # never coincide with a candidate's lookup key -- with or without the
    # ``isinstance``/truthy guard that filters it out early, and even when the
    # candidate's own evidence file is also ``None`` (confirmed by removing the guard
    # and running both cases by hand). A test built on this scenario would pass against
    # a broken implementation as readily as a correct one, so it was deleted rather than
    # kept for the appearance of coverage.


class TestToolTokenLiftsTheCap:
    def test_a_duplication_finding_reaches_A_only_with_a_tool_token(self) -> None:
        """family_cap already returns None for duplication when a tool: token is
        present; this pins that the token merge adds is the one it reads."""
        from apply_verdicts import family_cap

        without = {"family": "duplication", "confirmed_by": ["scout:duplication"], "signals": {}}
        with_tool = {"family": "duplication",
                     "confirmed_by": ["scout:duplication", "tool:jscpd"], "signals": {}}
        assert family_cap(without) == "B"
        assert family_cap(with_tool) is None


class TestTierProducerInvariant:
    """Spec 4.7: rules.py and osv fact-class signals are the only producers of a
    non-None tier at merge time. select_candidates pools only candidates whose
    tier is None, so any other class acquiring one skips verification silently.

    Spec 4.7 requires the producer set asserted over the corpus *and* over a canned
    signals file, and both halves here are driven by ``canned_signals()``: no corpus
    fixture carries a ``tool-signals.json``, so a corpus run with none exercises no
    tool route at all, and every assertion below would survive deleting the feature
    it guards. The first two tests read the canned file from disk through ``merge``
    over the real service-py tree; the third dispatches the same rows directly, where
    a rule finding cannot absorb one and every route is visible. Each fails if
    ``tool_candidates`` stops producing candidates."""

    def test_only_rule_and_tool_sources_ever_carry_a_tier(self, tmp_path: Path) -> None:
        document = merge_over_corpus_fixture(tmp_path, "service-py", signals=canned_signals())
        tiered = [c for c in document["candidates"] if c.get("tier") is not None]
        assert tiered, "the fixture must produce at least one tiered candidate"
        assert {c["source"] for c in tiered} <= {"rule", "tool"}
        tool_cands = [c for c in document["candidates"] if c["source"] == "tool"]
        assert tool_cands, "the canned signals file must reach merge and raise candidates"
        assert [c for c in tool_cands if c["tier"] == "A"], "no tier-A tool candidate was raised"
        assert [c for c in tool_cands if c["tier"] is None], "no untiered tool candidate was raised"

    def test_every_tiered_tool_candidate_came_from_an_osv_fact(self, tmp_path: Path) -> None:
        document = merge_over_corpus_fixture(tmp_path, "service-py", signals=canned_signals())
        tiered = [
            c for c in document["candidates"]
            if c.get("tier") is not None and c["source"] == "tool"
        ]
        assert tiered, "the canned signals file must raise a tiered tool candidate to check"
        for cand in tiered:
            assert any(t == "tool:osv-scanner" for t in cand["confirmed_by"])
            assert cand["family"] == "dependency-debt"

    def test_a_canned_signals_file_gives_a_tier_only_to_its_osv_facts(self) -> None:
        """The canned half, dispatched directly. The file's own adversarial rows are
        asserted first: without them the tier assertions below hold vacuously, and a
        later edit that quietly drops a row would leave a test that proves nothing."""
        from merge_findings import tool_candidates

        signals = canned_signals()
        dicts = [s for s in signals if isinstance(s, dict)]
        assert any(isinstance(s.get("extra"), dict) and s["extra"].get("tier") == "A"
                   for s in dicts), "no row tries to forge a tier through extra"
        assert any(s.get("tier") == "A" for s in dicts), "no row carries a top-level tier"
        assert any(s.get("tool") == "trivy" for s in dicts), "no unknown fact-class tool"
        assert any(s.get("tool") == "osv-scanner" and s.get("fact") is False
                   for s in dicts), "no inference row from a tool the dispatch knows"
        assert any(not isinstance(s, dict) for s in signals), "no non-object row"

        new, _ = tool_candidates(signals, {"files": []}, [])
        assert new, "the canned signals file must produce candidates"
        tiered = [c for c in new if c["tier"] is not None]
        untiered = [c for c in new if c["tier"] is None]
        assert tiered and untiered, "the file must exercise both the tiered and untiered routes"
        for cand in tiered:
            assert cand["confirmed_by"] == ["tool:osv-scanner"]
            assert cand["family"] == "dependency-debt"
            assert cand["type_id"] == "TD-02"


class TestFactClassRoutings:
    def _osv(self) -> dict:
        return {
            "tool": "osv-scanner", "family": "dependency-debt", "kind": "vuln",
            "file": "package-lock.json", "line_start": None, "line_end": None,
            "message": "left-pad 1.1.3 (npm) is affected by GHSA-xxxx-yyyy-zzzz",
            "fact": True,
            "extra": {"package": "left-pad", "version": "1.1.3",
                      "ecosystem": "npm", "id": "GHSA-xxxx-yyyy-zzzz", "aliases": []},
        }

    def _gitleaks(self) -> dict:
        return {
            "tool": "gitleaks", "family": "security", "kind": "secret",
            "file": "src/config/settings.py", "line_start": 12, "line_end": 12,
            "message": "generic-api-key: Detected a Generic API Key",
            "fact": True, "extra": {"rule": "generic-api-key", "entropy": 4.31},
        }

    def _hadolint(self) -> dict:
        return {
            "tool": "hadolint", "family": "pipeline-infra", "kind": "dockerfile",
            "file": "Dockerfile", "line_start": 1, "line_end": 1,
            "message": "DL3006: Always tag the version of an image explicitly",
            "fact": True, "extra": {"code": "DL3006", "level": "warning", "severity": 3},
        }

    def test_an_osv_fact_becomes_a_tier_A_candidate_with_no_line_range(self) -> None:
        from merge_findings import tool_candidates

        new, _ = tool_candidates([self._osv()], {"files": []}, [])
        assert len(new) == 1
        cand = new[0]
        assert cand["tier"] == "A"
        assert cand["source"] == "tool"
        assert cand["evidence"][0]["file"] == "package-lock.json"
        assert cand["evidence"][0]["line_start"] is None
        assert cand["evidence"][0]["quote_verified"] is True
        assert "tool:osv-scanner" in cand["confirmed_by"]

    def test_an_osv_candidate_has_a_fingerprint_like_any_other(self) -> None:
        from merge_findings import tool_candidates

        new, _ = tool_candidates([self._osv()], {"files": []}, [])
        assert len(new[0]["fingerprint"]) == 16

    def test_two_advisories_on_one_package_are_two_candidates(self) -> None:
        from merge_findings import tool_candidates

        second = self._osv()
        second["extra"] = dict(second["extra"], id="GHSA-aaaa-bbbb-cccc")
        second["message"] = "left-pad 1.1.3 (npm) is affected by GHSA-aaaa-bbbb-cccc"
        new, _ = tool_candidates([self._osv(), second], {"files": []}, [])
        assert len({c["fingerprint"] for c in new}) == 2

    def test_a_gitleaks_fact_becomes_a_candidate_with_no_tier(self) -> None:
        """Placeholders and test fixtures produce false positives, so gitleaks
        goes to the verifier (spec 4.5)."""
        from merge_findings import tool_candidates

        new, _ = tool_candidates([self._gitleaks()], {"files": []}, [])
        assert new[0]["tier"] is None
        assert new[0]["source"] == "tool"

    def test_hadolint_merges_into_a_same_file_rule_finding(self) -> None:
        from merge_findings import tool_candidates

        rule = {"fingerprint": "a" * 16, "family": "pipeline-infra", "source": "rule",
                "evidence": [{"file": "Dockerfile", "line_start": 3, "line_end": 3,
                              "quote": "FROM python", "quote_verified": True}],
                "confirmed_by": ["rule:container.image"], "tier": "A", "signals": {}}
        new, merged = tool_candidates([self._hadolint()], {"files": []}, [rule])
        assert new == []
        assert "tool:hadolint" in merged[0]["confirmed_by"]

    def test_hadolint_becomes_its_own_candidate_when_no_rule_covers_the_file(self) -> None:
        from merge_findings import tool_candidates

        new, merged = tool_candidates([self._hadolint()], {"files": []}, [])
        assert len(new) == 1
        assert new[0]["evidence"][0]["file"] == "Dockerfile"
        assert new[0]["tier"] is None

    def test_an_inference_signal_never_becomes_a_candidate(self) -> None:
        """Two ways a signal can be inference-class, and the ``fact`` guard is only
        pinned by the first. A ``vulture`` row is rejected on its tool name alone --
        the dispatch table has no entry for it -- so it says nothing about the guard:
        deleting ``or not sig.get("fact")`` left that assertion green. A ``fact:
        False`` row from a tool the dispatch *does* know is the case only the guard
        can stop."""
        from merge_findings import tool_candidates

        known_tool = dict(self._osv(), fact=False)
        assert known_tool["tool"] == "osv-scanner"
        new, _ = tool_candidates([known_tool], {"files": []}, [])
        assert new == []

        unknown_tool = dict(self._osv(), fact=False, tool="vulture", family="dead-code")
        new, _ = tool_candidates([unknown_tool], {"files": []}, [])
        assert new == []

    def test_a_fact_class_signal_from_an_unknown_tool_is_ignored(self) -> None:
        """The dispatch table, not the ``fact`` flag, is what closes the tool set: a
        future scanner claiming ``fact: True`` has no metadata here to build from."""
        from merge_findings import tool_candidates

        counts: list[tuple[str, str, str | None]] = []
        new, _ = tool_candidates(
            [dict(self._gitleaks(), tool="trivy")], {"files": []}, [], counts=counts
        )
        assert new == []
        assert counts == []

    def test_every_message_is_redacted(self) -> None:
        from merge_findings import tool_candidates

        leaky = dict(self._gitleaks(),
                     message='found token = "sk_live_51H8f2kL9mN3pQ7rS4tU6vW" in settings')
        new, _ = tool_candidates([leaky], {"files": []}, [])
        blob = json.dumps(new)
        assert "sk_live_51H8f2kL9mN3pQ7rS4tU6vW" not in blob
        assert "sk_l***" in blob

    def test_a_confirmed_gitleaks_candidate_does_not_self_corroborate_to_tier_A(self) -> None:
        """A candidate's own ``tool:<name>`` token, if it carried one, would be read by
        ``apply_verdicts.family_cap`` (``_has(cand, "tool:")``) and ``corroborated`` as
        independent corroboration of the very thing that raised it -- neither knows the
        token names the candidate's own source. That would let a single bare "confirm"
        verdict jump straight to tier A with no second opinion, the exact self-vouching
        ``corroborate_with_tools`` was built to keep out of the scout path. An empty
        ``confirmed_by`` at construction is what closes the same hole on this path:
        this test would fail (tier A instead of B) if that empty list were replaced
        with a self-referencing ``tool:gitleaks`` entry."""
        from apply_verdicts import earned_tier
        from merge_findings import tool_candidates

        new, _ = tool_candidates([self._gitleaks()], {"files": []}, [])
        cand = new[0]
        verdict = {"verdict": "confirm", "severity": 4, "effort": "M"}
        assert earned_tier(cand, verdict) == "B"

    def test_an_osv_fact_with_no_file_becomes_a_repository_level_tier_A_candidate(self) -> None:
        """osv-scanner names a docker image or git remote in ``source.path``, which is
        not a file ``rel_path`` can resolve (the 4b fix in
        ``tool_normalisers.normalise_osv_scanner``): the signal reaches here with
        ``file: None`` and the source recorded in ``extra``, and the candidate takes
        the null-file repository-fact shape a path-less rule finding already uses."""
        from merge_findings import tool_candidates

        sig = dict(
            self._osv(),
            file=None,
            extra=dict(self._osv()["extra"], source_type="docker", source_path="alpine:3.18"),
        )
        new, _ = tool_candidates([sig], {"files": []}, [])
        assert len(new) == 1
        cand = new[0]
        assert cand["tier"] == "A"
        assert cand["evidence"][0]["file"] is None
        assert cand["evidence"][0]["line_start"] is None
        assert cand["evidence"][0]["quote_verified"] is True
        assert "alpine:3.18" in cand["title"]

    def test_two_non_file_sources_with_the_same_advisory_are_two_candidates(self) -> None:
        """Without the source folded into the quote before fingerprinting, two docker
        images affected by the same advisory would share one empty path and one
        identical message, collide onto a single fingerprint, and silently merge into
        one candidate."""
        from merge_findings import tool_candidates

        first = dict(
            self._osv(), file=None,
            extra=dict(self._osv()["extra"], source_type="docker", source_path="alpine:3.18"),
        )
        second = dict(
            self._osv(), file=None,
            extra=dict(self._osv()["extra"], source_type="docker", source_path="alpine:3.19"),
        )
        new, _ = tool_candidates([first, second], {"files": []}, [])
        assert len({c["fingerprint"] for c in new}) == 2


class TestFactSignalIdentity:
    """One fact per candidate, and one candidate per fact (spec 4.7 steps 4 and 5)."""

    def _gitleaks(self, line: int) -> dict[str, Any]:
        return {
            "tool": "gitleaks", "family": "security", "kind": "secret",
            "file": "src/app/config.py", "line_start": line, "line_end": line,
            "message": "generic-api-key: Detected a Generic API Key",
            "fact": True, "extra": {"rule": "generic-api-key"},
        }

    def test_two_hits_of_one_rule_in_one_file_have_distinct_fingerprints(self) -> None:
        """gitleaks emits one record per hit and builds its message as
        ``f"{RuleID}: {Description}"``, identical for every hit of one rule in one file;
        hadolint repeats one code's message down a Dockerfile. With family, path and
        message the whole fingerprint input, those hits collided."""
        from merge_findings import tool_candidates

        new, _ = tool_candidates([self._gitleaks(3), self._gitleaks(41)], {"files": []}, [])
        assert len(new) == 2
        assert len({c["fingerprint"] for c in new}) == 2

    def test_two_identical_signals_collapse_to_one_candidate(self) -> None:
        """Same family, path, range and message is the same fact twice. Before, it gave
        two candidates sharing one fingerprint, which is worse than either merging or
        keeping them apart: one verdict then decided both."""
        from merge_findings import tool_candidates

        counts: list[tuple[str, str, str | None]] = []
        new, _ = tool_candidates(
            [self._gitleaks(3), self._gitleaks(3)], {"files": []}, [], counts=counts
        )
        assert len(new) == 1
        assert counts == [("security", "clustered", None)]

    def test_a_confirmed_hit_does_not_inherit_another_hits_rejection(self) -> None:
        """The end-to-end failure the line range exists to stop. ``apply_verdicts.apply``
        keys verdicts by fingerprint and the last write wins, so while two hits in one
        file shared an id, a verifier that confirmed the live key at line 3 and rejected
        the placeholder at line 41 saw both land ``reject``, and the real credential left
        the report with nothing counting it."""
        from apply_verdicts import apply
        from merge_findings import tool_candidates

        new, _ = tool_candidates([self._gitleaks(3), self._gitleaks(41)], {"files": []}, [])
        by_line = {c["evidence"][0]["line_start"]: c for c in new}
        plan = {"selected": [c["fingerprint"] for c in new]}
        verdicts = {"verdicts/verify-01.json": [
            {"fingerprint": by_line[3]["fingerprint"], "verdict": "confirm",
             "severity": 5, "effort": "M", "proof": "a live key"},
            {"fingerprint": by_line[41]["fingerprint"], "verdict": "reject",
             "severity": 1, "effort": "S", "proof": "a placeholder"},
        ]}
        document = apply(new, plan, verdicts)
        by_fp = {f["fingerprint"]: f for f in document["findings"]}
        assert by_fp[by_line[3]["fingerprint"]]["verdict"] == "confirm"
        assert by_fp[by_line[3]["fingerprint"]]["tier"] == "B"
        assert by_fp[by_line[41]["fingerprint"]]["verdict"] == "reject"
        assert by_fp[by_line[41]["fingerprint"]]["tier"] is None
        assert document["stats"]["selected"] == 2
        assert document["stats"]["verdicts"] == 2


class TestFactSignalValidation:
    """``tool-signals.json`` is unvalidated input, so every route checks it (spec 4.7)."""

    def _osv(self) -> dict[str, Any]:
        return {
            "tool": "osv-scanner", "family": "dependency-debt", "kind": "vuln",
            "file": "package-lock.json", "line_start": None, "line_end": None,
            "message": "left-pad 1.1.3 (npm) is affected by GHSA-1",
            "fact": True, "extra": {"package": "left-pad", "id": "GHSA-1"},
        }

    def _dropped(self, sig: dict[str, Any]) -> tuple[list[dict[str, Any]], list[Any]]:
        from merge_findings import tool_candidates

        counts: list[tuple[str, str, str | None]] = []
        new, _ = tool_candidates([sig], {"files": []}, [], counts=counts)
        return new, counts

    def test_a_signal_with_no_family_is_dropped_not_given_the_family_None(self) -> None:
        """It reached a report as a tier-A candidate in a family literally named
        ``"None"``, with a ``"None"`` key in ``stats``, and survived apply and rank."""
        sig = self._osv()
        del sig["family"]
        new, counts = self._dropped(sig)
        assert new == []
        assert counts == [("dependency-debt", "dropped",
                           "osv-scanner family 'None' is not a known family")]

    def test_a_signal_claiming_another_familys_name_is_dropped(self) -> None:
        """``duplication`` is a real family, so a membership check alone passes it --
        and it arrived as a tier-A duplication finding carrying the dependency
        ``type_id`` TD-02, a triple ``categories.FAMILY_BLOCKS`` does not allow. The
        family picks the caps and the rubric; ``_TOOL_META`` picks the type. They have
        to agree."""
        new, counts = self._dropped(dict(self._osv(), family="duplication"))
        assert new == []
        assert counts == [("dependency-debt", "dropped",
                           "osv-scanner family 'duplication' is not 'dependency-debt'")]

    def test_every_route_validates_its_family_not_only_the_tiered_one(self) -> None:
        from merge_findings import tool_candidates

        signals = [
            {"tool": "gitleaks", "family": "duplication", "file": "a.py",
             "line_start": 1, "line_end": 1, "message": "m", "fact": True, "extra": {}},
            {"tool": "hadolint", "family": "duplication", "file": "Dockerfile",
             "line_start": 1, "line_end": 1, "message": "m", "fact": True, "extra": {}},
            {"tool": "actionlint", "family": "duplication", "file": "w.yml",
             "line_start": 1, "line_end": 1, "message": "m", "fact": True, "extra": {}},
        ]
        counts: list[tuple[str, str, str | None]] = []
        new, _ = tool_candidates(signals, {"files": []}, [], counts=counts)
        assert new == []
        assert counts == [
            ("security", "dropped", "gitleaks family 'duplication' is not 'security'"),
            ("pipeline-infra", "dropped",
             "hadolint family 'duplication' is not 'pipeline-infra'"),
            ("pipeline-infra", "dropped",
             "actionlint family 'duplication' is not 'pipeline-infra'"),
        ]

    def test_a_hadolint_signal_with_a_foreign_family_cannot_merge_into_a_rule(self) -> None:
        """Validation runs before the merge, so a junk family cannot put a
        ``tool:hadolint`` token onto a rule finding either."""
        from merge_findings import tool_candidates

        rule = {"fingerprint": "a" * 16, "family": "pipeline-infra", "source": "rule",
                "evidence": [{"file": "Dockerfile", "line_start": 3, "line_end": 3,
                              "quote": "FROM python", "quote_verified": True}],
                "confirmed_by": ["rule:container.image"], "tier": "A", "signals": {}}
        sig = {"tool": "hadolint", "family": "duplication", "file": "Dockerfile",
               "line_start": 1, "line_end": 1, "message": "DL3006: tag it",
               "fact": True, "extra": {}}
        new, merged = tool_candidates([sig], {"files": []}, [rule])
        assert new == []
        assert merged[0]["confirmed_by"] == ["rule:container.image"]

    def test_an_untiered_signal_with_no_file_is_dropped_rather_than_crashing_later(self) -> None:
        """``verify_prompts._span`` does ``root / ev["file"]`` on every pooled
        candidate, and ``select_candidates`` pools every untiered one, so a null-file
        gitleaks/hadolint/actionlint candidate aborted the whole scan with a
        ``TypeError`` rather than losing one finding. There is nothing for a verifier
        to read either way, so it never becomes a candidate. The tier-A osv route keeps
        its null-file shape: it is never pooled, and every downstream consumer already
        handles the path-less rule-finding shape."""
        for tool, family in (("gitleaks", "security"), ("hadolint", "pipeline-infra"),
                             ("actionlint", "pipeline-infra")):
            sig = {"tool": tool, "family": family, "file": None, "line_start": 1,
                   "line_end": 1, "message": "m", "fact": True, "extra": {}}
            new, counts = self._dropped(sig)
            assert new == [], f"{tool} raised a null-file candidate"
            assert counts == [(family, "dropped", f"{tool} signal names no usable file")]

    def test_an_untiered_signal_with_an_unusable_path_is_dropped(self) -> None:
        """``_normalise_path`` is what "usable" means: a traversal or absolute path
        would otherwise be joined to the root and read by the verifier prompt."""
        sig = {"tool": "gitleaks", "family": "security", "file": "../../etc/shadow",
               "line_start": 1, "line_end": 1, "message": "m", "fact": True, "extra": {}}
        new, counts = self._dropped(sig)
        assert new == []
        assert counts == [("security", "dropped", "gitleaks signal names no usable file")]

    def test_a_null_file_osv_fact_still_becomes_a_tier_A_candidate(self) -> None:
        sig = dict(self._osv(), file=None,
                   extra=dict(self._osv()["extra"], source_type="docker",
                              source_path="alpine:3.18"))
        new, counts = self._dropped(sig)
        assert len(new) == 1 and new[0]["tier"] == "A"
        assert counts == []

    def test_a_null_file_untiered_candidate_no_longer_aborts_the_verify_plan(
        self, tmp_path: Path
    ) -> None:
        """The same defect end to end: before, ``build_verify_plan`` raised
        ``TypeError: unsupported operand type(s) for /: 'WindowsPath' and 'NoneType'``
        and the scan died with a traceback and no output at all."""
        from verify_prompts import build_verify_plan

        repo, workdir = _repo(tmp_path)
        _scout(workdir, "error-masking", [])
        _scout(workdir, "security", [])
        write_json(workdir / "tool-signals.json", {"schema_version": 2, "signals": [
            {"tool": "hadolint", "family": "pipeline-infra", "kind": "dockerfile",
             "file": None, "line_start": 1, "line_end": 1,
             "message": "DL3006: Always tag the version of an image explicitly",
             "fact": True, "extra": {"code": "DL3006"}},
        ]})
        document = merge(workdir, repo, DEFAULTS)
        write_json(workdir / "candidates.json", document)
        assert [c for c in document["candidates"] if c["source"] == "tool"] == []
        assert document["stats"]["pipeline-infra"]["dropped"] == 1
        plan, _prompts = build_verify_plan(workdir, repo, DEFAULTS, top=5)
        assert plan["batches"] == []

    def test_a_gitleaks_signal_with_a_null_line_start_is_dropped_rather_than_crashing_later(
        self, tmp_path: Path
    ) -> None:
        """N1's sibling of the null-file defect: ``verify_prompts._span`` does
        ``int(ev["line_start"])`` on every pooled candidate's evidence, two lines past
        the ``root / ev["file"]`` the null-file guard closed. A null ``line_start`` on
        an untiered candidate reached that line and aborted the whole scan."""
        from verify_prompts import build_verify_plan

        repo, workdir = _repo(tmp_path)
        _scout(workdir, "error-masking", [])
        _scout(workdir, "security", [])
        write_json(workdir / "tool-signals.json", {"schema_version": 2, "signals": [
            {"tool": "gitleaks", "family": "security", "kind": "secret",
             "file": "src/pay.py", "line_start": None, "line_end": 3,
             "message": "generic-api-key: Detected a Generic API Key",
             "fact": True, "extra": {"rule": "generic-api-key"}},
        ]})
        document = merge(workdir, repo, DEFAULTS)
        write_json(workdir / "candidates.json", document)
        plan, _prompts = build_verify_plan(workdir, repo, DEFAULTS, top=5)
        assert plan["batches"] == []
        assert [c for c in document["candidates"] if c["source"] == "tool"] == []
        assert document["stats"]["security"]["dropped"] == 1
        assert document["stats"]["security"]["dropped_reasons"] == [
            "gitleaks signal names no usable line range"
        ]

    def test_a_gitleaks_signal_with_a_null_line_end_is_dropped_rather_than_crashing_later(
        self, tmp_path: Path
    ) -> None:
        """Same defect, the other half of the pair: ``line_end`` null with
        ``line_start`` present still fails ``int(ev["line_end"])``."""
        from verify_prompts import build_verify_plan

        repo, workdir = _repo(tmp_path)
        _scout(workdir, "error-masking", [])
        _scout(workdir, "security", [])
        write_json(workdir / "tool-signals.json", {"schema_version": 2, "signals": [
            {"tool": "gitleaks", "family": "security", "kind": "secret",
             "file": "src/pay.py", "line_start": 3, "line_end": None,
             "message": "generic-api-key: Detected a Generic API Key",
             "fact": True, "extra": {"rule": "generic-api-key"}},
        ]})
        document = merge(workdir, repo, DEFAULTS)
        write_json(workdir / "candidates.json", document)
        plan, _prompts = build_verify_plan(workdir, repo, DEFAULTS, top=5)
        assert plan["batches"] == []
        assert [c for c in document["candidates"] if c["source"] == "tool"] == []
        assert document["stats"]["security"]["dropped"] == 1

    def test_a_gitleaks_signal_with_a_non_integer_line_range_is_dropped(
        self, tmp_path: Path
    ) -> None:
        """``_fact_candidate`` silently coerces a non-``int`` ``line_start`` (a
        string, a float) to ``None`` -- the entirely plausible
        ``"line_start": "3"`` a hand-edited or truncated ``tool-signals.json`` would
        carry -- so this crashes exactly like the null case, one step removed."""
        from verify_prompts import build_verify_plan

        repo, workdir = _repo(tmp_path)
        _scout(workdir, "error-masking", [])
        _scout(workdir, "security", [])
        write_json(workdir / "tool-signals.json", {"schema_version": 2, "signals": [
            {"tool": "gitleaks", "family": "security", "kind": "secret",
             "file": "src/pay.py", "line_start": "3", "line_end": 3,
             "message": "generic-api-key: Detected a Generic API Key",
             "fact": True, "extra": {"rule": "generic-api-key"}},
        ]})
        document = merge(workdir, repo, DEFAULTS)
        write_json(workdir / "candidates.json", document)
        plan, _prompts = build_verify_plan(workdir, repo, DEFAULTS, top=5)
        assert plan["batches"] == []
        assert [c for c in document["candidates"] if c["source"] == "tool"] == []
        assert document["stats"]["security"]["dropped"] == 1

    def test_a_hadolint_signal_with_a_null_line_range_is_dropped(
        self, tmp_path: Path
    ) -> None:
        """The same guard on the other untiered route: hadolint with a real file but
        no usable line range."""
        from verify_prompts import build_verify_plan

        repo, workdir = _repo(tmp_path)
        _scout(workdir, "error-masking", [])
        _scout(workdir, "security", [])
        write_json(workdir / "tool-signals.json", {"schema_version": 2, "signals": [
            {"tool": "hadolint", "family": "pipeline-infra", "kind": "dockerfile",
             "file": "src/util.py", "line_start": None, "line_end": None,
             "message": "DL3006: Always tag the version of an image explicitly",
             "fact": True, "extra": {"code": "DL3006"}},
        ]})
        document = merge(workdir, repo, DEFAULTS)
        write_json(workdir / "candidates.json", document)
        plan, _prompts = build_verify_plan(workdir, repo, DEFAULTS, top=5)
        assert plan["batches"] == []
        assert [c for c in document["candidates"] if c["source"] == "tool"] == []
        assert document["stats"]["pipeline-infra"]["dropped"] == 1
        assert document["stats"]["pipeline-infra"]["dropped_reasons"] == [
            "hadolint signal names no usable line range"
        ]

    def test_a_null_line_range_osv_fact_still_becomes_a_tier_A_candidate(self) -> None:
        """The exemption N1 calls for: osv-scanner's null range is spec 4.5's
        deliberate shape (its evidence is a manifest path, not a line), it is tier A,
        and ``select_candidates`` never pools a tiered candidate -- so it must not be
        caught by the untiered range guard."""
        new, counts = self._dropped(self._osv())
        assert len(new) == 1 and new[0]["tier"] == "A"
        assert new[0]["evidence"][0]["line_start"] is None
        assert new[0]["evidence"][0]["line_end"] is None
        assert counts == []

    def test_a_dropped_fact_is_counted_and_its_reason_recorded_in_stats(
        self, tmp_path: Path
    ) -> None:
        repo, workdir = _repo(tmp_path)
        _scout(workdir, "error-masking", [])
        _scout(workdir, "security", [])
        write_json(workdir / "tool-signals.json", {"schema_version": 2, "signals": [
            dict(self._osv(), family="duplication"),
        ]})
        document = merge(workdir, repo, DEFAULTS)
        assert document["stats"]["dependency-debt"]["dropped"] == 1
        assert document["stats"]["dependency-debt"]["dropped_reasons"] == [
            "osv-scanner family 'duplication' is not 'dependency-debt'"
        ]


class TestToolCandidateDisables:
    def test_a_path_class_disable_drops_a_tool_candidate(self, tmp_path: Path) -> None:
        """Spec 4.7 step 7 applies suppressions *and* path-class disables. Rule
        findings are exempt because ``rules.py`` drops disabled-class artefacts before
        emitting them; ``tools_probe`` filters only the vendored and generated classes,
        so nothing upstream has applied a user's disables to a tool signal. Without
        this, ``tests: {disable: [security]}`` -- the natural way to stop gitleaks
        reporting fixture credentials -- was silently ignored."""
        repo, workdir = _repo(tmp_path)
        _scout(workdir, "error-masking", [])
        _scout(workdir, "security", [])
        write_json(workdir / "tool-signals.json", {"schema_version": 2, "signals": [
            {"tool": "gitleaks", "family": "security", "kind": "secret",
             "file": "src/pay.py", "line_start": 12, "line_end": 12,
             "message": "generic-api-key: Detected a Generic API Key",
             "fact": True, "extra": {"rule": "generic-api-key"}},
        ]})
        on = merge(workdir, repo, DEFAULTS)
        assert [c for c in on["candidates"] if c["source"] == "tool"]

        cfg = deepcopy(DEFAULTS)
        cfg["families"]["per_path_class"]["source"] = {"disable": ["security"]}
        off = merge(workdir, repo, cfg)
        assert [c for c in off["candidates"] if c["source"] == "tool"] == []
        assert off["stats"]["security"]["disabled"] == 1


class TestToolSeverityAndEffort:
    def _sig(self, tool: str, family: str, **extra: Any) -> dict[str, Any]:
        return {"tool": tool, "family": family, "kind": "k", "file": "a.py",
                "line_start": 1, "line_end": 1, "message": "m", "fact": True,
                "extra": dict(extra)}

    def _one(self, sig: dict[str, Any]) -> dict[str, Any]:
        from merge_findings import tool_candidates

        new, _ = tool_candidates([sig], {"files": []}, [])
        assert len(new) == 1
        candidate: dict[str, Any] = new[0]
        return candidate

    def test_only_hadolint_and_osv_read_a_severity_out_of_extra(self) -> None:
        """``_tool_severity`` read ``extra["severity"]`` for every tool while its own
        comment and the module docstring said hadolint, and an osv ``extra`` severity
        overrode the deliberate constant. Both tools in the closed set compute the value
        in their own normaliser (hadolint from its level, osv from the advisory's
        published severity); a tool that computes none must not be able to acquire one
        from an unvalidated signals file."""
        assert self._one(self._sig("gitleaks", "security", severity=1))["severity"] == 5
        assert self._one(
            self._sig("actionlint", "pipeline-infra", severity=1)
        )["severity"] == 3
        assert self._one(self._sig("hadolint", "pipeline-infra", severity=1))["severity"] == 1
        assert self._one(
            self._sig("osv-scanner", "dependency-debt", severity=2)
        )["severity"] == 2

    def test_an_out_of_range_severity_falls_back_to_the_table(self) -> None:
        for value in (0, 6, True, "4", None):
            cand = self._one(self._sig("hadolint", "pipeline-infra", severity=value))
            assert cand["severity"] == 3, value

    def test_an_osv_advisory_with_no_published_severity_keeps_the_constant(self) -> None:
        assert self._one(self._sig("osv-scanner", "dependency-debt"))["severity"] == 4

    def test_gitleaks_effort_is_M(self) -> None:
        """A confirmed live credential is a rotation, a redeploy, an access audit and
        usually a history rewrite -- not the S the other three fact tools take."""
        assert self._one(self._sig("gitleaks", "security"))["effort"] == "M"


class TestToolCandidateSourcePaths:
    def _osv(self, source_path: str) -> dict[str, Any]:
        return {
            "tool": "osv-scanner", "family": "dependency-debt", "kind": "vuln",
            "file": None, "line_start": None, "line_end": None,
            "message": "libcrypto 1.1.1 is affected by CVE-2099-0001", "fact": True,
            "extra": {"id": "CVE-2099-0001", "source_type": "git",
                      "source_path": source_path},
        }

    def test_a_source_urls_userinfo_never_reaches_a_candidate(self) -> None:
        """A git source is a URL, and a submodule remote or a CI checkout can carry
        ``user:password@``. ``CREDENTIAL_RE`` needs a key name and an operator and
        ``SECRET_TOKEN_RE`` a known issuer prefix, so neither catches it: the password
        reached the title, note and quote verbatim. An issuer-prefixed token was caught
        only by luck of its prefix."""
        from merge_findings import tool_candidates

        new, _ = tool_candidates(
            [self._osv("https://user:hunter2password@git.example.com/o/r.git")],
            {"files": []}, [],
        )
        blob = json.dumps(new)
        assert "hunter2password" not in blob
        assert "user:" not in blob
        assert "https://git.example.com/o/r.git" in new[0]["note"]
        assert "https://git.example.com/o/r.git" in new[0]["evidence"][0]["quote"]

    def test_a_source_url_with_no_userinfo_is_untouched(self) -> None:
        from merge_findings import tool_candidates

        new, _ = tool_candidates([self._osv("https://git.example.com/o/r.git")],
                                 {"files": []}, [])
        assert "https://git.example.com/o/r.git" in new[0]["note"]


class TestMergeIntoRuleUsesTheSignalsFamily:
    def _rule(self, family: str) -> dict[str, Any]:
        return {"fingerprint": "a" * 16, "family": family, "source": "rule",
                "evidence": [{"file": "Dockerfile", "line_start": 3, "line_end": 3,
                              "quote": "FROM python", "quote_verified": True}],
                "confirmed_by": ["rule:container.image"], "tier": "A", "signals": {}}

    def _sig(self, family: str) -> dict[str, Any]:
        return {"tool": "hadolint", "family": family, "kind": "dockerfile",
                "file": "Dockerfile", "line_start": 1, "line_end": 1,
                "message": "DL3006: tag it", "fact": True, "extra": {}}

    def test_the_merge_target_family_follows_the_tools_registry_not_a_literal(
        self, monkeypatch: Any
    ) -> None:
        """``_merge_into_rule`` hard-coded ``pipeline-infra``. Correct only while both
        merging tools sat in that family: the day either moved, the merge would stop
        merging and start raising a duplicate candidate beside the rule finding, with
        nothing failing. Moving hadolint's registry family here is the only way to
        observe that, because the family validation now guarantees a signal's family is
        its tool's."""
        import merge_findings

        monkeypatch.setitem(merge_findings._TOOL_FAMILY, "hadolint", "architecture")
        merged, findings = merge_findings.tool_candidates(
            [self._sig("architecture")], {"files": []}, [self._rule("architecture")]
        )
        assert merged == []
        assert "tool:hadolint" in findings[0]["confirmed_by"]

        new, untouched = merge_findings.tool_candidates(
            [self._sig("architecture")], {"files": []}, [self._rule("pipeline-infra")]
        )
        assert len(new) == 1
        assert untouched[0]["confirmed_by"] == ["rule:container.image"]
