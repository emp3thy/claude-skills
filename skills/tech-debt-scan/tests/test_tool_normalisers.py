"""Tests for the pure tool-output normalisers (spec 4.5)."""
from __future__ import annotations

import csv
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

    def test_a_jscpd_pseudo_path_is_rejected(self) -> None:
        """jscpd names a code block embedded in a document
        ``<path>.md:<format>``. Those passed the old first-segment-only colon
        check and became the ``file`` of 57% of the signals from a scan of
        this repository -- a path no consumer can open."""
        from tool_normalisers import rel_path

        assert rel_path(Path("C:/repo"), "docs/plans/phase-4a.md:markdown") is None
        assert rel_path(Path("C:/repo"), "task-1-brief.md:bash") is None

    def test_a_legitimate_windows_absolute_path_still_survives(self) -> None:
        """Rejecting a colon in every segment must not cost the drive-letter
        case the relativiser exists for: an absolute path under root has its
        drive prefix removed before the colon rule is reached, so it is kept,
        while an absolute path outside root is still rejected."""
        from tool_normalisers import rel_path

        root = Path("C:/repo")
        assert rel_path(root, "C:\\repo\\src\\pay\\refund.py") == "src/pay/refund.py"
        assert rel_path(root, "C:\\repo\\src\\a b\\c-d.py") == "src/a b/c-d.py"
        assert rel_path(root, "D:\\other\\a.py") is None

    @pytest.mark.parametrize(
        "raw", ["src/a.py", "src\\a.py", "./src/a.py", "../outside.py", "  ", "/abs/a.py"]
    )
    def test_agrees_with_merge_findings_on_relative_inputs(self, raw: str) -> None:
        """The probe has its own relativiser; on inputs merge_findings accepts they agree.

        merge_findings._normalise_path rejects absolute paths outright because a
        scout must never cite one. The probe must accept an absolute path a tool
        emitted and turn it into a relative one, so the two differ deliberately on
        that input class -- and, since the whole-branch review, on one more:
        see the divergence test below.
        """
        from merge_findings import _normalise_path
        from tool_normalisers import rel_path

        assert rel_path(Path("C:/repo"), raw) == _normalise_path(raw)

    def test_the_colon_rule_is_stricter_than_merge_findings_deliberately(self) -> None:
        """Documents the second deliberate divergence rather than hiding it.

        ``merge_findings._normalise_path`` still carries the first-segment-only
        colon rule, so it accepts ``docs/x.md:markdown``. That is a scout-facing
        cleaner in phase 2 with its own goldens, and no scout emits a jscpd
        pseudo-path, so it is left alone here; the probe's rule is tightened
        because a real installed tool emits those paths in volume. If phase 5
        ever unifies the two, this test is the record of why they differ.
        """
        from merge_findings import _normalise_path
        from tool_normalisers import rel_path

        raw = "docs/x.md:markdown"
        assert _normalise_path(raw) == raw
        assert rel_path(Path("C:/repo"), raw) is None


class TestNormaliseRuff:
    def _signals(self) -> list:
        from tool_normalisers import normalise_ruff

        payload = json.loads((FIXTURES / "ruff.json").read_text(encoding="utf-8"))
        return normalise_ruff(payload, ROOT)

    def test_exact_signal_count_from_the_real_fixture(self) -> None:
        """A set-membership assertion alone would not catch a record being

        emitted twice; this pins the count against the fixture's four
        mapped records."""
        assert len(self._signals()) == 4

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
        assert len(signals) == 7
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

    def test_unreachable_code_after_return_is_kept_without_a_symbol(self) -> None:
        """vulture reports unreachable code with no 'unused <kind> <symbol>'

        shape at all -- see reachability.py -- so nothing is fabricated for
        the fields it never carried."""
        unreachable = next(
            s for s in self._signals() if s["message"] == "unreachable code after 'return'"
        )
        assert unreachable["file"] == "src/pay/orders.py"
        assert unreachable["line_start"] == 3 and unreachable["line_end"] == 3
        assert unreachable["family"] == "dead-code" and unreachable["kind"] == "unused"
        assert unreachable["extra"] == {"confidence": 100}

    def test_unreachable_else_block_is_kept_without_a_symbol(self) -> None:
        unreachable = next(
            s for s in self._signals() if s["message"] == "unreachable 'else' block"
        )
        assert unreachable["file"] == "src/pay/orders.py"
        assert unreachable["line_start"] == 10 and unreachable["line_end"] == 10
        assert unreachable["extra"] == {"confidence": 100}


