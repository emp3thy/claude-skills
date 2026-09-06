"""design_writer.py v2: render design.md and findings.json from the ranked chain (spec 4.11)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from design_parser import parse_design
from design_writer import (
    SECTION_ORDER,
    DesignWriteError,
    load_inputs,
    render_design,
    write_design,
)
from inventory import write_json

SCAN_DATE = "2026-09-06"
GOLDEN = Path(__file__).parent / "golden"

TOP_FP = "0123456789abcdef"
CUT_FP = "fedcba9876543210"
TIER_C_FP = "aaaabbbbccccdddd"


def _inventory() -> dict[str, Any]:
    return {
        "schema_version": 2, "root": "/abs/path/to/repo", "total_files": 100,
        "total_loc": 12000, "languages": ["python"], "git_available": True,
        "hotspots": [
            {"path": "src/pay/refund.py", "churn": 4, "complexity": 20, "loc": 100, "score": 80.0},
            {"path": "src/pay/gateway.py", "churn": 2, "complexity": 9, "loc": 40, "score": 45.0},
        ],
        "hotspot_band": ["src/pay/refund.py"],
        "files": [
            {"path": "src/pay/refund.py", "path_class": "source", "hotspot_score": 80.0,
             "churn": 4, "coupling_degree": 1, "fan_in_approx": 2, "fan_in_mode": "import-lines"},
            {"path": "src/pay/gateway.py", "path_class": "source", "hotspot_score": 45.0,
             "churn": 2, "coupling_degree": 1, "fan_in_approx": 0, "fan_in_mode": "import-lines"},
        ],
    }


def _coupling() -> dict[str, Any]:
    return {"schema_version": 2, "pairs": [
        {"a": "src/pay/refund.py", "b": "src/pay/gateway.py", "shared_commits": 4,
         "ratio": 0.8, "cross_directory": False}
    ], "degree": {}, "cycles": [], "directories": [], "unstable_edges": []}


def _plan() -> dict[str, Any]:
    return {
        "schema_version": 2, "set": "default", "top": 5, "chunked": False, "thresholds": {},
        "entries": [], "families_run": ["error-masking", "security"],
        "families_skipped": [{"family": "duplication", "reason": "no leads"}],
    }


def _finding(
    fingerprint: str, family: str, title: str, file: str, start: int, end: int, quote: str,
    *, tier: str | None, verdict: str, severity: int = 4, effort: str = "M",
    debt_type: str = "defect", type_id: str | None = "TD-13", proof: str = "",
    confirmed: list[str] | None = None, signals: dict[str, Any] | None = None,
    trap: str | None = None, verified: bool = True,
) -> dict[str, Any]:
    return {
        "fingerprint": fingerprint, "quote_hash": "0" * 40, "family": family,
        "debt_type": debt_type, "type_id": type_id, "title": title, "severity": severity,
        "effort": effort, "source": "scout", "rule_id": None, "note": "n",
        "evidence": [{"file": file, "line_start": start, "line_end": end, "quote": quote,
                      "quote_verified": True}],
        "confirmed_by": confirmed if confirmed is not None else [f"scout:{family}"],
        "signals_cited": [],
        "signals": signals if signals is not None else {
            "hotspot_score": 80.0, "churn": 4, "coupling_degree": 1, "fan_in_approx": 2,
            "path_class": "source", "in_hotspot_band": True},
        "tier": tier, "verdict": verdict, "proof": proof, "checked": [], "opened": [],
        "trap_matched": trap, "verified": verified,
    }


def _verified() -> dict[str, Any]:
    return {"schema_version": 2, "findings": [
        _finding(TOP_FP, "error-masking", "Refund failure swallowed by a bare except",
                 "src/pay/refund.py", 120, 123, "    except Exception:\n        pass",
                 tier="A", verdict="confirm",
                 proof="The catch at lines 120 to 123 returns on any failure and logs nothing.",
                 confirmed=["hotspot", "pattern:swallowed-catch", "scout:error-masking"]),
        _finding(CUT_FP, "security", "Hard-coded credential in the gateway client",
                 "src/pay/gateway.py", 11, 11, 'token = "sk_l***"',
                 tier="B", verdict="confirm", severity=5, effort="S",
                 debt_type="security", type_id="TD-03",
                 proof="A credential-shaped literal sits in source, not in configuration.",
                 confirmed=["scout:security"],
                 signals={"hotspot_score": 45.0, "churn": 2, "coupling_degree": 1,
                          "fan_in_approx": 0, "path_class": "source", "in_hotspot_band": False}),
        _finding(TIER_C_FP, "dead-code", "Unused helper in the ledger module",
                 "src/pay/ledger.py", 40, 41, "def unused_helper():\n    return None",
                 tier="C", verdict="unverified", severity=2, effort="S",
                 debt_type="code", type_id="TD-09", verified=False,
                 signals={"hotspot_score": 0.0, "churn": 0, "coupling_degree": 0,
                          "fan_in_approx": 0, "path_class": "source", "in_hotspot_band": False}),
    ], "stats": {"selected": 2, "verdicts": 2, "unknown_fingerprint": 0, "missing_verdict": 1,
                 "tier_a": 1, "tier_b": 1, "tier_c": 1, "rejected": 0}}


def _ranked() -> dict[str, Any]:
    terms = {"severity": 4, "H": 0.8, "C": 0.4, "F": 0.2, "interest": 2.1,
             "tier_weight": 1.0, "tractability": 0.75, "priority": 6.3}
    return {
        "schema_version": 2, "formula_version": 1, "preset": "balanced", "top": 5,
        "weights": {"wH": 1.0, "wC": 0.5, "wF": 0.5},
        "tractability": {"S": 1.0, "M": 0.75, "L": 0.5},
        "top_n": [TOP_FP],
        "findings": [
            {"fingerprint": TOP_FP, "rank": 1, "priority": 6.3, "terms": terms, "tier": "A",
             "in_top_n": True, "spread_capped": False},
            {"fingerprint": CUT_FP, "rank": 2, "priority": 3.5, "terms": dict(terms, priority=3.5),
             "tier": "B", "in_top_n": False, "spread_capped": False},
            {"fingerprint": TIER_C_FP, "rank": 3, "priority": 0.7,
             "terms": dict(terms, priority=0.7), "tier": "C", "in_top_n": False,
             "spread_capped": False},
        ],
    }


def _candidates() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "candidates": [
            {"fingerprint": TOP_FP}, {"fingerprint": CUT_FP}, {"fingerprint": TIER_C_FP},
        ],
        "open_questions": [
            {"file": "src/pay/refund.py", "line_start": 51,
             "question": "Is audit_trail() wired into a production caller?", "reason": None},
            {"file": "src/pay/ledger.py", "line_start": 12,
             "question": "Ledger rounding drifts on partial refunds", "reason": "quote not found"},
        ],
        "looks_bad_but_fine": [
            {"file": "src/pay/gateway.py", "line_start": 19,
             "why": "One multi-line call, not nested branching."},
        ],
        "stats": {"error-masking": {"raw": 2, "dropped": 0, "quote_failed": 1, "clustered": 0,
                                    "suppressed": 0, "disabled": 0}},
    }


def _write_workdir(workdir: Path, **overrides: Any) -> Path:
    docs = {
        "inventory.json": _inventory(), "coupling.json": _coupling(), "scan-plan.json": _plan(),
        "verified.json": _verified(), "ranked.json": _ranked(), "candidates.json": _candidates(),
    }
    docs.update(overrides)
    for name, doc in docs.items():
        if doc is not None:
            write_json(workdir / name, doc)
    return workdir


def _inputs(tmp_path: Path, **overrides: Any) -> Any:
    return load_inputs(_write_workdir(tmp_path / "wd", **overrides))


# --- frontmatter, header, top N -------------------------------------------------


def test_document_parses_and_carries_the_promotable_findings(tmp_path: Path) -> None:
    """The top-N finding and the compact below-the-cut one both parse back as findings."""
    out = tmp_path / "design.md"
    write_design(_inputs(tmp_path), SCAN_DATE, out)
    raw = out.read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    parsed = parse_design(out)
    assert parsed["metadata"]["schema_version"] == 2
    assert parsed["metadata"]["counts"]["tier_a"] == 1
    assert [f["slug"] for f in parsed["findings"]] == [
        "refund-failure-swallowed-by-a-bare-except",
        "hard-coded-credential-in-the-gateway-client",
    ]
    finding = parsed["findings"][0]
    assert finding["category"] == finding["family"] == "error-masking"
    assert finding["tier"] == "A" and finding["diff"] == "NEW" and finding["priority"] == "6.3"
    assert "Considered and rejected" not in finding["body_md"]


def test_git_absent_omits_the_hotspot_and_coupling_summary(tmp_path: Path) -> None:
    inventory = _inventory()
    inventory["git_available"] = False
    inventory["hotspots"] = []
    inventory["hotspot_band"] = []
    text = render_design(_inputs(tmp_path, **{"inventory.json": inventory,
                                              "coupling.json": {"schema_version": 2, "pairs": []}}),
                         SCAN_DATE)
    assert "Top hotspots:" not in text and "Top coupled pairs:" not in text
    assert "git_available: false" in text
    assert "No git history: churn is 0 and the interest signal is absent." in text


def test_counts_come_from_the_documents(tmp_path: Path) -> None:
    text = render_design(_inputs(tmp_path), SCAN_DATE)
    for line in ("  candidates: 3", "  quote_failed: 1", "  verified: 2", "  tier_a: 1",
                 "  tier_b: 1", "  tier_c: 1", "  unverified: 1", "  rejected: 0",
                 "  suppressed: 0"):
        assert line in text, line
    assert "  new:" not in text and "  resolved:" not in text, "no diff.json in phase 3"


def test_every_written_string_is_redacted(tmp_path: Path) -> None:
    secret = "sk_live_51H8f2kL9mN3pQ7rS4tU6vW"
    verified = _verified()
    verified["findings"][0]["title"] = f'Leaks token = "{secret}" right in the title'
    verified["findings"][0]["proof"] = f'the literal token = "{secret}" sits here'
    verified["findings"][0]["evidence"][0]["quote"] = f'token = "{secret}"'
    text = render_design(_inputs(tmp_path, **{"verified.json": verified}), SCAN_DATE)
    assert secret not in text and "sk_l***" in text


# --- heading-shaped free text (finding 1, fix round 1) --------------------------


def test_proof_with_a_heading_shaped_line_keeps_the_whole_body(tmp_path: Path) -> None:
    """A ``# `` line in the verifier's proof must not truncate Evidence/Signals.

    ``design_parser._ends_section`` ends a finding's section at the next H1 or H2
    outside a fence. ``proof`` is written as raw prose (not inside a fence), so a
    proof whose second line happens to start with ``#`` used to read as a new H1
    and take Evidence, Signals, Remediation and Acceptance criteria out of the
    finding's ``body_md`` -- silently, with ``write_design`` and ``parse_design``
    both reporting success.
    """
    verified = _verified()
    verified["findings"][0]["proof"] = (
        "The catch swallows.\n# TODO: this is a comment the verifier quoted"
    )
    out = tmp_path / "design.md"
    write_design(_inputs(tmp_path, **{"verified.json": verified}), SCAN_DATE, out)
    parsed = parse_design(out)
    body = parsed["findings"][0]["body_md"]
    assert "### Evidence" in body
    assert "### Signals" in body
    assert "\n# TODO: this is a comment the verifier quoted" not in body
    assert "\\# TODO: this is a comment the verifier quoted" in body


def test_self_check_catches_a_free_text_field_that_skips_the_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``write_design`` must fail loudly if a field bypasses the escape helper.

    Constructed by monkeypatching ``free_text`` to a passthrough (plain
    ``redact``, no heading escape), so it is the self-check in ``write_design``
    that has to catch the truncated body, not the escape in ``free_text`` itself.
    """
    import design_writer

    monkeypatch.setattr(design_writer, "free_text", design_writer.redact)
    verified = _verified()
    verified["findings"][0]["proof"] = (
        "The catch swallows.\n# TODO: this is a comment the verifier quoted"
    )
    out = tmp_path / "design.md"
    with pytest.raises(DesignWriteError):
        write_design(_inputs(tmp_path, **{"verified.json": verified}), SCAN_DATE, out)


