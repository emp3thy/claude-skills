from __future__ import annotations

from pathlib import Path

import pytest
from config import DEFAULTS, ConfigError, deep_merge, enabled_families, load_config


def test_defaults_load_without_a_file(tmp_path: Path) -> None:
    cfg = load_config(tmp_path)
    assert cfg == DEFAULTS
    assert cfg is not DEFAULTS
    assert cfg["churn_months"] == 12
    assert cfg["coupling"] == {"min_shared": 3, "min_ratio": 0.30, "bulk_threshold": 50}
    assert cfg["hotspot_band"] == {"fraction": 0.10, "min": 5, "max": 50}
    assert cfg["fan_in"]["stoplist"] == [
        "utils", "config", "index", "main", "types", "common", "base", "core", "helpers", "models",
    ]
    assert cfg["rules"]["ownership"]["island_share"] == 0.8
    assert cfg["families"]["enabled"] == "default"


def test_defaults_are_not_mutated_by_a_caller(tmp_path: Path) -> None:
    cfg = load_config(tmp_path)
    cfg["fan_in"]["stoplist"].append("zzz")
    assert "zzz" not in DEFAULTS["fan_in"]["stoplist"]


def test_partial_file_merges_over_defaults(tmp_path: Path) -> None:
    (tmp_path / ".tech-debt.yaml").write_text(
        "churn_months: 6\ncoupling:\n  min_shared: 5\nbot_authors: [robot]\n", encoding="utf-8"
    )
    cfg = load_config(tmp_path)
    assert cfg["churn_months"] == 6
    assert cfg["coupling"]["min_shared"] == 5
    assert cfg["coupling"]["min_ratio"] == 0.30
    assert cfg["coupling"]["bulk_threshold"] == 50
    assert cfg["bot_authors"] == ["robot"]
    assert cfg["hotspot_band"]["max"] == 50


def test_unknown_top_level_key_is_reported_with_line_and_ignored(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".tech-debt.yaml").write_text(
        "churn_months: 6\nbogus_key: 1\ncoupling:\n  min_shared: 4\n", encoding="utf-8"
    )
    cfg = load_config(tmp_path)
    assert "bogus_key" not in cfg
    assert cfg["coupling"]["min_shared"] == 4
    err = capsys.readouterr().err
    assert ".tech-debt.yaml" in err
    assert "line 2" in err
    assert "bogus_key" in err


@pytest.mark.parametrize(
    ("enabled", "expected_first", "expected_len"),
    [
        ("default", "complex-units", 12),
        ("quick", "complex-units", 6),
        ("deep", "complex-units", 14),
        (["security", "dead-code"], "security", 2),
    ],
)
def test_families_enabled_accepts_four_forms(
    tmp_path: Path, enabled: str | list[str], expected_first: str, expected_len: int
) -> None:
    import yaml

    (tmp_path / ".tech-debt.yaml").write_text(
        yaml.safe_dump({"families": {"enabled": enabled}}), encoding="utf-8"
    )
    cfg = load_config(tmp_path)
    fams = enabled_families(cfg)
    assert fams[0] == expected_first
    assert len(fams) == expected_len


def test_unknown_family_set_name_raises(tmp_path: Path) -> None:
    (tmp_path / ".tech-debt.yaml").write_text("families:\n  enabled: turbo\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="turbo"):
        enabled_families(load_config(tmp_path))


def test_non_mapping_root_raises(tmp_path: Path) -> None:
    (tmp_path / ".tech-debt.yaml").write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="mapping"):
        load_config(tmp_path)


def test_empty_file_gives_defaults(tmp_path: Path) -> None:
    (tmp_path / ".tech-debt.yaml").write_text("", encoding="utf-8")
    assert load_config(tmp_path) == DEFAULTS


def test_deep_merge_replaces_lists_and_recurses_into_dicts() -> None:
    merged = deep_merge({"a": {"b": 1, "c": [1]}, "d": 2}, {"a": {"c": [9]}, "d": 3})
    assert merged == {"a": {"b": 1, "c": [9]}, "d": 3}