class TestNormaliseLizard:
    def _signals(self) -> list:
        from tool_normalisers import normalise_lizard

        text = (FIXTURES / "lizard.csv").read_text(encoding="utf-8")
        rows = [row for row in csv.reader(text.splitlines()) if row]
        return normalise_lizard(rows, ROOT)

    def test_exact_signal_count_from_the_real_fixture(self) -> None:
        """A set-membership assertion alone would not catch a row being

        emitted twice; this pins the count against the fixture's three
        threshold-clearing rows."""
        assert len(self._signals()) == 3

    def test_only_units_over_the_threshold_are_reported(self) -> None:
        """lizard reports every function; a signal per function would swamp
        the lead cap, so only complex or long units become signals."""
        assert {s["extra"]["name"] for s in self._signals()} == {
            "issue_partial", "settle", "build_invoice_lines",
        }

    def test_a_long_low_complexity_unit_is_kept_via_the_nloc_leg(self) -> None:
        """issue_partial and settle both clear LIZARD_MIN_CCN; this row only

        clears LIZARD_MIN_NLOC, so it is the one proof that the NLOC leg of
        the CCN-or-NLOC threshold actually keeps a unit on its own."""
        from tool_normalisers import LIZARD_MIN_CCN, LIZARD_MIN_NLOC

        long_unit = next(
            s for s in self._signals() if s["extra"]["name"] == "build_invoice_lines"
        )
        assert long_unit["extra"]["ccn"] < LIZARD_MIN_CCN
        assert long_unit["extra"]["nloc"] >= LIZARD_MIN_NLOC
        assert long_unit["file"] == "src/pay/invoice.py"
        assert (long_unit["line_start"], long_unit["line_end"]) == (1, 68)

    def test_line_range_comes_from_the_last_two_columns(self) -> None:
        partial = next(s for s in self._signals() if s["extra"]["name"] == "issue_partial")
        assert (partial["line_start"], partial["line_end"]) == (41, 74)

    def test_ccn_and_nloc_are_carried_in_extra(self) -> None:
        partial = next(s for s in self._signals() if s["extra"]["name"] == "issue_partial")
        assert partial["extra"]["ccn"] == 13
        assert partial["extra"]["nloc"] == 34
        assert partial["extra"]["parameters"] == 4

    def test_backslashed_path_is_forward_slashed(self) -> None:
        settle = next(s for s in self._signals() if s["extra"]["name"] == "settle")
        assert settle["file"] == "src/pay/settlement.py"

    def test_kind_and_family_are_complexity(self) -> None:
        assert {(s["kind"], s["family"]) for s in self._signals()} == {
            ("complexity", "complex-units")
        }

    def test_a_short_row_is_skipped_not_fatal(self) -> None:
        from tool_normalisers import normalise_lizard

        assert normalise_lizard([["2", "1", "18"]], ROOT) == []

    def test_a_non_numeric_row_is_skipped_not_fatal(self) -> None:
        from tool_normalisers import normalise_lizard

        row = ["x", "y", "1", "2", "3", "c", "src/a.py", "f", "f()", "a", "b"]
        assert normalise_lizard([row], ROOT) == []

    def test_every_lizard_signal_is_inference_class(self) -> None:
        assert all(s["fact"] is False for s in self._signals())


