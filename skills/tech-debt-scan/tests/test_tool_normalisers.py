"""Tests for the pure tool-output normalisers (spec 4.5)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "tool-output"
ROOT = Path("C:/repo")


class TestRelPath:
    def test_absolute_windows_path_under_root_is_relativised(self) -> None:
        from tool_normalisers import rel_path

        root = Path("C:/repo")
        raw = "C:\\repo\\src\\pay\\refund.py"
        assert rel_path(root, raw) == "src/pay/refund.py"

    def test_relative_path_is_forward_slashed(self) -> None:
        from tool_normalisers import rel_path

        assert rel_path(Path("C:/repo"), "src\\pay\\refund.py") == "src/pay/refund.py"

    def test_leading_dot_slash_is_stripped(self) -> None:
        from tool_normalisers import rel_path

        assert rel_path(Path("C:/repo"), "./src/a.py") == "src/a.py"

    def test_path_outside_root_is_rejected(self) -> None:
        from tool_normalisers import rel_path

        assert rel_path(Path("C:/repo"), "C:\\elsewhere\\a.py") is None

    def test_parent_traversal_is_rejected(self) -> None:
        from tool_normalisers import rel_path

        assert rel_path(Path("C:/repo"), "../outside.py") is None

    def test_empty_and_non_string_are_rejected(self) -> None:
        from tool_normalisers import rel_path

        assert rel_path(Path("C:/repo"), "   ") is None
        assert rel_path(Path("C:/repo"), None) is None  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "raw", ["src/a.py", "src\\a.py", "./src/a.py", "../outside.py", "  ", "/abs/a.py"]
    )
    def test_agrees_with_merge_findings_on_relative_inputs(self, raw: str) -> None:
        """The probe has its own relativiser; on inputs merge_findings accepts they agree.

        merge_findings._normalise_path rejects absolute paths outright because a
        scout must never cite one. The probe must accept an absolute path a tool
        emitted and turn it into a relative one, so the two differ deliberately on
        exactly that input class and nowhere else.
        """
        from merge_findings import _normalise_path
        from tool_normalisers import rel_path

        assert rel_path(Path("C:/repo"), raw) == _normalise_path(raw)


class TestNormaliseRuff:
    def _signals(self) -> list:
        from tool_normalisers import normalise_ruff

        payload = json.loads((FIXTURES / "ruff.json").read_text(encoding="utf-8"))
        return normalise_ruff(payload, ROOT)

    def test_absolute_backslashed_filename_becomes_relative(self) -> None:
        assert {s["file"] for s in self._signals()} == {
            "src/pay/refund.py", "src/pay/utils.py", "src/pay/ledger.py",
        }

    def test_blind_except_is_error_masking(self) -> None:
        blind = next(s for s in self._signals() if s["extra"]["code"] == "BLE001")
        assert blind["kind"] == "error-masking"
        assert blind["family"] == "error-masking"
        assert blind["line_start"] == 33
        assert blind["line_end"] == 33

    def test_complexity_rule_spans_its_whole_range(self) -> None:
        complex_unit = next(s for s in self._signals() if s["extra"]["code"] == "C901")
        assert complex_unit["kind"] == "complexity"
        assert (complex_unit["line_start"], complex_unit["line_end"]) == (41, 60)

    def test_unused_import_is_dead_code(self) -> None:
        unused = next(s for s in self._signals() if s["extra"]["code"] == "F401")
        assert (unused["kind"], unused["family"]) == ("unused", "dead-code")

    def test_every_ruff_signal_is_inference_class(self) -> None:
        assert all(s["fact"] is False for s in self._signals())

    def test_unmapped_rule_codes_are_dropped(self) -> None:
        from tool_normalisers import normalise_ruff

        payload = [{
            "code": "W291", "filename": "C:\\repo\\a.py",
            "location": {"row": 1, "column": 1}, "end_location": {"row": 1, "column": 2},
            "message": "trailing whitespace",
        }]
        assert normalise_ruff(payload, ROOT) == []

    def test_a_malformed_record_is_skipped_not_fatal(self) -> None:
        from tool_normalisers import normalise_ruff

        payload = [{"code": "E722"}, {"code": "E722", "filename": "C:\\repo\\a.py",
                                      "location": {"row": 2, "column": 1},
                                      "end_location": {"row": 2, "column": 3},
                                      "message": "Do not use bare `except`"}]
        assert len(normalise_ruff(payload, ROOT)) == 1


class TestNormaliseVulture:
    def _signals(self) -> list:
        from tool_normalisers import normalise_vulture

        lines = (FIXTURES / "vulture.txt").read_text(encoding="utf-8").splitlines()
        return normalise_vulture([line for line in lines if line.strip()], ROOT)

    def test_each_line_becomes_one_dead_code_signal(self) -> None:
        signals = self._signals()
        assert len(signals) == 5
        assert {s["family"] for s in signals} == {"dead-code"}
        assert {s["kind"] for s in signals} == {"unused"}

    def test_backslashed_path_and_line_are_parsed(self) -> None:
        first = self._signals()[0]
        assert first["file"] == "src/pay/legacy_export.py"
        assert first["line_start"] == 8 and first["line_end"] == 8

    def test_confidence_and_symbol_kind_are_carried_in_extra(self) -> None:
        first = self._signals()[0]
        assert first["extra"] == {"confidence": 60, "symbol_kind": "function",
                                  "symbol": "export_v1"}

    def test_high_confidence_attribute_is_kept(self) -> None:
        attribute = next(s for s in self._signals() if s["extra"]["symbol_kind"] == "attribute")
        assert attribute["extra"]["confidence"] == 100

    def test_a_line_that_does_not_match_the_grammar_is_dropped(self) -> None:
        from tool_normalisers import normalise_vulture

        assert normalise_vulture(["*** not a finding ***"], ROOT) == []

    def test_every_vulture_signal_is_inference_class(self) -> None:
        assert all(s["fact"] is False for s in self._signals())
