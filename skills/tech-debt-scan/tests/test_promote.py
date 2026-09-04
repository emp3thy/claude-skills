from __future__ import annotations

from pathlib import Path

import pytest
from promote import PromoteResult, run_promote

GOLDEN = Path(__file__).parent / "golden" / "design.md"


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