class TestNormaliseMadge:
    def _signals(self) -> list:
        from tool_normalisers import normalise_madge

        payload = json.loads((FIXTURES / "madge.json").read_text(encoding="utf-8"))
        return normalise_madge(payload, ROOT)

    def test_one_cycle_becomes_one_signal(self) -> None:
        assert len(self._signals()) == 1

    def test_the_signal_names_the_first_file_of_the_cycle(self) -> None:
        assert self._signals()[0]["file"] == "src/cart/cart.ts"

    def test_the_whole_cycle_is_carried_in_extra(self) -> None:
        assert self._signals()[0]["extra"]["cycle"] == [
            "src/cart/cart.ts", "src/cart/pricing.ts", "src/cart/stock.ts",
        ]

    def test_kind_and_family_are_cycle_and_architecture(self) -> None:
        assert (self._signals()[0]["kind"], self._signals()[0]["family"]) == (
            "cycle", "architecture",
        )

    def test_a_cycle_has_no_line_range(self) -> None:
        """A cycle is a property of the import graph, not of any line."""
        assert self._signals()[0]["line_start"] is None
        assert self._signals()[0]["line_end"] is None

    def test_an_empty_graph_produces_nothing(self) -> None:
        from tool_normalisers import normalise_madge

        assert normalise_madge([], ROOT) == []

    def test_every_madge_signal_is_inference_class(self) -> None:
        assert all(s["fact"] is False for s in self._signals())


class TestNormaliseJscpd:
    def _signals(self) -> list:
        from tool_normalisers import normalise_jscpd

        payload = json.loads((FIXTURES / "jscpd.json").read_text(encoding="utf-8"))
        return normalise_jscpd(payload, ROOT)

    def test_one_duplicate_becomes_one_signal(self) -> None:
        assert len(self._signals()) == 1

    def test_the_signal_names_the_first_file_and_its_span(self) -> None:
        first = self._signals()[0]
        assert first["file"] == "src/util/format.ts"
        assert (first["line_start"], first["line_end"]) == (1, 8)

    def test_the_second_file_and_its_span_are_carried_in_extra(self) -> None:
        extra = self._signals()[0]["extra"]
        assert extra["other_file"] == "src/util/format-legacy.ts"
        assert extra["other_line_start"] == 5
        assert extra["other_line_end"] == 12
        assert extra["tokens"] == 79

    def test_the_duplicated_source_fragment_is_never_carried(self) -> None:
        """jscpd's `fragment` holds the duplicated source itself. It is dropped
        for the same reason gitleaks' Secret is: tool-signals.json is read into
        prompts (spec 4.5)."""
        blob = json.dumps(self._signals())
        assert "fragment" not in blob
        assert "export function compute" not in blob

    def test_the_nondeterministic_detection_date_is_never_carried(self) -> None:
        assert "detectionDate" not in json.dumps(self._signals())
        assert "2026-09-06T16:32" not in json.dumps(self._signals())

    def test_a_report_with_no_duplicates_produces_nothing(self) -> None:
        from tool_normalisers import normalise_jscpd

        assert normalise_jscpd({"duplicates": [], "statistics": {}}, ROOT) == []

    def test_malformed_line_values_are_dropped_not_propagated(self) -> None:
        """The Signal schema declares line_start/line_end as int | None. A
        malformed-but-JSON-parseable jscpd report must not push a non-int
        value through -- the same guarantee normalise_knip already gives its
        `line` field."""
        from tool_normalisers import normalise_jscpd

        payload = {
            "duplicates": [
                {
                    "firstFile": {"name": "src/a.ts", "start": "bogus", "end": [1, 2, 3]},
                    "secondFile": {"name": "src/b.ts", "start": 5, "end": "nope"},
                    "lines": 8,
                    "tokens": 10,
                }
            ],
            "statistics": {},
        }
        result = normalise_jscpd(payload, ROOT)
        assert len(result) == 1
        first = result[0]
        assert first["line_start"] is None
        assert first["line_end"] is None
        assert first["extra"]["other_line_start"] == 5
        assert first["extra"]["other_line_end"] is None