def test_missing_input_document_is_an_error(tmp_path: Path) -> None:
    workdir = _write_workdir(tmp_path / "wd")
    (workdir / "ranked.json").unlink()
    with pytest.raises((DesignWriteError, FileNotFoundError)):
        load_inputs(workdir)


# --- below the cut, negative space, findings.json --------------------------------


def test_render_matches_the_full_worked_example(tmp_path: Path) -> None:
    text = render_design(_inputs(tmp_path), SCAN_DATE)
    assert text == (GOLDEN / "design-worked-example.md").read_bytes().decode("utf-8")


def test_below_the_cut_findings_are_promotable_and_carry_no_note_sections(tmp_path: Path) -> None:
    out = tmp_path / "design.md"
    write_design(_inputs(tmp_path), SCAN_DATE, out)
    findings = {f["slug"]: f for f in parse_design(out)["findings"]}
    cut = findings["hard-coded-credential-in-the-gateway-client"]
    assert cut["tier"] == "B" and cut["status"] == "pending" and cut["category"] == "security"
    assert "### Proof" in cut["body_md"] and "### Evidence" in cut["body_md"]
    assert "### Signals" not in cut["body_md"]
    assert "### Remediation" not in cut["body_md"]
    assert "tier C and unverified" not in cut["body_md"], "the H1 boundary holds"
    assert ("unused-helper-in-the-ledger-module" not in findings), \
        "tier C is a table row, not a finding"


