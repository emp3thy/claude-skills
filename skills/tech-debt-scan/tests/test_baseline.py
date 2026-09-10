"""Tests for baseline.py (spec 4.10)."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

GOLDEN_DESIGN = Path(__file__).parent / "golden" / "service-py" / "design.md"
GOLDEN_VERIFIED = Path(__file__).parent / "golden" / "service-py" / "verified.json"

# The pinned "now" for every classification and record below. Deliberately a
# date in the past: when this file was written TODAY equalled the wall clock,
# so a mutant reading date.today() instead of the `today` it was passed would
# have passed every one of these tests on the day they were written.
TODAY = "2026-04-15"

# Distinct from TODAY on purpose: TestRunRecordCLI drives --today through argparse
# and asserts it lands in the baseline, so its pin must differ from the real
# wall-clock date, or a mutant that ignores args.today and reads the clock could
# pass by coincidence on the day the test happens to run.
CLI_TODAY = "2026-01-15"


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
        "status": "pending", "first_seen": "2026-04-01", "last_seen": "2026-04-01",
        "reason": None, "until": None,
    }
    base.update(over)
    return base


def _baseline(**entries) -> dict:
    return {"schema_version": 2, "last_scan": "2026-04-01", "preset": "balanced",
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
                                                until="2027-01-01", bundle="chore-x-2026-04-01"))
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
        base = _baseline(aaaaaaaaaaaaaaaa=_entry(status="accepted", until="2026-04-01"))
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

    def test_edited_match_reports_an_expired_acceptance(self, tmp_path: Path) -> None:
        """Ruling 23: an edited match against an entry whose acceptance has
        expired must report the same note a direct match would, not None."""
        from baseline import classify

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 80})
        finding = _finding(fingerprint="bbbbbbbbbbbbbbbb", quote_hash="r" * 40,
                           title="Empty catch hides failure silently",
                           evidence=[{"file": "src/pay/refund.py", "line_start": 40,
                                      "line_end": 40, "quote": "except:", "quote_verified": True}])
        base = _baseline(aaaaaaaaaaaaaaaa=_entry(status="accepted", until="2026-01-01"))
        out = classify(finding, base, root, TODAY)
        assert out.diff == "UNCHANGED (edited)"
        assert out.note == "acceptance expired"
        assert out.suppressed_as is None

    def test_edited_match_reports_a_malformed_until(self, tmp_path: Path) -> None:
        """Same, but the matched entry's `until` cannot be parsed as a date."""
        from baseline import classify

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 80})
        finding = _finding(fingerprint="bbbbbbbbbbbbbbbb", quote_hash="r" * 40,
                           title="Empty catch hides failure silently",
                           evidence=[{"file": "src/pay/refund.py", "line_start": 40,
                                      "line_end": 40, "quote": "except:", "quote_verified": True}])
        base = _baseline(aaaaaaaaaaaaaaaa=_entry(status="accepted", until="soon"))
        out = classify(finding, base, root, TODAY)
        assert out.diff == "UNCHANGED (edited)"
        assert out.note == "until is not a date"
        assert out.suppressed_as is None


class TestPrimary:
    def test_bool_line_start_is_excluded(self) -> None:
        """`bool` is an `int` subclass; a boolean is never a line number
        (matches the guard in merge_findings.py:129)."""
        from baseline import _primary

        _, line = _primary({"evidence": [{"file": "src/x.py", "line_start": True}]})
        assert line is None