class TestNormaliseKnip:
    def _signals(self) -> list:
        from tool_normalisers import normalise_knip

        payload = json.loads((FIXTURES / "knip.json").read_text(encoding="utf-8"))
        return normalise_knip(payload, ROOT)

    def test_the_fixture_produces_exactly_three_signals(self) -> None:
        """The fixture has one files entry, one exports entry and one
        dependencies entry. A normaliser that double-emitted every entry
        would still satisfy every membership-style assertion in this class,
        so this is the one test that would actually catch it."""
        assert len(self._signals()) == 3

    def test_an_unused_file_becomes_a_whole_file_signal(self) -> None:
        unused_file = next(s for s in self._signals() if s["file"] == "vendor/tiny-emitter.js")
        assert unused_file["extra"]["issue"] == "files"
        assert unused_file["line_start"] is None

    def test_an_unused_export_carries_its_line_and_symbol(self) -> None:
        export = next(s for s in self._signals() if s["extra"].get("symbol") == "formatLegacy")
        assert export["file"] == "src/util/format-legacy.ts"
        assert export["line_start"] == 4 and export["line_end"] == 4

    def test_an_unused_dependency_is_dependency_debt(self) -> None:
        dependency = next(s for s in self._signals() if s["extra"].get("symbol") == "left-pad")
        assert dependency["family"] == "dependency-debt"
        assert dependency["kind"] == "unused"

    def test_unused_files_and_exports_are_dead_code(self) -> None:
        families = {s["family"] for s in self._signals()
                    if s["extra"].get("issue") in {"files", "exports"}}
        assert families == {"dead-code"}

    def test_empty_categories_produce_no_signals(self) -> None:
        from tool_normalisers import normalise_knip

        payload = {"issues": [{"file": "a.ts", "exports": [], "files": [], "types": [],
                               "dependencies": []}]}
        assert normalise_knip(payload, ROOT) == []

    def test_every_knip_signal_is_inference_class(self) -> None:
        assert all(s["fact"] is False for s in self._signals())


