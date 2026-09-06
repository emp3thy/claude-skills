# skills/tech-debt-scan/tests/test_design_parser.py
from __future__ import annotations

from pathlib import Path

import pytest
from design_parser import (
    DesignParseError,
    parse_design,
)

# design-v1.md is the v1 compatibility document (spec 8), not the v2 golden Task 7 adds.
GOLDEN = Path(__file__).parent / "golden" / "design-v1.md"


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


def test_parse_passes_through_classification_fields(tmp_path: Path):
    src = tmp_path / "design.md"
    text = GOLDEN.read_text()
    text = text.replace(
        "category: god-modules",
        "category: god-modules\ndebt_type: design\neffort: M\nconfidence: high",
        1,
    )
    src.write_text(text)
    result = parse_design(src)
    first, second = result["findings"][0], result["findings"][1]
    assert first["debt_type"] == "design"
    assert first["effort"] == "M"
    assert first["confidence"] == "high"
    # older-style findings without the fields simply omit them
    assert "debt_type" not in second


def test_a_finding_section_ends_at_an_h1(tmp_path: Path) -> None:
    """Spec 4.11: negative-space sections must never land in a finding's body (and its PBI)."""
    path = tmp_path / "design.md"
    path.write_bytes(
        "\n".join([
            "## Only finding",
            "",
            "```yaml",
            "status: pending",
            "slug: only-finding",
            "severity: 3",
            "category: error-masking",
            "```",
            "",
            "### Proof",
            "",
            "the body",
            "",
            "# Considered and rejected",
            "",
            "- not part of the body",
            "",
        ]).encode("utf-8")
    )
    parsed = parse_design(path)
    assert len(parsed["findings"]) == 1
    body = parsed["findings"][0]["body_md"]
    assert "the body" in body
    assert "Considered and rejected" not in body
    assert "not part of the body" not in body


def test_v2_optional_anchor_keys_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "design.md"
    path.write_bytes(
        "\n".join([
            "## A finding",
            "",
            "```yaml",
            "status: accepted",
            "slug: a-finding",
            "severity: 4",
            "category: security",
            "family: security",
            "fingerprint: 0123456789abcdef",
            "tier: B",
            "priority: 3.5",
            "debt_type: security",
            "type_id: TD-03",
            "effort: S",
            "diff: NEW",
            "reason: accepted until the rewrite",
            "until: 2027-01-31",
            "```",
            "",
            "body",
            "",
        ]).encode("utf-8")
    )
    finding = parse_design(path)["findings"][0]
    assert finding["status"] == "accepted"
    for key, value in {
        "family": "security", "fingerprint": "0123456789abcdef", "tier": "B", "priority": "3.5",
        "debt_type": "security", "type_id": "TD-03", "effort": "S", "diff": "NEW",
        "reason": "accepted until the rewrite", "until": "2027-01-31",
    }.items():
        assert finding[key] == value, key


def test_a_v1_confidence_value_is_parsed_and_kept_for_the_writer_to_discard(tmp_path: Path) -> None:
    path = tmp_path / "design.md"
    path.write_bytes(
        "\n".join([
            "## V1 finding", "", "```yaml", "status: pending", "slug: v1-finding",
            "severity: 2", "category: god-modules", "confidence: high", "```", "", "body", "",
        ]).encode("utf-8")
    )
    assert parse_design(path)["findings"][0]["confidence"] == "high"


def test_an_evidence_fence_starting_with_a_comment_does_not_end_the_section(tmp_path: Path) -> None:
    """A ``# `` comment line inside a fenced block must not be mistaken for an H1 boundary."""
    path = tmp_path / "design.md"
    path.write_bytes(
        "\n".join([
            "## Fence finding",
            "",
            "```yaml",
            "status: pending",
            "slug: fence-finding",
            "severity: 3",
            "category: error-masking",
            "```",
            "",
            "### Evidence",
            "",
            "```",
            "# TODO(#42): delete once finance moves to the v2 report",
            "```",
            "",
            "### Signals",
            "",
            "a signal line",
            "",
            "# Not assessed",
            "",
            "- not part of the body",
            "",
        ]).encode("utf-8")
    )
    parsed = parse_design(path)
    assert len(parsed["findings"]) == 1
    body = parsed["findings"][0]["body_md"]
    assert "# TODO(#42): delete once finance moves to the v2 report" in body
    assert "### Signals" in body
    assert "Not assessed" not in body


def test_a_hand_edited_code_block_with_a_comment_survives(tmp_path: Path) -> None:
    """The reviewer's case: a hand-edited ```python fence with a leading comment line."""
    path = tmp_path / "design.md"
    path.write_bytes(
        "\n".join([
            "## Broken function finding",
            "",
            "```yaml",
            "status: pending",
            "slug: broken-function-finding",
            "severity: 3",
            "category: error-masking",
            "```",
            "",
            "### Evidence",
            "",
            "```python",
            "# this is a comment explaining the bug",
            "def broken():",
            "    pass",
            "```",
            "",
            "### Suggested fix",
            "",
            "do the thing",
            "",
        ]).encode("utf-8")
    )
    parsed = parse_design(path)
    assert len(parsed["findings"]) == 1
    body = parsed["findings"][0]["body_md"]
    assert "# this is a comment explaining the bug" in body
    assert "def broken():" in body
    assert "    pass" in body
    assert "### Suggested fix" in body