class TestDiff:
    def _verified(self, *findings: dict) -> dict:
        return {"schema_version": 2, "findings": list(findings)}

    def test_absent_baseline_marks_everything_new(self, tmp_path: Path) -> None:
        from baseline import diff

        out = diff(self._verified(_finding()), None, tmp_path, TODAY)
        assert out["baseline_found"] is False
        assert out["status"]["aaaaaaaaaaaaaaaa"]["diff"] == "NEW"
        assert out["counts"] == {"new": 1, "unchanged": 0, "moved": 0, "edited": 0,
                                 "resolved": 0, "suppressed": 0, "expired": 0}

    def test_an_unmatched_entry_with_no_quote_and_file_present_stays_open(
        self, tmp_path: Path
    ) -> None:
        """An entry with no usable quote cannot be searched for. Resolving means
        the code that carried the debt is gone, not that we simply cannot look,
        so with its file present the entry stays open -- absent from ``status``
        and uncounted -- rather than being presumed resolved."""
        from baseline import diff

        root = _repo(tmp_path, {"src/pay/refund.py": "nothing here\n"})
        base = _baseline(aaaaaaaaaaaaaaaa=_entry())
        out = diff(self._verified(), base, root, TODAY)
        assert "aaaaaaaaaaaaaaaa" not in out["status"]
        assert out["counts"]["resolved"] == 0

    def test_an_unmatched_rejected_entry_with_no_quote_stays_suppressed(
        self, tmp_path: Path
    ) -> None:
        """The RESOLVED loop runs over every unmatched entry, suppressed ones
        included. A rejected entry with no quote must not silently lose its
        suppression the first scan that fails to reproduce its fingerprint."""
        from baseline import diff

        root = _repo(tmp_path, {"src/pay/refund.py": "nothing here\n"})
        base = _baseline(aaaaaaaaaaaaaaaa=_entry(status="rejected", reason="by design"))
        out = diff(self._verified(), base, root, TODAY)
        assert "aaaaaaaaaaaaaaaa" not in out["status"]
        assert out["counts"]["resolved"] == 0

    def test_an_unmatched_entry_whose_file_is_gone_is_resolved(self, tmp_path: Path) -> None:
        from baseline import diff

        out = diff(self._verified(), _baseline(aaaaaaaaaaaaaaaa=_entry()), tmp_path, TODAY)
        assert out["status"]["aaaaaaaaaaaaaaaa"]["diff"] == "RESOLVED"
        assert out["status"]["aaaaaaaaaaaaaaaa"]["note"] == "file absent"

    def test_an_unmatched_entry_whose_file_is_a_directory_is_resolved(
        self, tmp_path: Path
    ) -> None:
        """No quote can live in a directory, so this is resolved -- but the note
        should say what actually happened rather than claiming absence."""
        from baseline import diff

        (tmp_path / "src" / "pay" / "refund.py").mkdir(parents=True)
        base = _baseline(aaaaaaaaaaaaaaaa=_entry())
        out = diff(self._verified(), base, tmp_path, TODAY)
        assert out["status"]["aaaaaaaaaaaaaaaa"]["diff"] == "RESOLVED"
        assert out["status"]["aaaaaaaaaaaaaaaa"]["note"] == "file is a directory"

    def test_an_unmatched_entry_whose_quote_still_exists_is_not_resolved(
        self, tmp_path: Path
    ) -> None:
        """The scan simply did not raise it this time; it is neither resolved nor
        current, so it is absent from status and counted nowhere."""
        from baseline import diff

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 32 + "except Exception:\n"})
        base = _baseline(aaaaaaaaaaaaaaaa=_entry())
        base["findings"]["aaaaaaaaaaaaaaaa"]["quote"] = "except Exception:"
        out = diff(self._verified(), base, root, TODAY)
        assert "aaaaaaaaaaaaaaaa" not in out["status"]
        assert out["counts"]["resolved"] == 0

    def test_suppressed_findings_are_listed_not_statused(self, tmp_path: Path) -> None:
        from baseline import diff

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 32 + "except Exception:\n"})
        base = _baseline(aaaaaaaaaaaaaaaa=_entry(status="rejected", reason="by design"))
        out = diff(self._verified(_finding()), base, root, TODAY)
        assert "aaaaaaaaaaaaaaaa" not in out["status"]
        assert out["suppressed"] == [{"fingerprint": "aaaaaaaaaaaaaaaa", "status": "rejected",
                                      "reason": "by design"}]
        assert out["counts"]["suppressed"] == 1

    def test_expired_acceptance_is_counted(self, tmp_path: Path) -> None:
        from baseline import diff

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 32 + "except Exception:\n"})
        base = _baseline(aaaaaaaaaaaaaaaa=_entry(status="accepted", until="2026-01-01"))
        out = diff(self._verified(_finding()), base, root, TODAY)
        assert out["status"]["aaaaaaaaaaaaaaaa"]["note"] == "acceptance expired"
        assert out["counts"]["expired"] == 1

    def test_malformed_until_is_counted_as_expired(self, tmp_path: Path) -> None:
        """Task 1's ruling: a malformed `until` returns the finding under a
        different note (`until is not a date`) but must still count as expired,
        since `diff` returns the finding for the same reason either way."""
        from baseline import diff

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 32 + "except Exception:\n"})
        base = _baseline(aaaaaaaaaaaaaaaa=_entry(status="accepted", until="soon"))
        out = diff(self._verified(_finding()), base, root, TODAY)
        assert out["status"]["aaaaaaaaaaaaaaaa"]["note"] == "until is not a date"
        assert out["counts"]["expired"] == 1

    def test_expired_acceptance_through_an_edited_match_is_counted(self, tmp_path: Path) -> None:
        """Ruling 23: `diff()` already counts `acceptance expired` and `until is
        not a date` notes wherever they land; this proves an edited match's
        expiry note now reaches that count too, instead of being lost as
        `note: None` and left out of both `counts["expired"]` and the edited
        classification's visibility as an expired acceptance."""
        from baseline import diff

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 80})
        finding = _finding(fingerprint="bbbbbbbbbbbbbbbb", quote_hash="r" * 40,
                           title="Empty catch hides failure silently",
                           evidence=[{"file": "src/pay/refund.py", "line_start": 40,
                                      "line_end": 40, "quote": "except:", "quote_verified": True}])
        base = _baseline(aaaaaaaaaaaaaaaa=_entry(status="accepted", until="2026-01-01"))
        out = diff(self._verified(finding), base, root, TODAY)
        assert out["status"]["bbbbbbbbbbbbbbbb"]["diff"] == "UNCHANGED (edited)"
        assert out["status"]["bbbbbbbbbbbbbbbb"]["note"] == "acceptance expired"
        assert out["counts"]["expired"] == 1
        assert out["counts"]["edited"] == 1
        assert out["suppressed"] == []

    def test_counts_sum_over_every_classification(self, tmp_path: Path) -> None:
        from baseline import diff

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 80, "src/gone.py": "z\n"})
        moved = _finding(evidence=[{"file": "src/pay/refund.py", "line_start": 41,
                                    "line_end": 41, "quote": "except Exception:",
                                    "quote_verified": True}])
        edited = _finding(fingerprint="bbbbbbbbbbbbbbbb", quote_hash="r" * 40,
                          title="Empty catch hides failure silently",
                          evidence=[{"file": "src/pay/refund.py", "line_start": 60,
                                     "line_end": 60, "quote": "except:", "quote_verified": True}])
        new = _finding(fingerprint="cccccccccccccccc", quote_hash="s" * 40, family="security",
                       evidence=[{"file": "src/gone.py", "line_start": 1, "line_end": 1,
                                  "quote": "z", "quote_verified": True}])
        base = _baseline(
            aaaaaaaaaaaaaaaa=_entry(line_start=33),
            dddddddddddddddd=_entry(file="src/pay/refund.py", line_start=70,
                                    title="Entirely different wording here", quote="absent"),
            eeeeeeeeeeeeeeee=_entry(file="src/missing.py", line_start=1, quote="gone"),
        )
        out = diff(self._verified(moved, edited, new), base, root, TODAY)
        assert out["counts"] == {"new": 1, "unchanged": 0, "moved": 1, "edited": 1,
                                 "resolved": 2, "suppressed": 0, "expired": 0}

    def test_the_document_has_the_spec_shape(self, tmp_path: Path) -> None:
        from baseline import diff

        out = diff(self._verified(), None, tmp_path, TODAY)
        assert set(out) == {"schema_version", "baseline_found", "status", "suppressed", "counts"}
        assert out["schema_version"] == 2


def _git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text(".tech-debt/\n", encoding="utf-8")
    return tmp_path


def _decision(**over) -> dict:
    base = {"fingerprint": "aaaaaaaaaaaaaaaa", "status": "approved", "family": "error-masking",
            "title": "Empty catch swallows write failure", "tier": "A",
            "reason": None, "until": None}
    base.update(over)
    return base


