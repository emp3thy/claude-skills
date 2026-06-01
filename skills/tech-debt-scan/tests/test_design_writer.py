from __future__ import annotations

from pathlib import Path

import pytest
from design_writer import (
    DesignWriteError,
    mark_promoted,
    render_design_md,
)

GOLDEN = Path(__file__).parent / "golden" / "design.md"


def _top5_payload() -> dict:
    return {
        "top5": [
            {
                "slug": f"finding-{i}",
                "title": f"Finding {i} title",
                "severity": 5 - i % 5,
                "category": "god-modules",
                "reasoning": f"reasoning {i}",
                "evidence": [{"file": "src/x.py", "line": 10, "note": "n"}],
                "suggested_fix": f"fix {i}",
            }
            for i in range(5)
        ]
    }


def _inventory_payload() -> dict:
    return {
        "root": "/abs/path/to/repo",
        "total_files": 100,
        "total_loc": 12000,
        "languages": ["python"],
        "files": [],
    }


def test_render_matches_golden(tmp_path: Path):
    out = tmp_path / "design.md"
    render_design_md(
        top5=_top5_payload(),
        inventory=_inventory_payload(),
        scan_date="2026-05-31",
        out_path=out,
    )
    assert out.read_text(encoding="utf-8") == GOLDEN.read_text(encoding="utf-8")


def test_render_is_lf_only(tmp_path: Path):
    out = tmp_path / "design.md"
    render_design_md(
        top5=_top5_payload(),
        inventory=_inventory_payload(),
        scan_date="2026-05-31",
        out_path=out,
    )
    assert b"\r" not in out.read_bytes()


def test_render_empty_findings_raises(tmp_path: Path):
    with pytest.raises(DesignWriteError, match="no findings"):
        render_design_md(
            top5={"top5": []},
            inventory=_inventory_payload(),
            scan_date="2026-05-31",
            out_path=tmp_path / "design.md",
        )


def test_mark_promoted_status_transition(tmp_path: Path):
    src = tmp_path / "design.md"
    src.write_text(
        GOLDEN.read_text(encoding="utf-8").replace("status: pending", "status: approved", 1),
        encoding="utf-8",
    )
    mark_promoted(src, slugs=["finding-0"])
    text = src.read_text(encoding="utf-8")
    assert "status: promoted" in text
    # other findings unchanged
    assert text.count("status: pending") == 4


def test_mark_promoted_keeps_bak(tmp_path: Path):
    src = tmp_path / "design.md"
    pre = GOLDEN.read_text(encoding="utf-8").replace("status: pending", "status: approved", 1)
    src.write_text(pre, encoding="utf-8")
    mark_promoted(src, slugs=["finding-0"])
    bak = Path(str(src) + ".bak")
    assert bak.exists()
    assert bak.read_text(encoding="utf-8") == pre


def test_mark_promoted_idempotent_no_bak(tmp_path: Path):
    src = tmp_path / "design.md"
    # finding-0 already promoted; promoting it again is a no-op.
    src.write_text(
        GOLDEN.read_text(encoding="utf-8").replace("status: pending", "status: promoted", 1),
        encoding="utf-8",
    )
    mark_promoted(src, slugs=["finding-0"])
    assert not Path(str(src) + ".bak").exists()


def test_mark_promoted_unknown_slug_raises(tmp_path: Path):
    src = tmp_path / "design.md"
    src.write_text(GOLDEN.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(DesignWriteError, match="unknown slug"):
        mark_promoted(src, slugs=["not-a-finding"])


def test_mark_promoted_only_changes_approved(tmp_path: Path):
    src = tmp_path / "design.md"
    src.write_text(GOLDEN.read_text(encoding="utf-8"), encoding="utf-8")  # all pending
    with pytest.raises(DesignWriteError, match="not approved"):
        mark_promoted(src, slugs=["finding-0"])
