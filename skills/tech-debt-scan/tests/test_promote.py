from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from promote import PromoteResult, run_promote

# design-v1.md is the v1 compatibility document (spec 8), not the v2 golden Task 7 adds.
GOLDEN = Path(__file__).parent / "golden" / "design-v1.md"


def test_no_approved_returns_zero(tmp_path: Path):
    src = tmp_path / "design.md"
    src.write_text(GOLDEN.read_text())  # all pending
    result = run_promote(src, out_root=tmp_path / "out")
    assert result.emitted_count == 0
    assert result.pending_count == 5
    assert result.exit_code == 0


def test_one_approved_emits_one_bundle(tmp_path: Path):
    src = tmp_path / "design.md"
    src.write_text(GOLDEN.read_text().replace("status: pending", "status: approved", 1))
    result = run_promote(src, out_root=tmp_path / "out", date="2026-05-31")
    assert result.emitted_count == 1
    assert (tmp_path / "out" / "chore-finding-0-2026-05-31").exists()
    # design.md mutated to promoted
    assert "status: promoted" in src.read_text()
    assert result.exit_code == 0


def test_idempotent_rerun(tmp_path: Path):
    src = tmp_path / "design.md"
    src.write_text(GOLDEN.read_text().replace("status: pending", "status: approved", 1))
    run_promote(src, out_root=tmp_path / "out", date="2026-05-31")
    result = run_promote(src, out_root=tmp_path / "out", date="2026-05-31")
    assert result.emitted_count == 0
    assert result.already_promoted_count == 1
    assert result.exit_code == 0


def test_invalid_status_exits_2(tmp_path: Path):
    src = tmp_path / "design.md"
    src.write_text(GOLDEN.read_text().replace("status: pending", "status: yes", 1))
    result = run_promote(src, out_root=tmp_path / "out")
    assert result.exit_code == 2


def test_two_approved_emits_two_bundles(tmp_path: Path):
    src = tmp_path / "design.md"
    src.write_text(GOLDEN.read_text().replace("status: pending", "status: approved", 2))
    result = run_promote(src, out_root=tmp_path / "out", date="2026-05-31")
    assert result.emitted_count == 2
    assert len(result.emitted_paths) == 2
    assert result.pending_count == 3
    text = src.read_text()
    assert text.count("status: promoted") == 2
    assert text.count("status: pending") == 3
    assert result.exit_code == 0


def test_rejected_counted_not_emitted(tmp_path: Path):
    src = tmp_path / "design.md"
    src.write_text(GOLDEN.read_text().replace("status: pending", "status: rejected", 1))
    result = run_promote(src, out_root=tmp_path / "out", date="2026-05-31")
    assert result.emitted_count == 0
    assert result.rejected_count == 1
    assert result.pending_count == 4
    assert result.exit_code == 0


def test_default_result_emitted_paths_is_list():
    # per [[462d13a7-grep-test-callsites]]: PromoteResult() constructs cleanly
    # with a fresh list, not a shared mutable default.
    assert PromoteResult().emitted_paths == []
    a, b = PromoteResult(), PromoteResult()
    a.emitted_paths.append(Path("x"))
    assert b.emitted_paths == []


def test_accepted_counted_separately_from_pending(tmp_path: Path) -> None:
    src = tmp_path / "design.md"
    src.write_text(GOLDEN.read_text().replace("status: pending", "status: accepted", 1))
    result = run_promote(src, out_root=tmp_path / "out", date="2026-05-31")
    assert result.exit_code == 0
    assert result.emitted_count == 0
    assert result.accepted_count == 1
    assert result.pending_count == 4
    assert result.rejected_count == 0
    assert "status: accepted" in src.read_text()


def test_summary_line_reports_accepted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from promote import _main

    src = tmp_path / "design.md"
    src.write_text(GOLDEN.read_text().replace("status: pending", "status: accepted", 2))
    assert _main([str(src), "--out", str(tmp_path / "out")]) == 0
    out = capsys.readouterr().out
    assert "accepted: 2" in out
    assert "pending: 3" in out


def test_accepted_is_counted_and_never_pending(tmp_path: Path) -> None:
    design = tmp_path / "design.md"
    design.write_bytes("\n".join([
        "## Accepted finding", "", "```yaml", "status: accepted", "slug: accepted-finding",
        "severity: 3", "category: security", "reason: waiting for the rewrite",
        "until: 2027-01-31", "```", "", "body", "",
        "## Pending finding", "", "```yaml", "status: pending", "slug: pending-finding",
        "severity: 2", "category: security", "```", "", "body", "",
    ]).encode("utf-8"))
    result = run_promote(design, out_root=tmp_path / "out", date="2026-09-06")
    assert result.accepted_count == 1 and result.pending_count == 1
    assert result.emitted_count == 0 and result.exit_code == 0


def test_write_back_exit_code_is_reserved() -> None:
    from promote import EXIT_WRITE_BACK

    assert EXIT_WRITE_BACK == 6