class TestRecord:
    def test_writes_every_field_and_round_trips(self, tmp_path: Path) -> None:
        from baseline import load_baseline, record

        path = tmp_path / ".tech-debt" / "baseline.json"
        doc = record(path, decisions=[_decision(status="accepted", reason="tracked",
                                                until="2027-01-01")],
                     findings=[_finding()], today=TODAY, preset="balanced")
        entry = doc["findings"]["aaaaaaaaaaaaaaaa"]
        assert entry == {"family": "error-masking", "file": "src/pay/refund.py", "line_start": 33,
                         "quote_hash": "q" * 40, "quote": "except Exception:",
                         "title": "Empty catch swallows write failure", "tier": "A",
                         "status": "accepted", "first_seen": TODAY, "last_seen": TODAY,
                         "reason": "tracked", "until": "2027-01-01"}
        assert load_baseline(path) == doc

    def test_first_seen_survives_a_second_record(self, tmp_path: Path) -> None:
        from baseline import record

        path = tmp_path / ".tech-debt" / "baseline.json"
        record(path, decisions=[_decision()], findings=[_finding()],
               today="2026-04-01", preset="balanced")
        doc = record(path, decisions=[_decision()], findings=[_finding()],
                     today=TODAY, preset="balanced")
        assert doc["findings"]["aaaaaaaaaaaaaaaa"]["first_seen"] == "2026-04-01"
        assert doc["findings"]["aaaaaaaaaaaaaaaa"]["last_seen"] == TODAY

    def test_promoted_records_without_a_bundle(self, tmp_path: Path) -> None:
        """`promoted` now means "selected for a design session"; there is no
        bundle to vouch for, so recording one must simply work."""
        from baseline import record

        path = tmp_path / ".tech-debt" / "baseline.json"
        doc = record(path, decisions=[_decision(status="promoted")], findings=[_finding()],
                     today=TODAY, preset="balanced")
        entry = doc["findings"]["aaaaaaaaaaaaaaaa"]
        assert entry["status"] == "promoted"
        assert "bundle" not in entry

    def test_a_legacy_entry_carrying_a_bundle_still_reads(self, tmp_path: Path) -> None:
        """A baseline written before this change carries `bundle` on every
        entry; it is ignored on read, never an error."""
        from baseline import load_baseline, record

        path = tmp_path / ".tech-debt" / "baseline.json"
        path.parent.mkdir(parents=True)
        legacy = _baseline(**{"aaaaaaaaaaaaaaaa": _entry(
            status="promoted", bundle="chore-empty-catch-2026-04-01")})
        path.write_text(json.dumps(legacy), encoding="utf-8")

        assert load_baseline(path) is not None
        doc = record(path, decisions=[_decision(status="promoted")], findings=[_finding()],
                     today=TODAY, preset="balanced")
        assert "bundle" not in doc["findings"]["aaaaaaaaaaaaaaaa"]

    def test_an_entry_absent_from_this_scan_is_kept(self, tmp_path: Path) -> None:
        """The baseline remembers decisions across scans; a finding the scan did
        not raise this time keeps its status."""
        from baseline import record

        path = tmp_path / ".tech-debt" / "baseline.json"
        record(path, decisions=[_decision(status="rejected", reason="by design")],
               findings=[_finding()], today="2026-04-01", preset="balanced")
        doc = record(path, decisions=[], findings=[], today=TODAY, preset="balanced")
        assert doc["findings"]["aaaaaaaaaaaaaaaa"]["status"] == "rejected"
        assert doc["findings"]["aaaaaaaaaaaaaaaa"]["last_seen"] == "2026-04-01"

    def test_an_unknown_status_raises(self, tmp_path: Path) -> None:
        from baseline import BaselineError, record

        with pytest.raises(BaselineError, match="status"):
            record(tmp_path / "b.json", decisions=[_decision(status="maybe")],
                   findings=[_finding()], today=TODAY, preset="balanced")

    def test_title_and_reason_are_redacted(self, tmp_path: Path) -> None:
        from baseline import record

        doc = record(tmp_path / "b.json",
                     decisions=[_decision(reason='see token = "sk_live_51H8f2kL9mN3pQ7rS4tU6vW"')],
                     findings=[_finding(title='key "sk_live_51H8f2kL9mN3pQ7rS4tU6vW" leaks')],
                     today=TODAY, preset="balanced")
        blob = json.dumps(doc)
        assert "sk_live_51H8f2kL9mN3pQ7rS4tU6vW" not in blob
        assert "sk_l***" in blob

    def test_the_write_is_atomic(self, tmp_path: Path, monkeypatch) -> None:
        """A crash mid-write must leave the previous baseline intact."""
        import baseline as mod

        path = tmp_path / "b.json"
        mod.record(path, decisions=[_decision()], findings=[_finding()],
                   today="2026-04-01", preset="balanced")
        before = path.read_bytes()

        def boom(*a, **k):
            raise OSError("disk full")

        monkeypatch.setattr(mod.os, "replace", boom)
        with pytest.raises(mod.BaselineError):
            mod.record(path, decisions=[_decision(status="rejected")], findings=[_finding()],
                       today=TODAY, preset="balanced")
        assert path.read_bytes() == before

    def test_missing_fingerprint_raises_naming_the_decision(self, tmp_path: Path) -> None:
        from baseline import BaselineError, record

        decision = _decision(title="Untracked finding with no fingerprint")
        del decision["fingerprint"]
        with pytest.raises(BaselineError, match="Untracked finding with no fingerprint"):
            record(tmp_path / "b.json", decisions=[decision], findings=[_finding()],
                   today=TODAY, preset="balanced")

    def test_two_fingerprintless_decisions_do_not_collide(self, tmp_path: Path) -> None:
        """Without a guard, both decisions key onto the empty string and the
        second silently overwrites the first -- reproduced before this fix."""
        from baseline import BaselineError, record

        first = _decision(title="First finding, no fingerprint")
        del first["fingerprint"]
        second = _decision(title="Second finding, no fingerprint")
        del second["fingerprint"]
        with pytest.raises(BaselineError):
            record(tmp_path / "b.json", decisions=[first, second], findings=[_finding()],
                   today=TODAY, preset="balanced")

    def test_empty_string_fingerprint_raises(self, tmp_path: Path) -> None:
        """A hand-typed `fingerprint: ""` parses to an empty string, not a
        missing key -- also rejected."""
        from baseline import BaselineError, record

        with pytest.raises(BaselineError, match="fingerprint"):
            record(tmp_path / "b.json", decisions=[_decision(fingerprint="")],
                   findings=[_finding()], today=TODAY, preset="balanced")

    def test_an_undecided_finding_is_recorded_as_pending(self, tmp_path: Path) -> None:
        """Ruling 25: `record` remembers every finding it was shown, not only the
        ones the design document carried a decision for -- otherwise a
        suppressed-from-the-document, still-undecided finding classifies NEW on
        every re-scan forever."""
        from baseline import record

        undecided = _finding(
            fingerprint="bbbbbbbbbbbbbbbb", family="dead-code",
            title="Unreachable branch after early return", tier="C", quote_hash="r" * 40,
            evidence=[{"file": "src/pay/gateway.py", "line_start": 91, "line_end": 91,
                       "quote": "if False:", "quote_verified": True}],
        )
        doc = record(tmp_path / "b.json", decisions=[_decision()],
                     findings=[_finding(), undecided], today=TODAY, preset="balanced")
        assert set(doc["findings"]) == {"aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"}
        entry = doc["findings"]["bbbbbbbbbbbbbbbb"]
        assert entry == {"family": "dead-code", "file": "src/pay/gateway.py", "line_start": 91,
                         "quote_hash": "r" * 40, "quote": "if False:",
                         "title": "Unreachable branch after early return", "tier": "C",
                         "status": "pending", "first_seen": TODAY, "last_seen": TODAY,
                         "reason": None, "until": None}

    def test_a_rejected_entry_survives_when_undecided_this_scan(self, tmp_path: Path) -> None:
        """A finding still present in `findings` but with no decision this time
        (it is suppressed and so absent from the design document) keeps its
        recorded status, reason and first_seen; only last_seen refreshes."""
        from baseline import record

        path = tmp_path / "b.json"
        record(path, decisions=[_decision(status="rejected", reason="flaky, tracked elsewhere")],
               findings=[_finding()], today="2026-04-01", preset="balanced")
        doc = record(path, decisions=[], findings=[_finding()], today=TODAY,
                     preset="balanced")
        entry = doc["findings"]["aaaaaaaaaaaaaaaa"]
        assert entry["status"] == "rejected"
        assert entry["reason"] == "flaky, tracked elsewhere"
        assert entry["first_seen"] == "2026-04-01"
        assert entry["last_seen"] == TODAY

    def test_a_fingerprintless_finding_is_skipped_but_a_fingerprintless_decision_raises(
        self, tmp_path: Path
    ) -> None:
        from baseline import BaselineError, record

        no_fp_finding = _finding()
        del no_fp_finding["fingerprint"]
        doc = record(tmp_path / "b.json", decisions=[], findings=[no_fp_finding],
                     today=TODAY, preset="balanced")
        assert doc["findings"] == {}

        no_fp_decision = _decision()
        del no_fp_decision["fingerprint"]
        with pytest.raises(BaselineError, match="fingerprint"):
            record(tmp_path / "c.json", decisions=[no_fp_decision], findings=[_finding()],
                   today=TODAY, preset="balanced")

    def test_round_trip_with_diff_leaves_nothing_new(self, tmp_path: Path) -> None:
        """record then diff over the same findings: every finding -- decided or
        not -- is UNCHANGED, and diff's `new` count is zero."""
        from baseline import diff, record

        undecided = _finding(fingerprint="bbbbbbbbbbbbbbbb", family="dead-code",
                              title="Unreachable branch after early return", tier="C")
        path = tmp_path / "b.json"
        doc = record(path, decisions=[_decision()], findings=[_finding(), undecided],
                     today=TODAY, preset="balanced")
        out = diff({"findings": [_finding(), undecided]}, doc, tmp_path, TODAY)
        assert out["counts"]["new"] == 0
        assert all(v["diff"] == "UNCHANGED" for v in out["status"].values())

    # -- Ruling 26: an entry follows its finding across an edit ---------------

    def test_a_rejection_follows_its_finding_across_an_edit(self, tmp_path: Path) -> None:
        """Ruling 26: the code was edited, so the finding's fingerprint changed.
        The entry carrying the human's rejection migrates to the new
        fingerprint rather than being orphaned beside a fresh `pending` one --
        which the next `diff` would find by direct lookup, losing the
        rejection, while the old entry no finding matches reports a spurious
        RESOLVED."""
        from baseline import diff, record

        path = tmp_path / "b.json"
        path.write_text(json.dumps(_baseline(**{
            "1" * 16: _entry(status="rejected", reason="flaky, tracked elsewhere",
                             line_start=10, quote="except Exception:",
                             first_seen="2026-01-05", last_seen="2026-01-05"),
        })), encoding="utf-8")
        edited = _finding(
            fingerprint="2" * 16,
            evidence=[{"file": "src/pay/refund.py", "line_start": 20, "line_end": 20,
                       "quote": "except Exception:  # keep going", "quote_verified": True}],
        )

        doc = record(path, decisions=[], findings=[edited], today=TODAY,
                     preset="balanced")
        assert "1" * 16 not in doc["findings"], "the old key is removed, not left behind"
        entry = doc["findings"]["2" * 16]
        assert entry["status"] == "rejected"
        assert entry["reason"] == "flaky, tracked elsewhere"
        assert entry["first_seen"] == "2026-01-05"
        assert entry["last_seen"] == TODAY
        assert entry["line_start"] == 20

        out = diff({"findings": [edited]}, doc, tmp_path, TODAY)
        assert out["suppressed"] == [
            {"fingerprint": "2" * 16, "status": "rejected", "reason": "flaky, tracked elsewhere"}
        ]
        assert out["counts"]["resolved"] == 0

    def test_a_re_seen_entry_has_its_finding_fields_refreshed(self, tmp_path: Path) -> None:
        """I2: the decision is preserved, but where the code is and what it is
        called are re-read from this scan. A frozen `line_start` would leave
        the 40-line edited window measuring from wherever the finding was
        first seen, however far the code has since moved."""
        from baseline import record

        path = tmp_path / "b.json"
        path.write_text(json.dumps(_baseline(**{
            "aaaaaaaaaaaaaaaa": _entry(status="rejected", reason="by design", line_start=33,
                                       title="old", first_seen="2026-01-05",
                                       last_seen="2026-01-05"),
        })), encoding="utf-8")
        moved = _finding(
            title="new",
            evidence=[{"file": "src/pay/refund.py", "line_start": 500, "line_end": 500,
                       "quote": "except Exception:", "quote_verified": True}],
        )

        doc = record(path, decisions=[], findings=[moved], today=TODAY,
                     preset="balanced")
        entry = doc["findings"]["aaaaaaaaaaaaaaaa"]
        assert entry["line_start"] == 500
        assert entry["title"] == "new"
        assert entry["status"] == "rejected"
        assert entry["reason"] == "by design"
        assert entry["first_seen"] == "2026-01-05"
        assert entry["last_seen"] == TODAY

    def test_a_direct_match_is_never_taken_by_a_neighbour(self, tmp_path: Path) -> None:
        """The migration searches the whole baseline but keeps its result only
        when no current finding owns it, so the entry `fpA` matches directly
        cannot be migrated onto `fpB`, its same-titled neighbour fifteen lines
        away (ruling 29). `fpB` is new here and must be recorded as such."""
        from baseline import record

        path = tmp_path / "b.json"
        path.write_text(json.dumps(_baseline(**{
            "aaaaaaaaaaaaaaaa": _entry(status="rejected", reason="by design", line_start=10,
                                       first_seen="2026-01-05", last_seen="2026-01-05"),
        })), encoding="utf-8")
        owner = _finding(
            evidence=[{"file": "src/pay/refund.py", "line_start": 10, "line_end": 10,
                       "quote": "except Exception:", "quote_verified": True}],
        )
        neighbour = _finding(
            fingerprint="bbbbbbbbbbbbbbbb",
            evidence=[{"file": "src/pay/refund.py", "line_start": 15, "line_end": 15,
                       "quote": "except ValueError:", "quote_verified": True}],
        )

        doc = record(path, decisions=[_decision(status="pending")],
                     findings=[owner, neighbour], today=TODAY, preset="balanced")
        assert set(doc["findings"]) == {"aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"}
        assert doc["findings"]["aaaaaaaaaaaaaaaa"]["status"] == "pending"
        assert doc["findings"]["aaaaaaaaaaaaaaaa"]["first_seen"] == "2026-01-05"
        assert doc["findings"]["bbbbbbbbbbbbbbbb"]["status"] == "pending"
        assert doc["findings"]["bbbbbbbbbbbbbbbb"]["first_seen"] == TODAY, "fresh, not migrated"

    def test_a_decided_finding_migrates_and_keeps_its_decision(self, tmp_path: Path) -> None:
        """The decisions loop resolves its entry the same way: a re-promote of a
        finding whose code was edited since keeps the decision the baseline
        already recorded for it."""
        from baseline import record

        path = tmp_path / "b.json"
        path.write_text(json.dumps(_baseline(**{
            "1" * 16: _entry(status="promoted",
                             line_start=10, first_seen="2026-01-05", last_seen="2026-01-05"),
        })), encoding="utf-8")
        edited = _finding(
            fingerprint="2" * 16,
            evidence=[{"file": "src/pay/refund.py", "line_start": 20, "line_end": 20,
                       "quote": "except Exception:  # keep going", "quote_verified": True}],
        )

        doc = record(path, decisions=[_decision(fingerprint="2" * 16, status="promoted")],
                     findings=[edited], today=TODAY, preset="balanced")
        assert "1" * 16 not in doc["findings"]
        entry = doc["findings"]["2" * 16]
        assert entry["status"] == "promoted"
        assert entry["first_seen"] == "2026-01-05"

    def test_record_matches_an_edited_finding_the_way_diff_does(self, tmp_path: Path) -> None:
        """Ruling 29's reproduction: `fp1` is a direct match (owned by the
        current finding of that same fingerprint) at line 10, `fp2` is
        `rejected` at line 12 with no current finding of its own, and `fp3`
        -- a new fingerprint at line 11 sharing `fp1` and `fp2`'s title -- is
        the nearer-or-tied edited-match candidate for both. `_entry_for` must
        run the heuristic over the whole baseline exactly as `classify`
        does, and only check ownership of the *result*: since that result is
        `fp1`, already owned, `fp3` gets a fresh `pending` entry rather than
        stealing `fp2`'s rejection -- otherwise `record` would migrate an
        entry `diff` never considered available, and the next scan would
        silently suppress `fp3` with a rejection the user never gave it."""
        from baseline import diff, record

        root = _repo(tmp_path, {"src/a.py": "x\n" * 9 + "except Exception:\n" + "x\n" * 40})
        path = tmp_path / "b.json"
        path.write_text(json.dumps(_baseline(**{
            "aaaaaaaaaaaaaaaa": _entry(file="src/a.py", line_start=10,
                                       quote="except Exception:",
                                       first_seen="2026-03-01", last_seen="2026-03-01"),
            "bbbbbbbbbbbbbbbb": _entry(file="src/a.py", line_start=12, status="rejected",
                                       reason="wontfix", quote="absent",
                                       first_seen="2026-03-01", last_seen="2026-03-01"),
        })), encoding="utf-8")

        fp1 = _finding(
            evidence=[{"file": "src/a.py", "line_start": 10, "line_end": 10,
                       "quote": "except Exception:", "quote_verified": True}],
        )
        fp3 = _finding(
            fingerprint="cccccccccccccccc", quote_hash="s" * 40,
            evidence=[{"file": "src/a.py", "line_start": 11, "line_end": 11,
                       "quote": "except Exception:", "quote_verified": True}],
        )

        doc = record(path, decisions=[], findings=[fp1, fp3], today=TODAY,
                     preset="balanced")

        assert doc["findings"]["cccccccccccccccc"]["status"] == "pending", \
            "fp3 must not come back rejected -- fp1's entry is owned, not a free candidate"
        assert doc["findings"]["cccccccccccccccc"]["first_seen"] == TODAY
        assert doc["findings"]["cccccccccccccccc"]["reason"] is None
        assert doc["findings"]["bbbbbbbbbbbbbbbb"]["status"] == "rejected"
        assert doc["findings"]["bbbbbbbbbbbbbbbb"]["last_seen"] == "2026-03-01", \
            "fp2 must be untouched -- it was never fp3's match"
        assert doc["findings"]["aaaaaaaaaaaaaaaa"]["status"] == "pending"

        verified = {"schema_version": 2, "findings": [fp1, fp3]}
        out = diff(verified, doc, root, TODAY)
        assert out["suppressed"] == []
        assert "cccccccccccccccc" not in {s["fingerprint"] for s in out["suppressed"]}