def test_tier_c_table_and_empty_sections(tmp_path: Path) -> None:
    text = render_design(_inputs(tmp_path), SCAN_DATE)
    assert "| slug | family | file | reason |" in text
    assert (
        "| unused-helper-in-the-ledger-module | dead-code | src/pay/ledger.py | unverified |"
        in text
    )
    assert text.count("_None._") == 1, "only 'Considered and rejected' is empty here"


def test_rejected_and_trap_findings_land_in_their_sections(tmp_path: Path) -> None:
    verified = _verified()
    verified["findings"].append(
        _finding("1111222233334444", "dead-code", "Entry point looks unreferenced",
                 "src/pay/cli.py", 3, 3, "def main():", tier=None, verdict="reject",
                 proof="It is the console entry point declared in pyproject.",
                 trap="Entry points have no in-repository caller and are alive."))
    ranked = _ranked()
    ranked["findings"].append({"fingerprint": "1111222233334444", "rank": 4, "priority": 0.0,
                               "terms": {}, "tier": None, "in_top_n": False,
                               "spread_capped": False})
    text = render_design(_inputs(tmp_path, **{"verified.json": verified, "ranked.json": ranked}),
                         SCAN_DATE)
    rejected = text.split("# Considered and rejected")[1].split("# Looks bad but is fine")[0]
    assert "**Entry point looks unreferenced**" in rejected
    assert "Entry points have no in-repository caller" in rejected
    fine = text.split("# Looks bad but is fine")[1].split("# Open questions")[0]
    assert "One multi-line call, not nested branching." in fine
    assert "Entry points have no in-repository caller" in fine, "a trap rejection appears in both"