class TestWriteBack:
    def test_without_baseline_flag_nothing_is_written(self, v2_design_workdir) -> None:
        from promote import _main

        design, workdir = v2_design_workdir
        assert _main([str(design), "--out", str(workdir / "pbis")]) == 0
        assert not (workdir / "baseline.json").exists()

    def test_with_baseline_flag_every_decision_is_recorded(self, v2_design_workdir) -> None:
        from baseline import load_baseline
        from promote import _main

        design, workdir = v2_design_workdir
        baseline = workdir / "baseline.json"
        code = _main([str(design), "--out", str(workdir / "pbis"), "--baseline", str(baseline)])
        assert code == 0
        doc = load_baseline(baseline)
        assert doc is not None
        statuses = {e["status"] for e in doc["findings"].values()}
        assert "promoted" in statuses  # every approved finding was emitted, so is now promoted

    def test_an_emitted_finding_records_its_bundle_directory(self, v2_design_workdir) -> None:
        from baseline import load_baseline
        from promote import _main

        design, workdir = v2_design_workdir
        baseline = workdir / "baseline.json"
        _main([str(design), "--out", str(workdir / "pbis"), "--baseline", str(baseline)])
        doc = load_baseline(baseline)
        promoted = [e for e in doc["findings"].values() if e["status"] == "promoted"]
        assert promoted and all(e["bundle"] for e in promoted)
        assert all((workdir / "pbis" / e["bundle"]).is_dir() for e in promoted)

    def test_write_back_failure_is_exit_6_and_bundles_remain(
        self, v2_design_workdir, monkeypatch
    ) -> None:
        import baseline as bmod
        from promote import EXIT_WRITE_BACK, _main

        design, workdir = v2_design_workdir

        def boom(*a, **k):
            raise bmod.BaselineError("simulated")

        monkeypatch.setattr(bmod, "record", boom)
        code = _main([str(design), "--out", str(workdir / "pbis"), "--baseline",
                      str(workdir / "baseline.json")])
        assert code == EXIT_WRITE_BACK == 6
        assert any((workdir / "pbis").iterdir()), "bundles emitted before the write-back remain"

    def test_a_promote_failure_is_not_reported_as_write_back(self, v2_design_workdir) -> None:
        """Exit 6 means the write-back failed and nothing else did."""
        from promote import EXIT_WRITE_BACK, _main

        design, workdir = v2_design_workdir
        baseline = workdir / "b.json"
        # A second run without --force hits the already-promoted path, which is not exit 6.
        _main([str(design), "--out", str(workdir / "pbis"), "--baseline", str(baseline)])
        code = _main([str(design), "--out", str(workdir / "pbis"), "--baseline", str(baseline)])
        assert code != EXIT_WRITE_BACK

    def test_v1_design_with_baseline_refuses_before_emitting(self, tmp_path: Path) -> None:
        from promote import _main

        design = tmp_path / "design.md"
        design.write_text(GOLDEN.read_text().replace("status: pending", "status: approved", 1))
        code = _main([str(design), "--out", str(tmp_path / "out"), "--baseline",
                      str(tmp_path / "baseline.json")])
        assert code == 2
        assert not (tmp_path / "out").exists()
        assert not (tmp_path / "baseline.json").exists()

    def test_already_promoted_finding_with_no_baseline_history_is_exit_zero(
        self, v2_design_workdir
    ) -> None:
        """A finding promoted before --baseline existed has no map entry and no
        baseline history; run_promote's already-promoted path must supply its
        existing bundle directory so record() does not raise."""
        from baseline import load_baseline
        from promote import _main

        design, workdir = v2_design_workdir
        out = workdir / "pbis"
        # First run with no --baseline: emits the bundle and marks it promoted,
        # exactly like every promote run before this task existed.
        assert _main([str(design), "--out", str(out)]) == 0
        assert not (workdir / "baseline.json").exists()

        baseline = workdir / "baseline.json"
        code = _main([str(design), "--out", str(out), "--baseline", str(baseline)])
        assert code == 0
        doc = load_baseline(baseline)
        assert doc is not None
        promoted = [e for e in doc["findings"].values() if e["status"] == "promoted"]
        assert promoted and all(e["bundle"] for e in promoted)
        assert all((out / e["bundle"]).is_dir() for e in promoted)

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
        from promote import _main

        design, workdir = v2_design_workdir
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

        code = _main([str(design), "--out", str(workdir / "pbis"), "--baseline",
                      str(baseline_path)])
        assert code == 0
        text = (repo / ".gitignore").read_text(encoding="utf-8")
        assert text.endswith("!.tech-debt/\n.tech-debt/*\n!.tech-debt/baseline.json\n")

    def test_malformed_ranked_json_is_exit_6_and_bundles_remain(
        self, v2_design_workdir
    ) -> None:
        """A malformed ranked.json raised json.JSONDecodeError uncaught before
        this fix (Finding #1, mode 2); the write-back must degrade to exit 6,
        same as a BaselineError, with the bundles already emitted left intact."""
        from promote import EXIT_WRITE_BACK, _main

        design, workdir = v2_design_workdir
        (workdir / "ranked.json").write_text("{not json", encoding="utf-8")

        code = _main([str(design), "--out", str(workdir / "pbis"), "--baseline",
                      str(workdir / "baseline.json")])
        assert code == EXIT_WRITE_BACK == 6
        assert any((workdir / "pbis").iterdir()), "bundles emitted before the write-back remain"
        assert not (workdir / "baseline.json").exists()

    def test_prefers_previously_recorded_bundle_over_newest_glob_match(
        self, v2_design_workdir
    ) -> None:
        """Three dated bundle directories exist for one slug: one older than the
        recorded bundle, the recorded bundle itself, and one newer -- neither
        "oldest" (pre-fix behavior) nor "newest" alone picks the recorded
        directory here, so only Ruling 2's actual rule (prefer the baseline's
        own record, else newest) can pass this."""
        from baseline import load_baseline
        from promote import _main

        design, workdir = v2_design_workdir
        out = workdir / "pbis"
        baseline_path = workdir / "baseline.json"

        assert _main([str(design), "--out", str(out)]) == 0
        assert _main([str(design), "--out", str(out), "--baseline", str(baseline_path)]) == 0
        doc1 = load_baseline(baseline_path)
        promoted1 = [e for e in doc1["findings"].values() if e["status"] == "promoted"]
        assert len(promoted1) == 1
        recorded_bundle = promoted1[0]["bundle"]

        # Neither fake directory is ever recorded in the baseline; they only
        # simulate stray regenerations left on disk. One sorts before the
        # recorded bundle, one sorts after it -- oldest-pick and newest-pick
        # each land on a different wrong directory, never the recorded one.
        slug = recorded_bundle.removeprefix("chore-")[:-11]
        (out / f"chore-{slug}-2000-01-01").mkdir()
        (out / f"chore-{slug}-9999-01-01").mkdir()

        assert _main([str(design), "--out", str(out), "--baseline", str(baseline_path)]) == 0
        doc2 = load_baseline(baseline_path)
        promoted2 = [e for e in doc2["findings"].values() if e["status"] == "promoted"]
        assert promoted2[0]["bundle"] == recorded_bundle, "must keep the baseline's own record"

    def test_preset_is_forwarded_from_ranked_json(self, v2_design_workdir) -> None:
        """A mutant hard-coding a wrong preset must fail this: the baseline's
        preset must equal ranked.json's actual value, not just its fallback."""
        from baseline import load_baseline
        from promote import _main

        design, workdir = v2_design_workdir
        ranked_path = workdir / "ranked.json"
        ranked = json.loads(ranked_path.read_bytes())
        ranked["preset"] = "hotspot-first"
        ranked_path.write_text(json.dumps(ranked), encoding="utf-8")

        baseline_path = workdir / "baseline.json"
        assert _main([str(design), "--out", str(workdir / "pbis"), "--baseline",
                      str(baseline_path)]) == 0
        doc = load_baseline(baseline_path)
        assert doc is not None
        assert doc["preset"] == "hotspot-first"

    def test_preset_defaults_to_balanced_when_ranked_json_absent(
        self, v2_design_workdir
    ) -> None:
        from baseline import load_baseline
        from promote import _main

        design, workdir = v2_design_workdir
        (workdir / "ranked.json").unlink()

        baseline_path = workdir / "baseline.json"
        assert _main([str(design), "--out", str(workdir / "pbis"), "--baseline",
                      str(baseline_path)]) == 0
        doc = load_baseline(baseline_path)
        assert doc is not None
        assert doc["preset"] == "balanced"

    def test_promote_failure_writes_no_baseline(self, v2_design_workdir, monkeypatch) -> None:
        """A mutant deleting `and result.exit_code == 0` from _main's write-back
        gate must fail this: when run_promote itself fails for a reason other
        than the v1 precheck, no write-back may be attempted.

        A pre-existing bundle without --force does not, on its own, produce
        this: run_promote's approved branch treats a BundleWriteError whose
        message contains "already exists" as an idempotent already-promoted
        case (exit stays 0), by design -- verified directly against this
        checkout before writing this test. A genuine bundle-write failure
        (disk full, permission denied, ...) is simulated instead, since it is
        the only way run_promote's exit_code actually becomes nonzero here.
        """
        import promote as pmod
        from promote import _main

        design, workdir = v2_design_workdir

        def boom(*_a: object, **_k: object) -> None:
            raise pmod.BundleWriteError("cannot write bundle: disk full")

        monkeypatch.setattr(pmod, "write_bundle", boom)
        baseline_path = workdir / "baseline.json"
        code = _main([str(design), "--out", str(workdir / "pbis"), "--baseline",
                      str(baseline_path)])
        assert code == 4
        assert not baseline_path.exists()
