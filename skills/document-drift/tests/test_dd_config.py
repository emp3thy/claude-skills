from __future__ import annotations

from dd_config import CONFIG_FILENAME, DEFAULTS, load_config


def test_load_config_missing_file_gives_defaults(tmp_path):
    cfg, warnings = load_config(tmp_path)
    assert cfg == DEFAULTS
    assert warnings == []
    assert cfg is not DEFAULTS and cfg["exclude"] is not DEFAULTS["exclude"]


def test_load_config_merges_values(tmp_path):
    (tmp_path / CONFIG_FILENAME).write_text(
        "exclude: ['a/**']\nunit_lines: 500\nnever_edit_heading: '(?i)faq'\n", encoding="utf-8"
    )
    cfg, warnings = load_config(tmp_path)
    assert cfg["exclude"] == ["a/**"]
    assert cfg["unit_lines"] == 500
    assert cfg["never_edit_heading"] == "(?i)faq"
    assert cfg["max_delete_lines"] == 15
    assert warnings == []


def test_load_config_unknown_key_warns(tmp_path):
    (tmp_path / CONFIG_FILENAME).write_text("bogus: 1\nunit_lines: 300\n", encoding="utf-8")
    cfg, warnings = load_config(tmp_path)
    assert cfg["unit_lines"] == 300
    assert "bogus" not in cfg
    assert len(warnings) == 1 and "bogus" in warnings[0]


def test_phase_1_keys_are_unknown(tmp_path):
    (tmp_path / CONFIG_FILENAME).write_text("lead_cap: 5\nrecent_change_days: 14\n",
                                            encoding="utf-8")
    cfg, warnings = load_config(tmp_path)
    assert "lead_cap" not in cfg and "recent_change_days" not in cfg
    assert len(warnings) == 2 and all("unknown key" in w for w in warnings)


def test_load_config_wrong_type_warns_and_defaults(tmp_path):
    (tmp_path / CONFIG_FILENAME).write_text(
        "unit_lines: many\nexclude: nope\ncommit_trailers: [1]\nmax_delete_lines: true\n",
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


def test_defaults_include_agentic_keys(tmp_path):
    cfg, warnings = load_config(tmp_path)
    assert warnings == []
    assert cfg["unit_lines"] == 6000
    assert cfg["max_delete_lines"] == 15
    assert cfg["max_section_lines"] == 40
    assert cfg["min_anchor_ratio"] == 0.25
    assert cfg["undocumented_ok"] == []
    assert {k: cfg["caps"][k] for k in ("review", "gaps", "verify")} == {
        "review": 40, "gaps": 15, "verify": 25
    }
    assert {k: cfg["models"][k] for k in ("review", "gap", "verify")} == {
        "review": "sonnet", "gap": "sonnet", "verify": "opus"
    }
    assert cfg["caps"] is not DEFAULTS["caps"] and cfg["models"] is not DEFAULTS["models"]


def test_caps_and_models_are_validated_per_subkey(tmp_path):
    (tmp_path / CONFIG_FILENAME).write_text(
        "caps: {review: x, gaps: 3, bogus: 1}\nmodels: {verify: 3, gap: haiku}\n",
        encoding="utf-8",
    )
    cfg, warnings = load_config(tmp_path)
    assert (cfg["caps"]["review"], cfg["caps"]["gaps"], cfg["caps"]["verify"]) == (40, 3, 25)
    assert (cfg["models"]["review"], cfg["models"]["gap"], cfg["models"]["verify"]) == (
        "sonnet", "haiku", "opus"
    )
    assert len(warnings) == 3
    assert any("caps.review" in w for w in warnings)
    assert any("caps.bogus" in w for w in warnings)
    assert any("models.verify" in w for w in warnings)
    (tmp_path / CONFIG_FILENAME).write_text("caps: nope\n", encoding="utf-8")
    cfg, warnings = load_config(tmp_path)
    assert cfg["caps"] == DEFAULTS["caps"] and len(warnings) == 1


def test_min_anchor_ratio_must_be_between_0_and_1(tmp_path):
    for text, expected, count in [
        ("min_anchor_ratio: 0\n", 0, 0),
        ("min_anchor_ratio: 1\n", 1, 0),
        ("min_anchor_ratio: 0.5\n", 0.5, 0),
        ("min_anchor_ratio: 1.5\n", 0.25, 1),
        ("min_anchor_ratio: -0.1\n", 0.25, 1),
        ("min_anchor_ratio: high\n", 0.25, 1),
        ("min_anchor_ratio: true\n", 0.25, 1),
    ]:
        (tmp_path / CONFIG_FILENAME).write_text(text, encoding="utf-8")
        cfg, warnings = load_config(tmp_path)
        assert cfg["min_anchor_ratio"] == expected, text
        assert len(warnings) == count, text


def test_undocumented_ok_must_be_string_list(tmp_path):
    (tmp_path / CONFIG_FILENAME).write_text("undocumented_ok: ['a.py', 'b/']\n", encoding="utf-8")
    cfg, warnings = load_config(tmp_path)
    assert cfg["undocumented_ok"] == ["a.py", "b/"] and warnings == []
    (tmp_path / CONFIG_FILENAME).write_text("undocumented_ok: [1]\n", encoding="utf-8")
    cfg, warnings = load_config(tmp_path)
    assert cfg["undocumented_ok"] == [] and len(warnings) == 1


def test_defaults_include_phase_b_keys(tmp_path):
    cfg, warnings = load_config(tmp_path)
    assert warnings == []
    assert cfg["readme"] is True
    assert cfg["area_lines"] == 5000
    assert cfg["readme_lines"] == 300
    assert cfg["caps"] == {
        "review": 40, "gaps": 15, "verify": 25, "sheet_agents": 12, "readme_batch": 15
    }
    assert cfg["models"] == {
        "review": "sonnet", "gap": "sonnet", "verify": "opus", "sheet": "sonnet", "readme": "opus"
    }


def test_readme_must_be_bool_and_area_lines_positive(tmp_path):
    (tmp_path / CONFIG_FILENAME).write_text(
        "readme: 'yes'\narea_lines: 0\ncaps: {sheet_agents: x}\n"
        "readme_lines: -1\nmodels: {sheet: ''}\n",
        encoding="utf-8",
    )
    cfg, warnings = load_config(tmp_path)
    assert cfg["readme"] is True
    assert cfg["area_lines"] == 5000
    assert cfg["readme_lines"] == 300
    assert cfg["caps"]["sheet_agents"] == 12 and cfg["caps"]["readme_batch"] == 15
    assert cfg["models"]["sheet"] == "sonnet"
    assert len(warnings) == 5
    (tmp_path / CONFIG_FILENAME).write_text(
        "readme: false\narea_lines: 100\ncaps: {readme_batch: 3}\nmodels: {readme: haiku}\n",
        encoding="utf-8",
    )
    cfg, warnings = load_config(tmp_path)
    assert cfg["readme"] is False and cfg["area_lines"] == 100 and warnings == []
    assert cfg["caps"]["readme_batch"] == 3 and cfg["models"]["readme"] == "haiku"