def test_open_questions_flag_the_quote_failures(tmp_path: Path) -> None:
    text = render_design(_inputs(tmp_path), SCAN_DATE)
    section = text.split("# Open questions for the maintainer")[1].split("# Not assessed")[0]
    assert "- `src/pay/refund.py:51` - Is audit_trail() wired into a production caller?" in section
    assert "- `src/pay/ledger.py:12` - quote not found: Ledger rounding drifts" in section


def test_findings_json_is_the_machine_readable_twin(tmp_path: Path) -> None:
    workdir = _write_workdir(tmp_path / "wd")
    write_design(load_inputs(workdir), SCAN_DATE, workdir / "design.md")
    doc = json.loads((workdir / "findings.json").read_bytes())
    assert list(doc) == ["schema_version", "findings"]
    assert [f["fingerprint"] for f in doc["findings"]] == [TOP_FP, CUT_FP, TIER_C_FP]
    top = doc["findings"][0]
    assert list(top) == ["fingerprint", "slug", "title", "family", "debt_type", "type_id",
                         "severity", "effort", "evidence", "signals", "confirmed_by", "tier",
                         "verdict", "proof", "priority", "terms", "in_top_n", "spread_capped",
                         "diff"]
    assert top["slug"] == "refund-failure-swallowed-by-a-bare-except"
    assert top["in_top_n"] is True and top["diff"] == "NEW" and top["priority"] == 6.3
    assert doc["findings"][2]["in_top_n"] is False
    raw = (workdir / "findings.json").read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")


