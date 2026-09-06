from __future__ import annotations

from pathlib import Path

import pytest
from bundle_writer import BundleWriteError, write_bundle

GOLDEN = Path(__file__).parent / "golden"
GOLDEN_DIR = GOLDEN / "bundle"


def _finding() -> dict:
    return {
        "slug": "finding-0",
        "title": "Finding 0 title",
        "severity": 5,
        "category": "god-modules",
        "body_md": "### Evidence\n\n- foo\n\n### Suggested fix\n\nbar\n",
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
    assert "type: feature" in pbi


def test_pbi_carries_created_and_updated_timestamps(tmp_path: Path):
    # ralph filesystem queue parser requires both fields; bundle writer must emit them
    # from the date arg so ralph can claim the PBI without further editing.
    # Full ISO datetime — bare YYYY-MM-DD parses as a YAML `date` which the ralph queue
    # parser rejects (it only accepts datetime or ISO-8601 string).
    write_bundle(_finding(), out_root=tmp_path, source_design="d.md", date="2026-05-31")
    pbi = (tmp_path / "chore-finding-0-2026-05-31" / "PBI.md").read_text()
    assert "created_at: 2026-05-31T00:00:00+00:00" in pbi
    assert "updated_at: 2026-05-31T00:00:00+00:00" in pbi


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


def test_pbi_includes_classification_fields_when_present(tmp_path: Path):
    finding = _finding()
    finding["debt_type"] = "design"
    finding["effort"] = "M"
    write_bundle(finding, out_root=tmp_path, source_design="d.md", date="2026-05-31")
    pbi = (tmp_path / "chore-finding-0-2026-05-31" / "PBI.md").read_text()
    assert "debt_type: design" in pbi
    assert "effort: M" in pbi


def test_written_files_are_lf_only(tmp_path: Path):
    bundle_dir = write_bundle(
        _finding(), out_root=tmp_path, source_design="d.md", date="2026-05-31"
    )
    for name in ("PBI.md", "PLAN.md", "HISTORY.md"):
        raw = (bundle_dir / name).read_bytes()
        assert b"\r" not in raw, f"{name} contains CR bytes"


def test_v2_finding_carries_the_new_frontmatter_keys(tmp_path: Path) -> None:
    finding = {
        "title": "Refund failure swallowed by a bare except",
        "status": "approved", "slug": "refund-failure-swallowed", "severity": 4,
        "category": "error-masking", "family": "error-masking", "fingerprint": "0123456789abcdef",
        "tier": "A", "type_id": "TD-13", "debt_type": "defect", "effort": "M", "priority": "6.3",
        "body_md": "\n".join([
            "### Proof", "", "p", "", "### Evidence", "", "- `src/pay/refund.py:120-123`", "",
            "```", "    except Exception:", "        pass", "```", "", "### Remediation", "",
            "Re-raise after logging.", "", "### Acceptance criteria", "",
            "- [ ] The failure path re-raises", "- [ ] A regression test covers it",
        ]),
    }
    bundle = write_bundle(finding, out_root=tmp_path, source_design="d.md", date="2026-09-06")
    pbi = (bundle / "PBI.md").read_text(encoding="utf-8")
    for line in ("category: error-masking", "fingerprint: 0123456789abcdef", "tier: A",
                 "type_id: TD-13", "family: error-masking", "debt_type: defect", "effort: M"):
        assert line in pbi, line
    assert "priority:" not in pbi, "priority is not a PBI key"
    assert pbi.index("category:") < pbi.index("fingerprint:"), "v1 keys keep their order first"
    assert "### Acceptance criteria" in pbi and "    except Exception:" in pbi
    plan = (bundle / "PLAN.md").read_text(encoding="utf-8")
    assert "- [ ] 1. The failure path re-raises" in plan
    assert "- [ ] 2. A regression test covers it" in plan
    assert "Address the tech-debt finding" not in plan, "criteria replace the one-step stub"


def test_a_finding_without_acceptance_criteria_keeps_the_one_step_plan(tmp_path: Path) -> None:
    finding = {"title": "T", "status": "approved", "slug": "t", "severity": 3,
               "category": "security", "body_md": "### Proof\n\np"}
    bundle = write_bundle(finding, out_root=tmp_path, source_design="d.md", date="2026-09-06")
    plan = (bundle / "PLAN.md").read_text(encoding="utf-8")
    assert "- [ ] 1. Address the tech-debt finding described in PBI.md." in plan


def test_v1_finding_still_writes_the_v1_golden_bytes(tmp_path: Path) -> None:
    """Spec 8: a v1 design promotes byte-identically."""
    finding = {"title": "Finding 0 title", "status": "approved", "slug": "finding-0",
               "severity": 5, "category": "god-modules",
               "body_md": "### Evidence\n\n- foo\n\n### Suggested fix\n\nbar"}
    bundle = write_bundle(finding, out_root=tmp_path, source_design="d.md", date="2026-05-31")
    for name in ("PBI.md", "PLAN.md", "HISTORY.md"):
        expected = (GOLDEN / "bundle" / "chore-finding-0-2026-05-31" / name).read_bytes()
        assert (bundle / name).read_bytes() == expected, name


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("### Acceptance criteria\n\n- [ ] one\n- [ ] two", ["one", "two"]),
        ("### Acceptance criteria\n\n- [ ] one\n\n# Next section\n\n- [ ] not mine", ["one"]),
        ("### Acceptance criteria\n\nremediation note not available", []),
        ("### Proof\n\np", []),
        ("", []),
    ],
)
def test_acceptance_criteria_parser(body: str, expected: list[str]) -> None:
    from bundle_writer import acceptance_criteria

    assert acceptance_criteria(body) == expected


def test_v2_written_files_byte_match_golden(tmp_path: Path) -> None:
    """The v2 rendered bundle is byte-identical to the canonical v2 golden bundle."""
    finding = {
        "title": "Refund failure swallowed by a bare except",
        "status": "approved", "slug": "refund-failure-swallowed", "severity": 4,
        "category": "error-masking", "family": "error-masking", "fingerprint": "0123456789abcdef",
        "tier": "A", "type_id": "TD-13", "debt_type": "defect", "effort": "M", "priority": "6.3",
        "body_md": "\n".join([
            "### Proof", "", "p", "", "### Evidence", "", "- `src/pay/refund.py:120-123`", "",
            "```", "    except Exception:", "        pass", "```", "", "### Remediation", "",
            "Re-raise after logging.", "", "### Acceptance criteria", "",
            "- [ ] The failure path re-raises", "- [ ] A regression test covers it",
        ]),
    }
    bundle = write_bundle(finding, out_root=tmp_path, source_design="d.md", date="2026-09-06")
    for name in ("PBI.md", "PLAN.md", "HISTORY.md"):
        expected = (
            GOLDEN / "bundle-v2" / "chore-refund-failure-swallowed-2026-09-06" / name
        ).read_bytes()
        assert (bundle / name).read_bytes() == expected, name