class TestNormaliseOsvScanner:
    def _signals(self) -> list:
        from tool_normalisers import normalise_osv_scanner

        payload = json.loads((FIXTURES / "osv-scanner.json").read_text(encoding="utf-8"))
        return normalise_osv_scanner(payload, ROOT)

    def test_one_vulnerability_becomes_one_signal(self) -> None:
        assert len(self._signals()) == 1

    def test_the_signal_names_the_lockfile_and_no_line(self) -> None:
        """osv-scanner's JSON carries no line numbers, so the evidence is the
        manifest path (spec 4.5)."""
        first = self._signals()[0]
        assert first["file"] == "package-lock.json"
        assert first["line_start"] is None and first["line_end"] is None

    def test_package_identity_and_advisory_are_carried_in_extra(self) -> None:
        extra = self._signals()[0]["extra"]
        assert extra["package"] == "left-pad"
        assert extra["version"] == "1.1.3"
        assert extra["ecosystem"] == "npm"
        assert extra["id"] == "GHSA-xxxx-yyyy-zzzz"

    def test_osv_signals_are_fact_class(self) -> None:
        """Fact-class is what lets 4b tier these without a verifier."""
        assert all(s["fact"] is True for s in self._signals())

    def test_kind_and_family_are_vuln_and_dependency_debt(self) -> None:
        first = self._signals()[0]
        assert (first["kind"], first["family"]) == ("vuln", "dependency-debt")

    def test_an_empty_result_set_produces_nothing(self) -> None:
        from tool_normalisers import normalise_osv_scanner

        assert normalise_osv_scanner({"results": []}, ROOT) == []

    def test_a_truthy_non_dict_source_or_package_does_not_raise(self) -> None:
        """``or {}`` lets a truthy non-dict through and then .get raises
        AttributeError -- which escaped _main's catch tuple entirely, so the
        process died with a traceback and no output file at all. This is one
        of the four normalisers whose real payload nobody has seen."""
        from tool_normalisers import normalise_osv_scanner

        assert normalise_osv_scanner({"results": [{"source": "package-lock.json"}]}, ROOT) == []
        payload = {
            "results": [{
                "source": {"path": "package-lock.json"},
                "packages": [{"package": "left-pad", "vulnerabilities": [{"id": "GHSA-1"}]}],
            }]
        }
        signals = normalise_osv_scanner(payload, ROOT)
        assert len(signals) == 1
        assert signals[0]["extra"]["package"] == ""

    def test_a_truthy_non_list_aliases_is_not_iterated_character_by_character(self) -> None:
        """A single id emitted as a bare string would otherwise become a list
        of one-character "aliases"."""
        from tool_normalisers import normalise_osv_scanner

        payload = {
            "results": [{
                "source": {"path": "package-lock.json"},
                "packages": [{
                    "package": {"name": "left-pad", "version": "1.1.3", "ecosystem": "npm"},
                    "vulnerabilities": [{"id": "GHSA-1", "aliases": "CVE-2024-0001"}],
                }],
            }]
        }
        assert normalise_osv_scanner(payload, ROOT)[0]["extra"]["aliases"] == []

    def test_a_docker_source_is_not_dropped_for_the_colon_in_its_path(self) -> None:
        """``rel_path`` rejects any colon-bearing segment, and an image reference like
        ``alpine:3.18`` has one -- so before the 4b fix, every advisory against a
        docker-sourced scan was silently dropped here. A docker or git source is not a
        path at all, so it is never sent through ``rel_path``: the signal carries a
        null ``file`` (4b's merge gives that the path-less repository-fact shape) and
        the raw source moves into ``extra``, rather than being lost."""
        from tool_normalisers import normalise_osv_scanner

        payload = {
            "results": [{
                "source": {"path": "alpine:3.18", "type": "docker"},
                "packages": [{
                    "package": {"name": "libssl", "version": "1.1.1", "ecosystem": "Alpine"},
                    "vulnerabilities": [{"id": "GHSA-docker-1"}],
                }],
            }]
        }
        signals = normalise_osv_scanner(payload, ROOT)
        assert len(signals) == 1
        assert signals[0]["file"] is None
        assert signals[0]["extra"]["source_type"] == "docker"
        assert signals[0]["extra"]["source_path"] == "alpine:3.18"

    def test_a_git_source_is_carried_the_same_way(self) -> None:
        from tool_normalisers import normalise_osv_scanner

        payload = {
            "results": [{
                "source": {"path": "https://github.com/example/vendored", "type": "git"},
                "packages": [{
                    "package": {"name": "left-pad", "version": "1.1.3", "ecosystem": "npm"},
                    "vulnerabilities": [{"id": "GHSA-git-1"}],
                }],
            }]
        }
        signals = normalise_osv_scanner(payload, ROOT)
        assert len(signals) == 1
        assert signals[0]["file"] is None
        assert signals[0]["extra"]["source_type"] == "git"
        assert signals[0]["extra"]["source_path"] == "https://github.com/example/vendored"

    def test_an_unrecognised_type_with_an_unresolvable_path_still_drops(self) -> None:
        """Only ``docker`` and ``git`` are known non-file sources. A colon-bearing path
        under any other (or missing) type is not known to be a legitimate non-file
        source, so it keeps the pre-fix behaviour: dropped, not invented a fact for."""
        from tool_normalisers import normalise_osv_scanner

        payload = {
            "results": [{
                "source": {"path": "docs/plans/phase-4a.md:markdown", "type": "sbom"},
                "packages": [{
                    "package": {"name": "left-pad", "version": "1.1.3", "ecosystem": "npm"},
                    "vulnerabilities": [{"id": "GHSA-sbom-1"}],
                }],
            }]
        }
        assert normalise_osv_scanner(payload, ROOT) == []

    def test_a_docker_source_still_needs_a_non_empty_path(self) -> None:
        """The package and vulnerability below are real: with ``packages: []`` the inner
        loop yielded nothing whatever the empty-path guard did, so the assertion held
        with the guard deleted and pinned nothing."""
        from tool_normalisers import normalise_osv_scanner

        packages = [{
            "package": {"name": "left-pad", "version": "1.1.3", "ecosystem": "npm"},
            "vulnerabilities": [{"id": "GHSA-empty-1"}],
        }]
        assert normalise_osv_scanner(
            {"results": [{"source": {"path": "alpine:3.18", "type": "docker"},
                          "packages": packages}]}, ROOT
        ), "the payload must otherwise produce a signal, or the guard is untested"
        assert normalise_osv_scanner(
            {"results": [{"source": {"path": "", "type": "docker"},
                          "packages": packages}]}, ROOT
        ) == []
        assert normalise_osv_scanner(
            {"results": [{"source": {"path": "   ", "type": "docker"},
                          "packages": packages}]}, ROOT
        ) == []

    def test_a_git_source_url_loses_its_userinfo_before_it_becomes_a_signal(self) -> None:
        """A checkout or submodule remote can carry ``user:password@``, which neither
        ``redaction`` pattern recognises -- no key name and operator for
        ``CREDENTIAL_RE``, no issuer prefix for ``SECRET_TOKEN_RE`` -- so it would reach
        tool-signals.json on disk, and 4b's candidate prose, verbatim."""
        from tool_normalisers import normalise_osv_scanner

        payload = {
            "results": [{
                "source": {"path": "https://ci:hunter2password@git.example.com/o/r.git",
                           "type": "git"},
                "packages": [{
                    "package": {"name": "left-pad", "version": "1.1.3", "ecosystem": "npm"},
                    "vulnerabilities": [{"id": "GHSA-git-2"}],
                }],
            }]
        }
        signals = normalise_osv_scanner(payload, ROOT)
        assert signals[0]["extra"]["source_path"] == "https://git.example.com/o/r.git"
        assert "hunter2password" not in json.dumps(signals)


