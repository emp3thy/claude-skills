from __future__ import annotations

from pathlib import Path

import pytest
from bundle_writer import BundleWriteError, write_bundle

GOLDEN_DIR = Path(__file__).parent / "golden" / "bundle"


def _finding() -> dict:
    return {
        "slug": "finding-0",
        "title": "Finding 0 title",
        "severity": 5,
        "category": "god-modules",
        "confidence": 5,
        "change_size": "L",
        "change_risk": "med",
        "disposition": "full-repayment",
        "body_md": (
            "### Evidence\n\n- foo\n\n### Suggested fix\n\nbar\n\n"
            "### Why now\n\nhot\n\n### Scope boundary\n\nnarrow\n\n"
            "### Acceptance criteria\n\ntests pass\n"
        ),
        "status": "approved",
    }


def test_write_bundle_creates_canonical_files(tmp_path: Path):
    written = write_bundle(_finding(), out_root=tmp_path, source_design="d.md", date="2026-05-31")
    bundle_dir = tmp_path / "chore-finding-0-2026-05-31"
    assert bundle_dir.is_dir()
    assert (bundle_dir / "PBI.md").exists()
    assert (bundle_dir / "PLAN.md").exists()
    assert (bundle_dir / "HISTORY.md").exists()
    assert written == bundle_dir


def test_pbi_contains_target_repo_key(tmp_path: Path):
    write_bundle(_finding(), out_root=tmp_path, source_design="d.md", date="2026-05-31")
    pbi = (tmp_path / "chore-finding-0-2026-05-31" / "PBI.md").read_text()
    assert "target_repo:" in pbi  # per [[77c83c69-target-repo-required]]
    assert "type: chore" in pbi


def test_collision_without_force_raises(tmp_path: Path):
    write_bundle(_finding(), out_root=tmp_path, source_design="d.md", date="2026-05-31")
    with pytest.raises(BundleWriteError, match="already exists"):
        write_bundle(
            _finding(), out_root=tmp_path, source_design="d.md", date="2026-05-31", force=False
        )


def test_force_overwrites(tmp_path: Path):
    write_bundle(_finding(), out_root=tmp_path, source_design="d.md", date="2026-05-31")
    finding2 = _finding()
    finding2["body_md"] = "### Evidence\n\n- DIFFERENT\n"
    write_bundle(finding2, out_root=tmp_path, source_design="d.md", date="2026-05-31", force=True)
    pbi = (tmp_path / "chore-finding-0-2026-05-31" / "PBI.md").read_text()
    assert "DIFFERENT" in pbi


def test_unwritable_out_dir(tmp_path: Path, monkeypatch):
    def _no_mkdir(*a, **kw):
        raise PermissionError("no write")
    monkeypatch.setattr(Path, "mkdir", _no_mkdir)
    with pytest.raises(BundleWriteError, match="cannot write"):
        write_bundle(_finding(), out_root=tmp_path, source_design="d.md", date="2026-05-31")


def test_written_files_byte_match_golden(tmp_path: Path):
    """The rendered bundle is byte-identical to the canonical golden bundle."""
    bundle_dir = write_bundle(
        _finding(), out_root=tmp_path, source_design="d.md", date="2026-05-31"
    )
    for name in ("PBI.md", "PLAN.md", "HISTORY.md"):
        golden = (GOLDEN_DIR / "chore-finding-0-2026-05-31" / name).read_text(encoding="utf-8")
        actual = (bundle_dir / name).read_text(encoding="utf-8")
        assert actual == golden, f"{name} drifted from golden"


def test_pbi_contains_change_profile(tmp_path: Path):
    write_bundle(_finding(), out_root=tmp_path, source_design="d.md", date="2026-05-31")
    pbi = (tmp_path / "chore-finding-0-2026-05-31" / "PBI.md").read_text()
    assert "change_size: L" in pbi
    assert "change_risk: med" in pbi
    assert "disposition: full-repayment" in pbi
    assert "confidence: 5" in pbi
    assert "### Acceptance criteria" in pbi  # rides body_md


def test_written_files_are_lf_only(tmp_path: Path):
    bundle_dir = write_bundle(
        _finding(), out_root=tmp_path, source_design="d.md", date="2026-05-31"
    )
    for name in ("PBI.md", "PLAN.md", "HISTORY.md"):
        raw = (bundle_dir / name).read_bytes()
        assert b"\r" not in raw, f"{name} contains CR bytes"
