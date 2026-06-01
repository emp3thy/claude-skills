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