class TestOsvSeverity:
    """Spec 4.5 + 4.9: an osv candidate is tier A, so no verifier ever revises its
    severity and ``rank.priority`` multiplies by it directly. A flat constant ranked a
    critical remote-code-execution advisory and a low-severity ReDoS alike."""

    def _one(self, vulnerability: dict, **package: object) -> dict:
        from tool_normalisers import normalise_osv_scanner

        payload = {
            "results": [{
                "source": {"path": "package-lock.json", "type": "lockfile"},
                "packages": [{
                    "package": {"name": "left-pad", "version": "1.1.3", "ecosystem": "npm"},
                    "vulnerabilities": [vulnerability],
                    **package,
                }],
            }]
        }
        signal: dict = normalise_osv_scanner(payload, ROOT)[0]
        return signal

    def test_a_database_specific_label_maps_onto_the_skills_scale(self) -> None:
        for label, expected in (("CRITICAL", 5), ("HIGH", 4), ("MODERATE", 3),
                                ("MEDIUM", 3), ("LOW", 2), ("critical", 5)):
            signal = self._one({"id": "GHSA-1", "database_specific": {"severity": label}})
            assert signal["extra"]["severity"] == expected, label

    def test_a_numeric_cvss_score_falls_into_its_own_qualitative_band(self) -> None:
        for score, expected in (("9.8", 5), (7.5, 4), ("5.3", 3), (2.1, 2), (0.0, 1)):
            signal = self._one({"id": "GHSA-1",
                                "severity": [{"type": "CVSS_V3", "score": score}]})
            assert signal["extra"]["severity"] == expected, score

    def test_a_cvss_vector_string_is_not_guessed_at(self) -> None:
        """Deriving a base score from a vector means implementing the CVSS formula. A
        record carrying a vector nearly always carries the label too, which is read
        first; with neither, the caller's own constant stands."""
        signal = self._one({"id": "GHSA-1", "severity": [
            {"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"},
        ]})
        assert "severity" not in signal["extra"]

    def test_the_label_wins_over_a_score_and_a_group_maximum(self) -> None:
        signal = self._one(
            {"id": "GHSA-1", "database_specific": {"severity": "LOW"},
             "severity": [{"type": "CVSS_V3", "score": "9.8"}]},
            groups=[{"ids": ["GHSA-1"], "max_severity": "9.8"}],
        )
        assert signal["extra"]["severity"] == 2

    def test_a_groups_max_severity_is_the_last_resort(self) -> None:
        signal = self._one({"id": "GHSA-1"},
                           groups=[{"ids": ["GHSA-1"], "max_severity": "7.5"}])
        assert signal["extra"]["severity"] == 4

    def test_a_group_maximum_is_matched_to_its_own_advisory(self) -> None:
        from tool_normalisers import normalise_osv_scanner

        payload = {
            "results": [{
                "source": {"path": "package-lock.json", "type": "lockfile"},
                "packages": [{
                    "package": {"name": "left-pad", "version": "1.1.3", "ecosystem": "npm"},
                    "vulnerabilities": [{"id": "GHSA-1"}, {"id": "GHSA-2"}],
                    "groups": [{"ids": ["GHSA-1"], "max_severity": "9.9"},
                               {"ids": ["GHSA-2"], "max_severity": "3.1"}],
                }],
            }]
        }
        by_id = {s["extra"]["id"]: s["extra"].get("severity")
                 for s in normalise_osv_scanner(payload, ROOT)}
        assert by_id == {"GHSA-1": 5, "GHSA-2": 2}

    def test_an_advisory_with_no_published_severity_carries_no_severity_key(self) -> None:
        """Absent rather than null: ``merge_findings`` then keeps its own constant, the
        flat value every advisory carried before, and the key's absence says the record
        published none more plainly than a null would."""
        assert "severity" not in self._one({"id": "GHSA-1"})["extra"]

    def test_junk_severity_data_does_not_raise_or_score(self) -> None:
        for vulnerability in (
            {"id": "GHSA-1", "database_specific": "HIGH"},
            {"id": "GHSA-1", "database_specific": {"severity": "URGENT"}},
            {"id": "GHSA-1", "severity": "9.8"},
            {"id": "GHSA-1", "severity": ["9.8"]},
            {"id": "GHSA-1", "severity": [{"type": "CVSS_V3", "score": 11.0}]},
            {"id": "GHSA-1", "severity": [{"type": "CVSS_V3", "score": -1}]},
        ):
            assert "severity" not in self._one(vulnerability)["extra"], vulnerability

    def test_the_captured_fixture_carries_its_published_severity(self) -> None:
        from tool_normalisers import normalise_osv_scanner

        payload = json.loads((FIXTURES / "osv-scanner.json").read_text(encoding="utf-8"))
        assert normalise_osv_scanner(payload, ROOT)[0]["extra"]["severity"] == 4


