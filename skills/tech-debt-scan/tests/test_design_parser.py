# skills/tech-debt-scan/tests/test_design_parser.py
from __future__ import annotations

from pathlib import Path

import pytest
from design_parser import (
    DesignParseError,
    parse_design,
)

GOLDEN = Path(__file__).parent / "golden" / "design.md"


def test_parse_golden(tmp_path: Path):
    result = parse_design(GOLDEN)
    assert len(result["findings"]) == 5
    for f in result["findings"]:
        assert f["status"] == "pending"


def test_parse_mixed_statuses(tmp_path: Path):
    src = tmp_path / "design.md"
    text = GOLDEN.read_text()
    text = text.replace("status: pending", "status: approved", 1)
    src.write_text(text)
    result = parse_design(src)
    assert [f["status"] for f in result["findings"]] == [
        "approved", "pending", "pending", "pending", "pending",
    ]


def test_parse_invalid_status(tmp_path: Path):
    src = tmp_path / "design.md"
    src.write_text(GOLDEN.read_text().replace("status: pending", "status: yes", 1))
    with pytest.raises(DesignParseError, match="unknown status"):
        parse_design(src)


def test_parse_empty_status_via_is_not_none(tmp_path: Path):
    src = tmp_path / "design.md"
    src.write_text(GOLDEN.read_text().replace("status: pending", "status: ", 1))
    with pytest.raises(DesignParseError, match="unknown status"):
        parse_design(src)


def test_parse_duplicate_slug(tmp_path: Path):
    src = tmp_path / "design.md"
    src.write_text(GOLDEN.read_text().replace("slug: finding-1", "slug: finding-0"))
    with pytest.raises(DesignParseError, match="duplicate slug"):
        parse_design(src)


def test_parse_missing_yaml_block(tmp_path: Path):
    src = tmp_path / "design.md"
    text = GOLDEN.read_text()
    # delete the first finding's yaml block
    text = text.replace("```yaml\nstatus: pending", "<missing yaml block>")
    src.write_text(text)
    with pytest.raises(DesignParseError, match="no yaml anchor"):
        parse_design(src)


def test_parse_invalid_slug(tmp_path: Path):
    src = tmp_path / "design.md"
    src.write_text(GOLDEN.read_text().replace("slug: finding-0", "slug: Bad Slug"))
    with pytest.raises(DesignParseError, match="invalid slug"):
        parse_design(src)


def test_missing_file():
    with pytest.raises(DesignParseError, match="not found"):
        parse_design(Path("/nope/does-not-exist.md"))


def test_parse_carries_change_profile_fields():
    result = parse_design(GOLDEN)
    f0 = result["findings"][0]
    assert f0["change_size"] in {"S", "M", "L", "XL"}
    assert f0["change_risk"] in {"low", "med", "high"}
    assert f0["disposition"] in {
        "full-repayment", "debt-conversion", "interest-only"
    }
    assert isinstance(f0["confidence"], int)


def test_parse_rejects_missing_change_size(tmp_path: Path):
    text = GOLDEN.read_text(encoding="utf-8").replace(
        "change_size: L\n", "", 1
    )
    bad = tmp_path / "design.md"
    bad.write_text(text, encoding="utf-8")
    with pytest.raises(DesignParseError, match="change_size"):
        parse_design(bad)


def test_parse_rejects_bad_disposition(tmp_path: Path):
    text = GOLDEN.read_text(encoding="utf-8").replace(
        "disposition: full-repayment", "disposition: rewrite", 1
    )
    bad = tmp_path / "design.md"
    bad.write_text(text, encoding="utf-8")
    with pytest.raises(DesignParseError, match="disposition"):
        parse_design(bad)


def test_parse_rejects_non_int_confidence(tmp_path: Path):
    text = GOLDEN.read_text(encoding="utf-8").replace(
        "confidence: 5\n", "confidence: high\n", 1
    )
    bad = tmp_path / "design.md"
    bad.write_text(text, encoding="utf-8")
    with pytest.raises(DesignParseError, match="confidence"):
        parse_design(bad)


def test_parse_rejects_out_of_range_confidence(tmp_path: Path):
    text = GOLDEN.read_text(encoding="utf-8").replace(
        "confidence: 5\n", "confidence: 7\n", 1
    )
    bad = tmp_path / "design.md"
    bad.write_text(text, encoding="utf-8")
    with pytest.raises(DesignParseError, match="confidence"):
        parse_design(bad)
