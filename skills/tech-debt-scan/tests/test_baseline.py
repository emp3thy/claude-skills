"""Tests for baseline.py (spec 4.10)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

TODAY = "2026-09-07"


def _finding(**over) -> dict:
    base = {
        "fingerprint": "aaaaaaaaaaaaaaaa", "family": "error-masking",
        "title": "Empty catch swallows write failure",
        "tier": "A", "quote_hash": "q" * 40,
        "evidence": [{"file": "src/pay/refund.py", "line_start": 33, "line_end": 33,
                      "quote": "except Exception:", "quote_verified": True}],
    }
    base.update(over)
    return base


def _entry(**over) -> dict:
    base = {
        "family": "error-masking", "file": "src/pay/refund.py", "line_start": 33,
        "quote_hash": "q" * 40, "title": "Empty catch swallows write failure", "tier": "A",
        "status": "pending", "first_seen": "2026-09-01", "last_seen": "2026-09-01",
        "reason": None, "until": None, "bundle": None,
    }
    base.update(over)
    return base


def _baseline(**entries) -> dict:
    return {"schema_version": 2, "last_scan": "2026-09-01", "preset": "balanced",
            "findings": entries}


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return tmp_path


class TestLoadBaseline:
    def test_absent_file_is_none(self, tmp_path: Path) -> None:
        from baseline import load_baseline

        assert load_baseline(tmp_path / "baseline.json") is None

    def test_wrong_schema_version_raises(self, tmp_path: Path) -> None:
        from baseline import BaselineError, load_baseline

        path = tmp_path / "baseline.json"
        path.write_text(json.dumps({"schema_version": 1, "findings": {}}), encoding="utf-8")
        with pytest.raises(BaselineError, match="schema_version"):
            load_baseline(path)

    def test_round_trips_every_field(self, tmp_path: Path) -> None:
        from baseline import load_baseline

        doc = _baseline(aaaaaaaaaaaaaaaa=_entry(status="accepted", reason="tracked in JIRA-1",
                                                until="2027-01-01", bundle="chore-x-2026-09-01"))
        path = tmp_path / "baseline.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        assert load_baseline(path) == doc


class TestTitleTokens:
    def test_lowercases_and_splits_on_non_alphanumerics(self) -> None:
        from baseline import title_tokens

        assert title_tokens("Empty catch, swallows-write failure!") == {
            "empty", "catch", "swallows", "write", "failure",
        }

    def test_stop_words_are_kept(self) -> None:
        """Spec 4.10 says half the tokens, not half the interesting ones."""
        from baseline import title_tokens

        assert "the" in title_tokens("the empty catch")


class TestClassify:
    def test_fingerprint_match_is_unchanged(self, tmp_path: Path) -> None:
        from baseline import classify

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 32 + "except Exception:\n"})
        out = classify(_finding(), _baseline(aaaaaaaaaaaaaaaa=_entry()), root, TODAY)
        assert out.diff == "UNCHANGED"
        assert out.matched == "aaaaaaaaaaaaaaaa"
        assert out.note is None

    def test_same_fingerprint_at_another_line_is_moved(self, tmp_path: Path) -> None:
        """The fingerprint carries no line, so a quote that moved keeps its
        fingerprint; the baseline's recorded line is what differs."""
        from baseline import classify

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 40 + "except Exception:\n"})
        finding = _finding(evidence=[{"file": "src/pay/refund.py", "line_start": 41,
                                      "line_end": 41, "quote": "except Exception:",
                                      "quote_verified": True}])
        out = classify(finding, _baseline(aaaaaaaaaaaaaaaa=_entry(line_start=33)), root, TODAY)
        assert out.diff == "UNCHANGED (moved)"
        assert out.matched == "aaaaaaaaaaaaaaaa"

    def test_a_one_line_move_is_still_moved(self, tmp_path: Path) -> None:
        """`moved` is any difference, not just a large one."""
        from baseline import classify

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 33 + "except Exception:\n"})
        finding = _finding(evidence=[{"file": "src/pay/refund.py", "line_start": 34,
                                      "line_end": 34, "quote": "except Exception:",
                                      "quote_verified": True}])
        out = classify(finding, _baseline(aaaaaaaaaaaaaaaa=_entry(line_start=33)), root, TODAY)
        assert out.diff == "UNCHANGED (moved)"
        assert out.matched == "aaaaaaaaaaaaaaaa"

    def test_edited_match_shares_half_the_tokens_within_forty_lines(self, tmp_path: Path) -> None:
        from baseline import classify

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 80})
        # Baseline title has 5 tokens; the new title shares 3 of them (>= half).
        finding = _finding(fingerprint="bbbbbbbbbbbbbbbb", quote_hash="r" * 40,
                           title="Empty catch hides failure silently",
                           evidence=[{"file": "src/pay/refund.py", "line_start": 73,
                                      "line_end": 73, "quote": "except:", "quote_verified": True}])
        base = _baseline(aaaaaaaaaaaaaaaa=_entry(line_start=33))
        out = classify(finding, base, root, TODAY)
        assert out.diff == "UNCHANGED (edited)"
        assert out.matched == "aaaaaaaaaaaaaaaa"

    def test_edited_match_at_exactly_half_the_tokens(self, tmp_path: Path) -> None:
        from baseline import classify

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 80})
        # Baseline title has 4 tokens; the new title shares exactly 2 of them (= half).
        # Base: {"error", "catch", "missing", "handler"}
        # New:  {"catch", "error", "in", "callback"}
        # Shared: {"catch", "error"} = 2, which is exactly 50% (shared * 2 >= 4).
        finding = _finding(fingerprint="cccccccccccccccc", quote_hash="t" * 40,
                           title="catch error in callback",
                           evidence=[{"file": "src/pay/refund.py", "line_start": 40,
                                      "line_end": 40, "quote": "except:", "quote_verified": True}])
        base = _baseline(aaaaaaaaaaaaaaaa=_entry(title="error catch missing handler",
                                                 line_start=33))
        out = classify(finding, base, root, TODAY)
        assert out.diff == "UNCHANGED (edited)"
        assert out.matched == "aaaaaaaaaaaaaaaa"

    def test_edited_requires_at_least_half_not_fewer(self, tmp_path: Path) -> None:
        from baseline import classify

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 80})
        # Baseline title has 5 tokens; the new title shares exactly 2 (< half).
        finding = _finding(fingerprint="bbbbbbbbbbbbbbbb", quote_hash="r" * 40,
                           title="Empty catch around nothing",
                           evidence=[{"file": "src/pay/refund.py", "line_start": 35,
                                      "line_end": 35, "quote": "except:", "quote_verified": True}])
        out = classify(finding, _baseline(aaaaaaaaaaaaaaaa=_entry(line_start=33)), root, TODAY)
        assert out.diff == "NEW"

    def test_edited_requires_forty_lines_not_forty_one(self, tmp_path: Path) -> None:
        from baseline import classify

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 80})
        finding = _finding(fingerprint="bbbbbbbbbbbbbbbb", quote_hash="r" * 40,
                           title="Empty catch swallows write failure",
                           evidence=[{"file": "src/pay/refund.py", "line_start": 74,
                                      "line_end": 74, "quote": "except:", "quote_verified": True}])
        out = classify(finding, _baseline(aaaaaaaaaaaaaaaa=_entry(line_start=33)), root, TODAY)
        assert out.diff == "NEW"

    def test_edited_requires_the_same_family(self, tmp_path: Path) -> None:
        from baseline import classify

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 80})
        finding = _finding(fingerprint="bbbbbbbbbbbbbbbb", family="security", quote_hash="r" * 40)
        out = classify(finding, _baseline(aaaaaaaaaaaaaaaa=_entry(line_start=33)), root, TODAY)
        assert out.diff == "NEW"

    def test_edited_match_requires_a_line_on_the_finding_side(self, tmp_path: Path) -> None:
        """An osv-scanner finding always has `line_start: null` (spec 4.6). The
        forty-line window has no "near" to check without a line on both sides,
        so it can never match by the edited heuristic -- fingerprint or NEW."""
        from baseline import classify

        root = _repo(tmp_path, {"requirements.txt": "x\n" * 80})
        finding = _finding(fingerprint="bbbbbbbbbbbbbbbb", quote_hash="r" * 40,
                           family="dependency", title="Empty catch swallows write failure",
                           evidence=[{"file": "requirements.txt", "line_start": None,
                                      "line_end": None, "quote": "numpy==1.0",
                                      "quote_verified": True}])
        base = _baseline(aaaaaaaaaaaaaaaa=_entry(family="dependency", file="requirements.txt",
                                                  line_start=9999))
        out = classify(finding, base, root, TODAY)
        assert out.diff == "NEW"

    def test_edited_match_requires_a_line_on_the_baseline_side(self, tmp_path: Path) -> None:
        """Mirror of the above: a baseline entry recorded without a line (also
        an osv-scanner shape) is likewise never a candidate for an edited match."""
        from baseline import classify

        root = _repo(tmp_path, {"requirements.txt": "x\n" * 80})
        finding = _finding(fingerprint="bbbbbbbbbbbbbbbb", quote_hash="r" * 40,
                           family="dependency", title="Empty catch swallows write failure",
                           evidence=[{"file": "requirements.txt", "line_start": 33,
                                      "line_end": 33, "quote": "numpy==1.0",
                                      "quote_verified": True}])
        base = _baseline(aaaaaaaaaaaaaaaa=_entry(family="dependency", file="requirements.txt",
                                                  line_start=None))
        out = classify(finding, base, root, TODAY)
        assert out.diff == "NEW"

    def test_no_match_at_all_is_new(self, tmp_path: Path) -> None:
        from baseline import classify

        root = _repo(tmp_path, {"src/other.py": "y\n"})
        finding = _finding(fingerprint="cccccccccccccccc", quote_hash="s" * 40,
                           evidence=[{"file": "src/other.py", "line_start": 1, "line_end": 1,
                                      "quote": "y", "quote_verified": True}])
        out = classify(finding, _baseline(aaaaaaaaaaaaaaaa=_entry()), root, TODAY)
        assert out.diff == "NEW"
        assert out.matched is None

    def test_absent_baseline_is_new(self, tmp_path: Path) -> None:
        from baseline import classify

        out = classify(_finding(), None, tmp_path, TODAY)
        assert out.diff == "NEW"

    def test_rejected_match_is_suppressed(self, tmp_path: Path) -> None:
        from baseline import classify

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 32 + "except Exception:\n"})
        base = _baseline(aaaaaaaaaaaaaaaa=_entry(status="rejected", reason="intentional"))
        out = classify(_finding(), base, root, TODAY)
        assert out.suppressed_as == "rejected"
        assert out.matched == "aaaaaaaaaaaaaaaa"
        assert out.diff == "UNCHANGED"

    def test_unexpired_accepted_match_is_suppressed(self, tmp_path: Path) -> None:
        from baseline import classify

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 32 + "except Exception:\n"})
        base = _baseline(aaaaaaaaaaaaaaaa=_entry(status="accepted", until="2027-01-01"))
        out = classify(_finding(), base, root, TODAY)
        assert out.suppressed_as == "accepted"
        assert out.diff == "UNCHANGED"

    def test_expired_accepted_match_returns_as_unchanged_with_a_note(self, tmp_path: Path) -> None:
        from baseline import classify

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 32 + "except Exception:\n"})
        base = _baseline(aaaaaaaaaaaaaaaa=_entry(status="accepted", until="2026-09-01"))
        out = classify(_finding(), base, root, TODAY)
        assert out.suppressed_as is None
        assert out.diff == "UNCHANGED"
        assert out.note == "acceptance expired"

    def test_malformed_until_is_treated_as_expired(self, tmp_path: Path) -> None:
        """An `until` that isn't a parseable date fails safe: the finding
        returns and says why, instead of suppressing silently forever."""
        from baseline import classify

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 32 + "except Exception:\n"})
        base = _baseline(aaaaaaaaaaaaaaaa=_entry(status="accepted", until="soon"))
        out = classify(_finding(), base, root, TODAY)
        assert out.suppressed_as is None
        assert out.diff == "UNCHANGED"
        assert out.note == "until is not a date"

    def test_accepted_expiring_today_is_still_suppressed(self, tmp_path: Path) -> None:
        """`until` is inclusive: the acceptance holds through its last day."""
        from baseline import classify

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 32 + "except Exception:\n"})
        base = _baseline(aaaaaaaaaaaaaaaa=_entry(status="accepted", until=TODAY))
        assert classify(_finding(), base, root, TODAY).suppressed_as == "accepted"

    def test_suppression_through_an_edited_match_is_noted(self, tmp_path: Path) -> None:
        """A rejected entry matched only by the edited heuristic suppresses the
        new finding, and says so, because that inference can be wrong."""
        from baseline import classify

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 80})
        finding = _finding(fingerprint="bbbbbbbbbbbbbbbb", quote_hash="r" * 40,
                           title="Empty catch hides failure silently",
                           evidence=[{"file": "src/pay/refund.py", "line_start": 40,
                                      "line_end": 40, "quote": "except:", "quote_verified": True}])
        base = _baseline(aaaaaaaaaaaaaaaa=_entry(status="rejected", reason="by design"))
        out = classify(finding, base, root, TODAY)
        assert out.suppressed_as == "rejected"
        assert out.note == "suppressed by edited match"


class TestPrimary:
    def test_bool_line_start_is_excluded(self) -> None:
        """`bool` is an `int` subclass; a boolean is never a line number
        (matches the guard in merge_findings.py:129)."""
        from baseline import _primary

        _, line = _primary({"evidence": [{"file": "src/x.py", "line_start": True}]})
        assert line is None