def test_findings_json_feeds_evaluate(tmp_path: Path) -> None:
    """evaluate.load_findings prefers findings.json; the writer must satisfy it."""
    from evaluate import load_findings

    workdir = _write_workdir(tmp_path / "wd")
    write_design(load_inputs(workdir), SCAN_DATE, workdir / "design.md")
    findings, name = load_findings(workdir)
    assert name == "findings.json" and len(findings) == 3
    assert {f["tier"] for f in findings} == {"A", "B", "C"}


# --- evidence fences (controller ruling, fix round 2) ---------------------------


def test_a_quote_that_contains_a_fence_gets_a_longer_fence(tmp_path: Path) -> None:
    """A quote holding ``` lines must not terminate the evidence fence early.

    A Markdown or Ruby fixture is inventoried, so an evidence quote carrying a
    fenced block is reachable. Wrapped in a plain three-backtick fence, the
    quote's own ``` closes the writer's fence and everything after it renders as
    prose rather than as part of the quote. The writer opens with one more
    backtick than the longest run inside the quote instead, which is what the
    byte assertion below pins; the round-trip assertions guard the parse.

    This particular quote (a complete, balanced inner fence) carries an *even*
    number of backtick-run lines together with the writer's own wrapper, so it
    round-trips even under a length-agnostic parser -- it does not by itself
    prove the read side cooperates. See the test below for the case that does.
    """
    verified = _verified()
    verified["findings"][0]["evidence"][0]["quote"] = 'DOC = """\n```python\nvalue = 1\n```\n"""'
    out = tmp_path / "design.md"
    write_design(_inputs(tmp_path, **{"verified.json": verified}), SCAN_DATE, out)
    text = out.read_text(encoding="utf-8")
    assert '\n````\nDOC = """\n```python\nvalue = 1\n```\n"""\n````\n' in text
    body = parse_design(out)["findings"][0]["body_md"]
    assert "```python\nvalue = 1\n```" in body
    assert "### Signals" in body, "the fenced quote did not truncate the section"


def test_a_quote_with_an_unbalanced_inner_fence_round_trips_end_to_end(tmp_path: Path) -> None:
    """The odd-count case Task 4's report flagged as the still-open defect.

    A quote holding a single, unbalanced ```` ``` ```` line (a fixture snippet
    quoted mid-fence, e.g. a truncated Markdown or Ruby excerpt) makes the
    writer open a four-backtick wrapper (one more than the quote's own longest
    run of three) -- but the wrapper plus the quote's lone marker is an *odd*
    total of backtick-run lines. Before design_parser's fence tracking was made
    length-aware, this exact shape made the parser's flat parity toggle end the
    document still "in a fence": DesignParseError, caught by write_design's
    self-check and re-raised as DesignWriteError -- the render aborted and the
    user got no design.md at all, regardless of how wide the writer's own fence
    was. With the parser now recognising that the quote's three-backtick line
    is shorter than the wrapper's four and so cannot close it, the whole thing
    renders, parses, and the quote survives whole in the body.
    """
    verified = _verified()
    verified["findings"][0]["evidence"][0]["quote"] = (
        "Example:\n```\nsnippet without a closing fence"
    )
    out = tmp_path / "design.md"
    write_design(_inputs(tmp_path, **{"verified.json": verified}), SCAN_DATE, out)
    text = out.read_text(encoding="utf-8")
    assert "\n````\nExample:\n```\nsnippet without a closing fence\n````\n" in text
    body = parse_design(out)["findings"][0]["body_md"]
    assert "Example:\n```\nsnippet without a closing fence" in body
    assert "### Signals" in body, "the unbalanced inner fence did not truncate the section"


