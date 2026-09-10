from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from design_parser import parse_design

# design-v1.md is the v1 compatibility document (spec 8), not the v2 golden Task 7 adds.
GOLDEN = Path(__file__).parent / "golden" / "design-v1.md"


def test_invalid_status_exits_2(tmp_path: Path) -> None:
    """An invalid status value fails parse_design itself -- there is no
    run_promote status dispatch left to reach; _main's own initial parse call
    is what turns this into exit 2."""
    from promote import _main

    src = tmp_path / "design.md"
    src.write_text(GOLDEN.read_text().replace("status: pending", "status: yes", 1))
    assert _main([str(src), "--list-approved"]) == 2


def test_write_back_exit_code_is_reserved() -> None:
    from promote import EXIT_WRITE_BACK

    assert EXIT_WRITE_BACK == 6


class TestWriteBack:
    def test_without_baseline_flag_nothing_is_written(self, v2_design_workdir) -> None:
        from promote import _main, list_approved

        design, workdir = v2_design_workdir
        slug = list_approved(design)[0]["slug"]
        assert _main([str(design), "--select", slug]) == 0
        assert not (workdir / "baseline.json").exists()

    def test_with_baseline_flag_every_decision_is_recorded(self, v2_design_workdir) -> None:
        from baseline import load_baseline
        from promote import _main, list_approved

        design, workdir = v2_design_workdir
        slug = list_approved(design)[0]["slug"]
        baseline_path = workdir / "baseline.json"
        code = _main([str(design), "--select", slug, "--baseline", str(baseline_path)])
        assert code == 0
        doc = load_baseline(baseline_path)
        assert doc is not None
        statuses = {e["status"] for e in doc["findings"].values()}
        assert "promoted" in statuses  # the selected finding is now promoted

    def test_write_back_failure_is_exit_6_and_evidence_remains(
        self, v2_design_workdir, monkeypatch
    ) -> None:
        import baseline as bmod
        from promote import EXIT_WRITE_BACK, _main, list_approved

        design, workdir = v2_design_workdir
        slug = list_approved(design)[0]["slug"]

        def boom(*a, **k):
            raise bmod.BaselineError("simulated")

        monkeypatch.setattr(bmod, "record", boom)
        code = _main(
            [str(design), "--select", slug, "--baseline", str(workdir / "baseline.json")]
        )
        assert code == EXIT_WRITE_BACK == 6
        assert (workdir / "evidence.md").is_file(), "evidence written before the write-back remains"

    def test_v1_design_with_baseline_refuses_before_emitting(self, tmp_path: Path) -> None:
        from promote import _main

        design = tmp_path / "design.md"
        design.write_text(GOLDEN.read_text().replace("status: pending", "status: approved", 1))
        slug = parse_design(design)["findings"][0]["slug"]
        code = _main(
            [str(design), "--select", slug, "--baseline", str(tmp_path / "baseline.json")]
        )
        assert code == 2
        assert not (tmp_path / "evidence.md").exists()
        assert not (tmp_path / "baseline.json").exists()

    def test_already_selected_finding_with_no_baseline_history_is_exit_zero(
        self, v2_design_workdir
    ) -> None:
        """A finding promoted before --baseline existed has no baseline history;
        select's SELECTABLE ({"approved", "promoted"}) must let a later
        --baseline run record it anyway."""
        from baseline import load_baseline
        from promote import _main, list_approved

        design, workdir = v2_design_workdir
        slug = list_approved(design)[0]["slug"]
        # First run with no --baseline: writes evidence.md and marks promoted,
        # exactly like every select run before this task existed.
        assert _main([str(design), "--select", slug]) == 0
        assert not (workdir / "baseline.json").exists()

        baseline_path = workdir / "baseline.json"
        code = _main([str(design), "--select", slug, "--baseline", str(baseline_path)])
        assert code == 0
        doc = load_baseline(baseline_path)
        assert doc is not None
        promoted = [e for e in doc["findings"].values() if e["status"] == "promoted"]
        assert promoted

    # -- Fix round 1 --------------------------------------------------------

    @pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
    def test_root_is_derived_from_baseline_not_cwd(
        self, v2_design_workdir, monkeypatch
    ) -> None:
        """cwd need not be an ancestor of --baseline's path: SKILL.md's documented
        invocation cwd (skills/tech-debt-scan/) is generally unrelated to the
        scanned repo, and a cwd inside a subdirectory of the scanned repo isn't
        an ancestor of .tech-debt/ either. Reproduced (Finding #1) as an
        uncaught ValueError from Path.relative_to before this fix; root must be
        derived from --baseline's own path instead."""
        from promote import _main, list_approved

        design, workdir = v2_design_workdir
        slug = list_approved(design)[0]["slug"]
        repo = workdir / "repo"
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / ".gitignore").write_text(".tech-debt/\n", encoding="utf-8")
        tech_debt = repo / ".tech-debt"
        tech_debt.mkdir()
        baseline_path = tech_debt / "baseline.json"
        ignored = subprocess.run(
            ["git", "-C", str(repo), "check-ignore", "-q", ".tech-debt/baseline.json"]
        )
        assert ignored.returncode == 0, "precondition: the baseline starts ignored"

        elsewhere = workdir / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)

        code = _main([str(design), "--select", slug, "--baseline", str(baseline_path)])
        assert code == 0
        text = (repo / ".gitignore").read_text(encoding="utf-8")
        assert text.endswith("!.tech-debt/\n.tech-debt/*\n!.tech-debt/baseline.json\n")

    def test_malformed_ranked_json_is_exit_6_and_evidence_remains(
        self, v2_design_workdir
    ) -> None:
        """A malformed ranked.json raised json.JSONDecodeError uncaught before
        this fix (Finding #1, mode 2); the write-back must degrade to exit 6,
        same as a BaselineError, with evidence.md already written left intact."""
        from promote import EXIT_WRITE_BACK, _main, list_approved

        design, workdir = v2_design_workdir
        slug = list_approved(design)[0]["slug"]
        (workdir / "ranked.json").write_text("{not json", encoding="utf-8")

        code = _main(
            [str(design), "--select", slug, "--baseline", str(workdir / "baseline.json")]
        )
        assert code == EXIT_WRITE_BACK == 6
        assert (workdir / "evidence.md").is_file(), "evidence written before the write-back remains"
        assert not (workdir / "baseline.json").exists()

    def test_malformed_candidates_json_is_exit_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A malformed candidates.json raised json.JSONDecodeError (a ValueError)
        uncaught through select() before this fix (Important #2); _main's own
        except tuple must degrade it to the documented exit 2, with the error on
        stderr, rather than an unhandled traceback."""
        from promote import _main, list_approved

        src = _v2_design(tmp_path)
        slug = list_approved(src)[0]["slug"]
        (tmp_path / "candidates.json").write_text("{not json", encoding="utf-8")

        code = _main([str(src), "--select", slug])
        assert code == 2
        err = capsys.readouterr().err
        assert err.startswith("error: ")
        assert not (tmp_path / "evidence.md").exists()

    def test_preset_is_forwarded_from_ranked_json(self, v2_design_workdir) -> None:
        """A mutant hard-coding a wrong preset must fail this: the baseline's
        preset must equal ranked.json's actual value, not just its fallback."""
        from baseline import load_baseline
        from promote import _main, list_approved

        design, workdir = v2_design_workdir
        slug = list_approved(design)[0]["slug"]
        ranked_path = workdir / "ranked.json"
        ranked = json.loads(ranked_path.read_bytes())
        ranked["preset"] = "hotspot-first"
        ranked_path.write_text(json.dumps(ranked), encoding="utf-8")

        baseline_path = workdir / "baseline.json"
        assert _main(
            [str(design), "--select", slug, "--baseline", str(baseline_path)]
        ) == 0
        doc = load_baseline(baseline_path)
        assert doc is not None
        assert doc["preset"] == "hotspot-first"

    def test_preset_defaults_to_balanced_when_ranked_json_absent(
        self, v2_design_workdir
    ) -> None:
        from baseline import load_baseline
        from promote import _main, list_approved

        design, workdir = v2_design_workdir
        slug = list_approved(design)[0]["slug"]
        (workdir / "ranked.json").unlink()

        baseline_path = workdir / "baseline.json"
        assert _main(
            [str(design), "--select", slug, "--baseline", str(baseline_path)]
        ) == 0
        doc = load_baseline(baseline_path)
        assert doc is not None
        assert doc["preset"] == "balanced"

    def test_select_failure_writes_no_baseline(self, v2_design_workdir) -> None:
        """A mutant that reaches the write-back even when select() failed must
        fail this: _main returns immediately on a SelectionError, before the
        --baseline write-back is ever attempted."""
        from promote import _main

        design, workdir = v2_design_workdir
        baseline_path = workdir / "baseline.json"
        code = _main(
            [str(design), "--select", "no-such-slug", "--baseline", str(baseline_path)]
        )
        assert code == 2
        assert not baseline_path.exists()

    def test_a_design_parse_error_in_the_write_back_is_exit_6(
        self, v2_design_workdir, monkeypatch
    ) -> None:
        """The write-back re-parses design.md after select's own mark-promoted
        mutation, so a DesignParseError is one of the failures it can genuinely
        raise -- from a document that was edited between the two parses, or a
        mutation that left it unparseable. It belongs with the other write-back
        failures at exit 6: evidence.md is on disk and the previous baseline is
        untouched, which is exactly what exit 6 tells the user."""
        import sys

        import promote as pmod
        from design_parser import DesignParseError
        from promote import EXIT_WRITE_BACK, _main, list_approved

        design, workdir = v2_design_workdir
        slug = list_approved(design)[0]["slug"]
        baseline_path = workdir / "baseline.json"
        assert _main(
            [str(design), "--select", slug, "--baseline", str(baseline_path)]
        ) == 0
        before = baseline_path.read_bytes()
        assert (workdir / "evidence.md").is_file()

        real = pmod.parse_design

        def parse(path: Path) -> dict:
            # Only the write-back's own call fails; _main's own initial parse
            # and select() must both parse normally, or the run would never
            # reach the write-back at all.
            if sys._getframe(1).f_code.co_name == "_write_back":
                raise DesignParseError("simulated: unparseable after mark_promoted")
            return real(path)

        monkeypatch.setattr(pmod, "parse_design", parse)
        code = _main(
            [str(design), "--select", slug, "--baseline", str(baseline_path)]
        )
        assert code == EXIT_WRITE_BACK == 6
        assert (workdir / "evidence.md").is_file()
        assert baseline_path.read_bytes() == before, "the previous baseline is intact"

    def test_write_back_records_an_empty_v2_design(self, tmp_path: Path) -> None:
        """A v2 design.md with no findings at all carries no fingerprints
        either, but is not a v1 document -- --baseline given alone (the
        record-only mode) must record it as an empty baseline rather than
        refusing it as a v1 design.md."""
        from baseline import load_baseline
        from promote import _main

        design = tmp_path / "design.md"
        design.write_text(
            "---\nschema_version: 2\nscan_date: 2026-09-06\nroot: /repo\n"
            "counts:\n  candidates: 0\n  verified: 0\n---\n\n"
            "# Tech debt scan\n\nNo findings this run.\n",
            encoding="utf-8",
        )
        baseline_path = tmp_path / "baseline.json"
        assert _main([str(design), "--baseline", str(baseline_path)]) == 0
        doc = load_baseline(baseline_path)
        assert doc is not None and doc["findings"] == {}


# design-worked-example.md is the v2 golden: two findings, both `status: pending`,
# both carrying fingerprints. Document order is severity 4 then severity 5.
V2_GOLDEN = Path(__file__).parent / "golden" / "design-worked-example.md"


def _v2_design(tmp_path: Path, *, approve: int = 1) -> Path:
    src = tmp_path / "design.md"
    src.write_text(
        V2_GOLDEN.read_text(encoding="utf-8").replace(
            "status: pending", "status: approved", approve
        ),
        encoding="utf-8",
    )
    return src


def test_list_approved_returns_only_approved_rows(tmp_path: Path) -> None:
    from promote import list_approved

    rows = list_approved(_v2_design(tmp_path, approve=2))
    assert len(rows) == 2
    assert set(rows[0]) == {
        "slug", "title", "family", "severity", "effort", "primary_file", "fingerprint",
    }
    assert all(isinstance(row["severity"], int) for row in rows)


def test_list_approved_is_empty_when_nothing_is_approved(tmp_path: Path) -> None:
    from promote import list_approved

    src = tmp_path / "design.md"
    src.write_text(V2_GOLDEN.read_text(encoding="utf-8"), encoding="utf-8")
    assert list_approved(src) == []


def test_list_approved_orders_by_severity_descending(tmp_path: Path) -> None:
    """The golden's severity-4 finding precedes its severity-5 one in the
    document, so a passing assertion here proves the sort, not the file order."""
    from promote import list_approved

    rows = list_approved(_v2_design(tmp_path, approve=2))
    assert [row["severity"] for row in rows] == [5, 4]
    assert rows[0]["slug"] == "hard-coded-credential-in-the-gateway-client"


def test_select_writes_evidence_and_marks_promoted(tmp_path: Path) -> None:
    from promote import list_approved, select

    src = _v2_design(tmp_path)
    slug = list_approved(src)[0]["slug"]
    written = select(src, slug)

    assert written == tmp_path / "evidence.md"
    text = written.read_text(encoding="utf-8")
    assert text.startswith("# ")
    assert "Repository: " in text
    assert "status: promoted" in src.read_text(encoding="utf-8")
    assert list_approved(src) == []


def test_select_folds_in_matching_open_questions(tmp_path: Path) -> None:
    from promote import list_approved, select

    src = _v2_design(tmp_path)
    finding = list_approved(src)[0]
    primary = finding["primary_file"]
    (tmp_path / "candidates.json").write_text(
        json.dumps({
            "open_questions": [
                {"file": primary, "line_start": 1, "question": "Is this deliberate?"}
            ],
            "looks_bad_but_fine": [],
        }),
        encoding="utf-8",
    )
    text = select(src, finding["slug"]).read_text(encoding="utf-8")
    assert "### Open questions from the scan" in text
    assert "Is this deliberate?" in text


def test_select_rejects_an_unknown_slug(tmp_path: Path) -> None:
    from promote import SelectionError, select

    with pytest.raises(SelectionError, match="unknown"):
        select(_v2_design(tmp_path), "no-such-slug")


def test_select_rejects_a_pending_finding(tmp_path: Path) -> None:
    from promote import SelectionError, select

    src = tmp_path / "design.md"
    src.write_text(V2_GOLDEN.read_text(encoding="utf-8"), encoding="utf-8")
    slug = parse_design(src)["findings"][0]["slug"]
    with pytest.raises(SelectionError, match="pending"):
        select(src, slug)


def test_select_accepts_an_already_promoted_finding(tmp_path: Path) -> None:
    """A re-run after a failed baseline write, or a second design session on
    the same finding, must be possible."""
    from promote import list_approved, select

    src = _v2_design(tmp_path)
    slug = list_approved(src)[0]["slug"]
    select(src, slug)
    written = select(src, slug)
    assert written.is_file()


def test_select_wraps_a_mark_promoted_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """evidence.md is already on disk once mark_promoted is reached; the
    caller must be told, and design.md must stay approved so a retry can
    re-render and re-attempt the mark cleanly."""
    import promote as pmod
    from promote import SelectionError, list_approved, select

    src = _v2_design(tmp_path)
    slug = list_approved(src)[0]["slug"]

    def boom(*_a: object, **_k: object) -> None:
        raise pmod.DesignWriteError("simulated: permission denied")

    monkeypatch.setattr(pmod, "mark_promoted", boom)

    with pytest.raises(SelectionError) as excinfo:
        select(src, slug)
    assert str(tmp_path / "evidence.md") in str(excinfo.value)

    assert (tmp_path / "evidence.md").is_file()
    assert "status: approved" in src.read_text(encoding="utf-8")


def test_main_list_approved_prints_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from promote import _main

    src = _v2_design(tmp_path)
    assert _main([str(src), "--list-approved"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 1 and rows[0]["slug"]


def test_main_select_writes_evidence(tmp_path: Path) -> None:
    from promote import _main, list_approved

    src = _v2_design(tmp_path)
    slug = list_approved(src)[0]["slug"]
    assert _main([str(src), "--select", slug]) == 0
    assert (tmp_path / "evidence.md").is_file()


def test_main_requires_a_mode(tmp_path: Path) -> None:
    from promote import _main

    with pytest.raises(SystemExit):
        _main([str(_v2_design(tmp_path))])


def test_main_rejects_list_approved_combined_with_baseline(tmp_path: Path) -> None:
    """M2: --list-approved is read-only; combining it with --baseline must be
    rejected rather than silently ignoring --baseline."""
    from promote import _main

    src = _v2_design(tmp_path)
    baseline_path = tmp_path / "baseline.json"
    with pytest.raises(SystemExit):
        _main([str(src), "--list-approved", "--baseline", str(baseline_path)])
    assert not baseline_path.exists()


def test_baseline_alone_records_decisions_without_selecting(tmp_path: Path) -> None:
    """I3: a review that rejects everything and approves nothing must still
    get those rejections recorded -- --baseline given alone (no --select)
    records every finding's current decision and writes no evidence.md."""
    from baseline import load_baseline
    from promote import _main

    src = tmp_path / "design.md"
    src.write_text(
        V2_GOLDEN.read_text(encoding="utf-8").replace("status: pending", "status: rejected"),
        encoding="utf-8",
    )
    baseline_path = tmp_path / "baseline.json"
    assert _main([str(src), "--baseline", str(baseline_path)]) == 0
    assert not (tmp_path / "evidence.md").exists()
    assert "status: rejected" in src.read_text(encoding="utf-8")

    doc = load_baseline(baseline_path)
    assert doc is not None
    statuses = {e["status"] for e in doc["findings"].values()}
    assert statuses == {"rejected"}


# -- Fix round 1 --------------------------------------------------------------
# _main's own initial parse (line ~243) can succeed while list_approved's and
# select's own internal re-parse of the same design.md fails -- the design.md
# on disk can change between the two calls, exactly like _write_back's own
# re-parse already accounts for. Both re-parse call sites must degrade to the
# documented "error: ...", exit 2, never an unhandled traceback.


def test_main_list_approved_reports_a_reparse_failure_as_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """list_approved() re-parses design.md internally; _main's own initial
    parse succeeding must not paper over that second parse failing."""
    import sys

    import promote as pmod
    from design_parser import DesignParseError
    from promote import _main

    src = _v2_design(tmp_path)
    real = pmod.parse_design

    def parse(path: Path) -> dict:
        # Only list_approved's own re-parse fails; _main's initial parse must
        # succeed, or the run would never reach --list-approved's branch.
        if sys._getframe(1).f_code.co_name == "list_approved":
            raise DesignParseError("simulated: unparseable on re-parse")
        return real(path)

    monkeypatch.setattr(pmod, "parse_design", parse)
    assert _main([str(src), "--list-approved"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error: ") and "simulated: unparseable on re-parse" in err


def test_main_select_reports_a_reparse_failure_as_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """select() re-parses design.md internally; the same guarantee applies to
    --select as to --list-approved."""
    import sys

    import promote as pmod
    from design_parser import DesignParseError
    from promote import _main, list_approved

    src = _v2_design(tmp_path)
    slug = list_approved(src)[0]["slug"]
    real = pmod.parse_design

    def parse(path: Path) -> dict:
        # Only select's own re-parse fails; _main's initial parse must
        # succeed, or the run would never reach the --select branch.
        if sys._getframe(1).f_code.co_name == "select":
            raise DesignParseError("simulated: unparseable on re-parse")
        return real(path)

    monkeypatch.setattr(pmod, "parse_design", parse)
    assert _main([str(src), "--select", slug]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error: ") and "simulated: unparseable on re-parse" in err
