from __future__ import annotations

from dd_config import CONFIG_FILENAME, DEFAULTS, load_config


def test_load_config_missing_file_gives_defaults(tmp_path):
    cfg, warnings = load_config(tmp_path)
    assert cfg == DEFAULTS
    assert warnings == []
    assert cfg is not DEFAULTS and cfg["exclude"] is not DEFAULTS["exclude"]


def test_load_config_merges_values(tmp_path):
    (tmp_path / CONFIG_FILENAME).write_text(
        "exclude: ['a/**']\nlead_cap: 5\nnever_edit_heading: '(?i)faq'\n", encoding="utf-8"
    )
    cfg, warnings = load_config(tmp_path)
    assert cfg["exclude"] == ["a/**"]
    assert cfg["lead_cap"] == 5
    assert cfg["never_edit_heading"] == "(?i)faq"
    assert cfg["recent_change_days"] == 14
    assert warnings == []


def test_load_config_unknown_key_warns(tmp_path):
    (tmp_path / CONFIG_FILENAME).write_text("bogus: 1\nlead_cap: 3\n", encoding="utf-8")
    cfg, warnings = load_config(tmp_path)
    assert cfg["lead_cap"] == 3
    assert "bogus" not in cfg
    assert len(warnings) == 1 and "bogus" in warnings[0]


def test_load_config_wrong_type_warns_and_defaults(tmp_path):
    (tmp_path / CONFIG_FILENAME).write_text(
        "lead_cap: many\nexclude: nope\ncommit_trailers: [1]\nrecent_change_days: true\n",
        encoding="utf-8",
    )
    cfg, warnings = load_config(tmp_path)
    assert cfg == DEFAULTS
    assert len(warnings) == 4


def test_load_config_invalid_yaml_or_regex_warns(tmp_path):
    (tmp_path / CONFIG_FILENAME).write_text("a: [unclosed\n", encoding="utf-8")
    cfg, warnings = load_config(tmp_path)
    assert cfg == DEFAULTS and len(warnings) == 1
    (tmp_path / CONFIG_FILENAME).write_text("never_edit_heading: '('\n", encoding="utf-8")
    cfg, warnings = load_config(tmp_path)
    assert cfg["never_edit_heading"] is None and len(warnings) == 1


def test_load_config_non_mapping_warns(tmp_path):
    (tmp_path / CONFIG_FILENAME).write_text("- a\n- b\n", encoding="utf-8")
    cfg, warnings = load_config(tmp_path)
    assert cfg == DEFAULTS and len(warnings) == 1