def test_a_scan_with_no_negative_space_renders_none_for_every_empty_section(
    tmp_path: Path,
) -> None:
    """No section is ever a bare heading; ``Not assessed`` still names its four limits."""
    verified = _verified()
    verified["findings"] = verified["findings"][:1]
    ranked = _ranked()
    ranked["findings"] = ranked["findings"][:1]
    plan = _plan()
    plan["families_skipped"] = []
    candidates = _candidates()
    candidates["open_questions"] = []
    candidates["looks_bad_but_fine"] = []
    text = render_design(
        _inputs(tmp_path, **{"verified.json": verified, "ranked.json": ranked,
                             "scan-plan.json": plan, "candidates.json": candidates}),
        SCAN_DATE,
    )
    assert text.count("_None._") == 5, "below the cut, tier C, rejected, fine, questions"
    assert "# Below the cut\n\n_None._\n" in text
    assert "- Families not run: none" in text
    assert text.endswith("class-level metrics that need a parser\n")


# --- fix round 1: free-text guard, self-check headings, findings.json location ---


def test_free_text_escapes_heading_shaped_lines_in_every_negative_space_field(
    tmp_path: Path,
) -> None:
    """Item 2: all four new free-text call sites escape a heading-shaped line.

    Every existing fixture string is escape-neutral (no fixture starts a line
    with ``#``), so a test built only from those fixtures would stay green
    even if a call site quietly dropped ``free_text`` for a bare ``redact``.
    This test seeds a ``# ``-shaped line into each of the four fields the
    controller named -- a rejection's ``proof``, a second rejection's
    ``trap_matched``, a ``looks_bad_but_fine`` ``why``, and an
    ``open_questions`` question -- and asserts each renders escaped
    (``\\#``) and that the document's top-level headings are exactly
    ``SECTION_ORDER`` (after the fixed scan header), unchanged: no spurious
    heading spliced into the document by any of the four.
    """
    verified = _verified()
    verified["findings"].append(
        _finding("2222333344445555", "dead-code", "Rejected via its proof",
                 "src/pay/misc1.py", 1, 1, "pass", tier=None, verdict="reject",
                 proof="fine because\n# Not assessed\nreally proof"))
    verified["findings"].append(
        _finding("3333444455556666", "dead-code", "Rejected via its trap",
                 "src/pay/misc2.py", 1, 1, "pass", tier=None, verdict="reject",
                 proof="ignored: trap_matched wins",
                 trap="fine because\n# Not assessed\nreally trap"))
    ranked = _ranked()
    ranked["findings"] += [
        {"fingerprint": "2222333344445555", "rank": 4, "priority": 0.0, "terms": {},
         "tier": None, "in_top_n": False, "spread_capped": False},
        {"fingerprint": "3333444455556666", "rank": 5, "priority": 0.0, "terms": {},
         "tier": None, "in_top_n": False, "spread_capped": False},
    ]
    candidates = _candidates()
    candidates["open_questions"].append(
        {"file": "src/pay/misc3.py", "line_start": 9,
         "question": "fine because\n# Not assessed\nreally question", "reason": None})
    candidates["looks_bad_but_fine"].append(
        {"file": "src/pay/misc4.py", "line_start": 9,
         "why": "fine because\n# Not assessed\nreally why"})

    text = render_design(
        _inputs(tmp_path, **{"verified.json": verified, "ranked.json": ranked,
                             "candidates.json": candidates}),
        SCAN_DATE,
    )
    # 5, not 4: a trap_matched rejection's text is rendered twice by design (once
    # under "Considered and rejected", once under "Looks bad but is fine"), so
    # the trap field's escaped heading line appears in both places.
    assert text.count("\\# Not assessed") == 5, "all four fields escaped their heading line"

    # If any of the four fields had rendered its heading-shaped line unescaped,
    # an extra "Not assessed" (or similar) H1 would appear among the document's
    # top-level headings, breaking this exact match against SECTION_ORDER.
    headings = [line[2:].strip() for line in text.split("\n") if line.startswith("# ")]
    headings = ["Top" if h.startswith("Top ") else h for h in headings[1:]]  # drop scan header
    assert headings == list(SECTION_ORDER)
    assert headings.count("Not assessed") == 1, "no spurious heading was spliced in"