class TestNormaliseGitleaks:
    def _signals(self) -> list:
        from tool_normalisers import normalise_gitleaks

        payload = json.loads((FIXTURES / "gitleaks.json").read_text(encoding="utf-8"))
        return normalise_gitleaks(payload, ROOT)

    def test_one_finding_becomes_one_signal(self) -> None:
        assert len(self._signals()) == 1

    def test_the_signal_names_the_file_and_line(self) -> None:
        first = self._signals()[0]
        assert first["file"] == "src/config/settings.py"
        assert (first["line_start"], first["line_end"]) == (12, 12)

    def test_the_matched_secret_is_never_carried_in_any_field(self) -> None:
        """Dropped, not redacted: a redacted secret is still its own first four
        characters, and this file is read into prompts (spec 4.5)."""
        blob = json.dumps(self._signals())
        assert "EXAMPLE-NOT-A-REAL-SECRET-VALUE" not in blob
        assert "Secret" not in blob
        assert "Match" not in blob

    def test_rule_and_entropy_survive_because_the_verifier_needs_them(self) -> None:
        extra = self._signals()[0]["extra"]
        assert extra["rule"] == "generic-api-key"
        assert extra["entropy"] == 4.31

    def test_gitleaks_signals_are_fact_class(self) -> None:
        assert all(s["fact"] is True for s in self._signals())

    def test_gitleaks_keeps_the_start_column_in_extra(self) -> None:
        from tool_normalisers import normalise_gitleaks

        payload = [{"File": "a.py", "StartLine": 3, "EndLine": 3, "StartColumn": 17,
                    "RuleID": "generic-api-key", "Description": "d", "Secret": "S", "Match": "M"}]
        [sig] = normalise_gitleaks(payload, Path("."))
        assert sig["extra"]["column"] == 17
        assert "Secret" not in json.dumps(sig) and sig.get("message") != "M"

    def test_gitleaks_without_a_column_records_none(self) -> None:
        from tool_normalisers import normalise_gitleaks

        payload = [{"File": "a.py", "StartLine": 3, "RuleID": "r", "Description": "d"}]
        [sig] = normalise_gitleaks(payload, Path("."))
        assert sig["extra"]["column"] is None

    def test_a_record_without_a_usable_file_is_dropped(self) -> None:
        from tool_normalisers import normalise_gitleaks

        assert normalise_gitleaks([{"RuleID": "x", "StartLine": 1}], ROOT) == []