class TestTriple:
    """Direct, git-free checks on the derived lines themselves."""

    def test_default_path_matches_TRIPLE_byte_for_byte(self) -> None:
        from baseline import TRIPLE, _triple

        assert _triple(".tech-debt/baseline.json") == TRIPLE

    def test_escapes_a_character_class_metacharacter(self) -> None:
        from baseline import _triple

        assert _triple("[weird]/baseline.json") == (
            "!\\[weird\\]/", "\\[weird\\]/*", "!\\[weird\\]/baseline.json",
        )

    def test_escapes_a_leading_hash(self) -> None:
        from baseline import _triple

        assert _triple("#hash/baseline.json") == (
            "!\\#hash/", "\\#hash/*", "!\\#hash/baseline.json",
        )


class TestGitignoreTriple:
    @pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
    def test_appends_the_triple_once_and_the_baseline_becomes_tracked(self, tmp_path: Path) -> None:
        from baseline import ensure_gitignore_triple

        root = _git_repo(tmp_path)
        baseline = root / ".tech-debt" / "baseline.json"
        baseline.parent.mkdir()
        baseline.write_text("{}", encoding="utf-8")
        ignored = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "-q", ".tech-debt/baseline.json"]
        )
        assert ignored.returncode == 0, "precondition: the baseline starts ignored"

        assert ensure_gitignore_triple(root, baseline) == "appended"
        text = (root / ".gitignore").read_text(encoding="utf-8")
        assert text.endswith("!.tech-debt/\n.tech-debt/*\n!.tech-debt/baseline.json\n")
        tracked = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "-q", ".tech-debt/baseline.json"]
        )
        assert tracked.returncode == 1, "the baseline is no longer ignored"
        other = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "-q", ".tech-debt/ranked.json"]
        )
        assert other.returncode == 0, "every other workdir file stays ignored"

        assert ensure_gitignore_triple(root, baseline) == "present"
        assert (root / ".gitignore").read_text(encoding="utf-8") == text

    @pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
    def test_derives_the_triple_for_a_baseline_outside_tech_debt(self, tmp_path: Path) -> None:
        """The hardcoded `.tech-debt/` triple would append lines that never match a
        baseline configured elsewhere, leaving it ignored while reporting
        "appended" -- reproduced before this fix. The derived triple must track
        the real directory and file name instead."""
        from baseline import ensure_gitignore_triple

        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        (tmp_path / ".gitignore").write_text("custom_baseline_dir/\n", encoding="utf-8")
        baseline = tmp_path / "custom_baseline_dir" / "state.json"
        baseline.parent.mkdir()
        baseline.write_text("{}", encoding="utf-8")
        ignored = subprocess.run(
            ["git", "-C", str(tmp_path), "check-ignore", "-q", "custom_baseline_dir/state.json"]
        )
        assert ignored.returncode == 0, "precondition: the baseline starts ignored"

        assert ensure_gitignore_triple(tmp_path, baseline) == "appended"
        text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        assert text.endswith(
            "!custom_baseline_dir/\ncustom_baseline_dir/*\n!custom_baseline_dir/state.json\n"
        )
        tracked = subprocess.run(
            ["git", "-C", str(tmp_path), "check-ignore", "-q", "custom_baseline_dir/state.json"]
        )
        assert tracked.returncode == 1, "the baseline is no longer ignored"

        assert ensure_gitignore_triple(tmp_path, baseline) == "present"
        assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == text

    @pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
    def test_an_ancestor_wholly_ignored_directory_reports_still_ignored(
        self, tmp_path: Path
    ) -> None:
        """`build/` is wholly ignored, so `!build/scan/` cannot re-include a path
        under it -- git prunes the ignored ancestor before it ever looks at the
        child rule. The triple is still the right pattern for `build/scan/` and
        is still appended, but the baseline stays ignored, and
        `ensure_gitignore_triple` must say so rather than claim "appended"."""
        from baseline import ensure_gitignore_triple

        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        (tmp_path / ".gitignore").write_text("build/\n", encoding="utf-8")
        baseline = tmp_path / "build" / "scan" / "baseline.json"
        baseline.parent.mkdir(parents=True)
        baseline.write_text("{}", encoding="utf-8")
        ignored = subprocess.run(
            ["git", "-C", str(tmp_path), "check-ignore", "-q", "build/scan/baseline.json"]
        )
        assert ignored.returncode == 0, "precondition: the baseline starts ignored"

        assert ensure_gitignore_triple(tmp_path, baseline) == "still-ignored"
        text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        assert text.endswith("!build/scan/\nbuild/scan/*\n!build/scan/baseline.json\n"), (
            "the lines are correct and harmless, so they stay appended"
        )
        still = subprocess.run(
            ["git", "-C", str(tmp_path), "check-ignore", "-q", "build/scan/baseline.json"]
        )
        assert still.returncode == 0, "the baseline is still ignored -- the ancestor wins"

    @pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
    def test_a_character_class_metacharacter_directory_name_is_escaped(
        self, tmp_path: Path
    ) -> None:
        """An unescaped `[weird]` is a gitignore character class, not the literal
        directory name -- the derived lines must escape it to actually match."""
        from baseline import ensure_gitignore_triple

        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        (tmp_path / ".gitignore").write_text("\\[weird]/\n", encoding="utf-8")
        baseline = tmp_path / "[weird]" / "baseline.json"
        baseline.parent.mkdir()
        baseline.write_text("{}", encoding="utf-8")
        ignored = subprocess.run(
            ["git", "-C", str(tmp_path), "check-ignore", "-q", "[weird]/baseline.json"]
        )
        assert ignored.returncode == 0, "precondition: the baseline starts ignored"

        assert ensure_gitignore_triple(tmp_path, baseline) == "appended"
        text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        assert text.endswith("!\\[weird\\]/\n\\[weird\\]/*\n!\\[weird\\]/baseline.json\n")
        tracked = subprocess.run(
            ["git", "-C", str(tmp_path), "check-ignore", "-q", "[weird]/baseline.json"]
        )
        assert tracked.returncode == 1, "the baseline is no longer ignored"

    @pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
    def test_a_leading_hash_directory_name_is_escaped_and_the_sibling_stays_ignored(
        self, tmp_path: Path
    ) -> None:
        """An unescaped `#hash/*` line is a gitignore comment, so it silently
        fails to re-ignore the rest of the directory -- a sibling file leaks out
        untracked. Escaping the leading `#` fixes both the baseline and the
        sibling."""
        from baseline import ensure_gitignore_triple

        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        (tmp_path / ".gitignore").write_text("\\#hash/\n", encoding="utf-8")
        baseline_dir = tmp_path / "#hash"
        baseline_dir.mkdir()
        baseline = baseline_dir / "baseline.json"
        baseline.write_text("{}", encoding="utf-8")
        (baseline_dir / "other.json").write_text("{}", encoding="utf-8")
        ignored = subprocess.run(
            ["git", "-C", str(tmp_path), "check-ignore", "-q", "#hash/baseline.json"]
        )
        assert ignored.returncode == 0, "precondition: the baseline starts ignored"

        assert ensure_gitignore_triple(tmp_path, baseline) == "appended"
        text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        assert text.endswith("!\\#hash/\n\\#hash/*\n!\\#hash/baseline.json\n")
        tracked = subprocess.run(
            ["git", "-C", str(tmp_path), "check-ignore", "-q", "#hash/baseline.json"]
        )
        assert tracked.returncode == 1, "the baseline is no longer ignored"
        other = subprocess.run(
            ["git", "-C", str(tmp_path), "check-ignore", "-q", "#hash/other.json"]
        )
        assert other.returncode == 0, "the sibling file stays ignored"

    @pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
    def test_an_untracked_baseline_needs_no_triple(self, tmp_path: Path) -> None:
        """A repository whose .gitignore never mentions the workdir at all has
        nothing to fix -- the baseline was never ignored in the first place."""
        from baseline import ensure_gitignore_triple

        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        baseline = tmp_path / ".tech-debt" / "baseline.json"
        baseline.parent.mkdir()
        baseline.write_text("{}", encoding="utf-8")
        # Not ignored to begin with, so nothing to do.
        assert ensure_gitignore_triple(tmp_path, baseline) == "present"

    @pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
    def test_creates_gitignore_when_absent(self, tmp_path: Path) -> None:
        """The baseline is ignored via .git/info/exclude, not .gitignore, so
        .gitignore does not exist yet -- this is what exercises 4.10's
        "creating it if absent"."""
        from baseline import ensure_gitignore_triple

        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        exclude = tmp_path / ".git" / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        exclude.write_text(".tech-debt/\n", encoding="utf-8")
        baseline = tmp_path / ".tech-debt" / "baseline.json"
        baseline.parent.mkdir()
        baseline.write_text("{}", encoding="utf-8")
        ignored = subprocess.run(
            ["git", "-C", str(tmp_path), "check-ignore", "-q", ".tech-debt/baseline.json"]
        )
        assert ignored.returncode == 0, "precondition: the baseline starts ignored"
        assert not (tmp_path / ".gitignore").is_file(), "precondition: no .gitignore yet"

        assert ensure_gitignore_triple(tmp_path, baseline) == "appended"
        assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == (
            "# tech-debt-scan: track the baseline, ignore the rest of the workdir\n"
            "!.tech-debt/\n"
            ".tech-debt/*\n"
            "!.tech-debt/baseline.json\n"
        )
        tracked = subprocess.run(
            ["git", "-C", str(tmp_path), "check-ignore", "-q", ".tech-debt/baseline.json"]
        )
        assert tracked.returncode == 1, "the baseline is now tracked, not ignored"

    def test_without_git_reports_no_git(self, tmp_path: Path, monkeypatch) -> None:
        import baseline as mod

        monkeypatch.setattr(mod.shutil, "which", lambda name: None)
        assert mod.ensure_gitignore_triple(tmp_path, tmp_path / "b.json") == "no-git"