def test_self_check_catches_unescaped_free_text_in_the_negative_space_sections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Item 2: the self-check must see the negative-space sections too.

    Before this fix, ``write_design``'s self-check only inspected the bodies
    ``parse_design`` returns for H2 findings; a heading-shaped line escaping
    into "Looks bad but is fine" was invisible to it, because ``parse_design``
    never returns the prose between H1 sections at all -- it only tracks
    finding sections. Simulated here by monkeypatching ``free_text`` to a bare
    ``redact`` (as if a call site forgot the escape), so it is the new
    headings check that has to catch this, not ``free_text`` itself.
    """
    import design_writer

    monkeypatch.setattr(design_writer, "free_text", design_writer.redact)
    candidates = _candidates()
    candidates["looks_bad_but_fine"].append(
        {"file": "src/pay/misc.py", "line_start": 9,
         "why": "fine because\n# Not assessed\nreally"})
    out = tmp_path / "design.md"
    with pytest.raises(DesignWriteError, match="Not assessed"):
        write_design(_inputs(tmp_path, **{"candidates.json": candidates}), SCAN_DATE, out)


def test_a_failed_self_check_writes_neither_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Item 3: design.md and findings.json are written only after the self-check passes.

    Before this fix, ``design.md`` (and the ``findings.json`` beside it) were
    written to disk before ``parse_design`` ran, so a self-check failure still
    left a ``findings.json`` on disk for a later ``evaluate.load_findings`` to
    prefer over ``verified.json`` -- a rejected render, silently treated as if
    it had succeeded downstream.
    """
    import design_writer

    monkeypatch.setattr(design_writer, "free_text", design_writer.redact)
    verified = _verified()
    verified["findings"][0]["proof"] = "swallow\n# TODO: heading-shaped, unescaped"
    workdir = _write_workdir(tmp_path / "wd", **{"verified.json": verified})
    out = workdir / "design.md"
    with pytest.raises(DesignWriteError):
        write_design(load_inputs(workdir), SCAN_DATE, out)
    assert not out.exists(), "design.md must not be written when the self-check fails"
    assert not (workdir / "findings.json").exists(), \
        "findings.json must not be written when the self-check fails"


def test_findings_json_always_lands_in_the_workdir_even_when_out_is_elsewhere(
    tmp_path: Path,
) -> None:
    """Item 4: ``findings.json`` follows ``inputs.workdir``, never ``--out``.

    ``evaluate.py`` looks for ``findings.json`` in the workdir it is given, not
    beside whatever path ``design.md`` was written to. Before this fix,
    ``findings.json`` was written beside ``out_path``, so a ``--out`` pointed
    outside the workdir hid it from ``evaluate.py``.
    """
    workdir = _write_workdir(tmp_path / "wd")
    elsewhere = tmp_path / "elsewhere" / "design.md"
    write_design(load_inputs(workdir), SCAN_DATE, elsewhere)
    assert elsewhere.exists()
    assert (workdir / "findings.json").exists()
    assert not (elsewhere.parent / "findings.json").exists()


def test_render_cli_prints_both_output_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Item 4: the CLI reports both ``design.md`` and ``findings.json`` on success."""
    from design_writer import _main

    workdir = _write_workdir(tmp_path / "wd")
    out = tmp_path / "elsewhere" / "design.md"
    assert _main(["render", "--workdir", str(workdir), "--scan-date", SCAN_DATE,
                  "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert str(out) in printed
    assert str(workdir / "findings.json") in printed