class TestNormaliseHadolint:
    def _signals(self) -> list:
        from tool_normalisers import normalise_hadolint

        payload = json.loads((FIXTURES / "hadolint.json").read_text(encoding="utf-8"))
        return normalise_hadolint(payload, ROOT)

    def test_each_record_becomes_one_dockerfile_signal(self) -> None:
        signals = self._signals()
        assert len(signals) == 2
        assert {s["kind"] for s in signals} == {"dockerfile"}
        assert {s["family"] for s in signals} == {"pipeline-infra"}

    def test_file_line_and_code_are_carried(self) -> None:
        first = self._signals()[0]
        assert first["file"] == "Dockerfile"
        assert (first["line_start"], first["line_end"]) == (1, 1)
        assert first["extra"]["code"] == "DL3006"

    def test_the_level_is_carried_as_a_severity_number(self) -> None:
        from tool_normalisers import HADOLINT_SEVERITY

        first = self._signals()[0]
        assert first["extra"]["severity"] == HADOLINT_SEVERITY["warning"]

    def test_hadolint_signals_are_fact_class(self) -> None:
        assert all(s["fact"] is True for s in self._signals())

    def test_an_unknown_level_falls_back_rather_than_raising(self) -> None:
        from tool_normalisers import normalise_hadolint

        payload = [{"file": "Dockerfile", "line": 3, "level": "nonsense",
                    "code": "DL9999", "message": "x"}]
        assert normalise_hadolint(payload, ROOT)[0]["extra"]["severity"] == 1


class TestNormaliseActionlint:
    def _signals(self) -> list:
        from tool_normalisers import normalise_actionlint

        payload = json.loads((FIXTURES / "actionlint.json").read_text(encoding="utf-8"))
        return normalise_actionlint(payload, ROOT)

    def test_each_record_becomes_one_workflow_signal(self) -> None:
        signals = self._signals()
        assert len(signals) == 2
        assert {s["kind"] for s in signals} == {"workflow"}
        assert {s["family"] for s in signals} == {"pipeline-infra"}

    def test_filepath_is_the_signal_file(self) -> None:
        assert {s["file"] for s in self._signals()} == {".github/workflows/ci.yml"}

    def test_the_kind_field_is_carried_in_extra(self) -> None:
        assert {s["extra"]["check"] for s in self._signals()} == {"action", "shellcheck"}

    def test_the_snippet_is_never_carried(self) -> None:
        """The snippet is a line of the workflow, which may hold a token; the
        file and line are enough to find it."""
        blob = json.dumps(self._signals())
        assert "snippet" not in blob
        assert "echo $VERSION" not in blob

    def test_actionlint_signals_are_fact_class(self) -> None:
        assert all(s["fact"] is True for s in self._signals())

    def test_a_record_without_a_filepath_is_dropped(self) -> None:
        from tool_normalisers import normalise_actionlint

        assert normalise_actionlint([{"message": "x", "line": 1}], ROOT) == []