class TestRunRecordCLI:
    """`_run_record` end to end: argparse, config load, the `verified.json` read
    and the exit codes -- none of it was exercised by anything above, which is
    how the `config["preset"]` bug (fixed to `config["ranking"]["preset"]`)
    reached the report only because it was hand-tested."""

    def test_happy_path_writes_the_baseline_and_exits_zero(self, tmp_path: Path) -> None:
        from baseline import _main, load_baseline

        root = tmp_path
        workdir = root / ".tech-debt"
        workdir.mkdir()
        shutil.copy(GOLDEN_VERIFIED, workdir / "verified.json")
        design = root / "design.md"
        design.write_text(
            GOLDEN_DESIGN.read_text(encoding="utf-8").replace(
                "status: pending", "status: approved", 1
            ),
            encoding="utf-8",
        )
        # A non-default preset proves _run_record reads config["ranking"]["preset"],
        # not the "balanced" default that would mask a regression of that bug.
        (root / ".tech-debt.yaml").write_text("ranking:\n  preset: quick-wins\n",
                                               encoding="utf-8")

        exit_code = _main([
            "record", "--workdir", str(workdir), "--design", str(design),
            "--root", str(root), "--today", CLI_TODAY,
        ])
        assert exit_code == 0

        doc = load_baseline(root / ".tech-debt" / "baseline.json")
        assert doc is not None
        assert doc["preset"] == "quick-wins"
        assert doc["last_scan"] == CLI_TODAY
        approved = [e for e in doc["findings"].values() if e["status"] == "approved"]
        assert len(approved) == 1
        assert approved[0]["file"] is not None, "matched against a real verified.json entry"

    def test_missing_verified_json_exits_2_with_a_message(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from baseline import _main

        root = tmp_path
        workdir = root / ".tech-debt"
        workdir.mkdir()  # no verified.json written
        design = root / "design.md"
        design.write_text(GOLDEN_DESIGN.read_text(encoding="utf-8"), encoding="utf-8")

        exit_code = _main([
            "record", "--workdir", str(workdir), "--design", str(design), "--root", str(root),
        ])
        assert exit_code == 2
        assert "verified.json" in capsys.readouterr().err

    @pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
    def test_ancestor_ignored_baseline_reports_still_ignored_with_guidance(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """When ensure_gitignore_triple can't win against a wholly ignored
        ancestor, _run_record must say so instead of the usual "appended"."""
        from baseline import _main

        root = tmp_path
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        (root / ".gitignore").write_text("build/\n", encoding="utf-8")
        workdir = root / ".tech-debt"
        workdir.mkdir()
        shutil.copy(GOLDEN_VERIFIED, workdir / "verified.json")
        design = root / "design.md"
        design.write_text(
            GOLDEN_DESIGN.read_text(encoding="utf-8").replace(
                "status: pending", "status: approved", 1
            ),
            encoding="utf-8",
        )
        baseline = root / "build" / "scan" / "baseline.json"

        exit_code = _main([
            "record", "--workdir", str(workdir), "--design", str(design),
            "--root", str(root), "--baseline", str(baseline), "--today", CLI_TODAY,
        ])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "still" in out and "ignored" in out
        assert "un-ignore" in out or "by hand" in out

    def test_malformed_config_exits_2_not_a_traceback(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Item 4: yaml.YAMLError from a malformed .tech-debt.yaml must hit the
        "error: ..." / exit 2 convention, not escape as an uncaught traceback."""
        from baseline import _main

        root = tmp_path
        workdir = root / ".tech-debt"
        workdir.mkdir()
        (workdir / "verified.json").write_text(
            json.dumps({"schema_version": 2, "findings": []}), encoding="utf-8"
        )
        design = root / "design.md"
        design.write_text(
            "## T\n\n```yaml\nstatus: pending\nslug: t\nseverity: 1\ncategory: security\n"
            "fingerprint: bbbbbbbbbbbbbbbb\n```\n",
            encoding="utf-8",
        )
        (root / ".tech-debt.yaml").write_text("families: [oops\n", encoding="utf-8")

        exit_code = _main([
            "record", "--workdir", str(workdir), "--design", str(design), "--root", str(root),
        ])
        assert exit_code == 2
        assert capsys.readouterr().err.startswith("error:")


def _diff_cli_case(tmp_path: Path, *, inventory_root: Path | None) -> tuple[Path, Path, Path]:
    """A repository, a workdir and a baseline for the `--root` CLI cases.

    The repository holds the one file the baseline's single `rejected` entry
    names, with that entry's quote still in it; `verified.json` is empty, so
    no current finding matches the entry and `diff` must decide whether its
    debt is gone by looking on disk. Against the right root the quote is
    found and the entry stays open; against any other directory the file is
    absent and the entry resolves. ``inventory_root`` writes the workdir's
    ``inventory.json`` with that ``root`` (``None`` writes no inventory at all).
    """
    repo = _repo(tmp_path / "repo", {
        "src/pay/refund.py": "def refund():\n    try:\n        post()\n    except Exception:\n"
                             "        pass\n",
    })
    workdir = tmp_path / "wd"
    workdir.mkdir()
    (workdir / "verified.json").write_text(json.dumps({"schema_version": 2, "findings": []}),
                                           encoding="utf-8")
    if inventory_root is not None:
        (workdir / "inventory.json").write_text(json.dumps({"root": str(inventory_root)}),
                                                encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps(_baseline(**{
        "aaaaaaaaaaaaaaaa": _entry(line_start=4, quote="except Exception:", status="rejected",
                                   reason="by design"),
    })), encoding="utf-8")
    return repo, workdir, baseline


class TestRunDiffCLI:
    """`_run_diff` end to end, and above all its `--root` default (C1).

    SKILL.md runs every chain command from the skill's own directory, which
    is not the scanned repository, so a `--root` that defaults to the process
    working directory resolved every baseline entry's `file` against the
    wrong tree and reported it RESOLVED with the note `file absent` -- a
    scan-wide false "the debt is gone". The default is the `root` the
    workdir's own `inventory.json` recorded instead.
    """

    def test_the_root_defaults_to_the_inventory_s_scanned_repository(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from baseline import _main

        repo, workdir, baseline = _diff_cli_case(tmp_path, inventory_root=tmp_path / "repo")
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)

        assert _main(["diff", "--workdir", str(workdir), "--baseline", str(baseline),
                      "--today", CLI_TODAY]) == 0
        doc = json.loads((workdir / "diff.json").read_bytes())
        assert doc["counts"]["resolved"] == 0
        assert doc["status"] == {}

    def test_without_an_inventory_the_root_falls_back_to_the_working_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from baseline import _main

        repo, workdir, baseline = _diff_cli_case(tmp_path, inventory_root=None)
        monkeypatch.chdir(repo)

        assert _main(["diff", "--workdir", str(workdir), "--baseline", str(baseline),
                      "--today", CLI_TODAY]) == 0
        doc = json.loads((workdir / "diff.json").read_bytes())
        assert doc["counts"]["resolved"] == 0
        assert doc["status"] == {}

    def test_an_explicit_root_beats_the_inventory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The flag is the answer whenever it is given: the inventory names the
        real repository here, and the explicit `--root` an empty directory, so
        only a `--root` that wins can report the entry's file absent."""
        from baseline import _main

        repo, workdir, baseline = _diff_cli_case(tmp_path, inventory_root=tmp_path / "repo")
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.chdir(repo)

        assert _main(["diff", "--workdir", str(workdir), "--root", str(empty),
                      "--baseline", str(baseline), "--today", CLI_TODAY]) == 0
        doc = json.loads((workdir / "diff.json").read_bytes())
        assert doc["counts"]["resolved"] == 1
        assert doc["status"]["aaaaaaaaaaaaaaaa"]["note"] == "file absent"
