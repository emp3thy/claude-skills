from __future__ import annotations

from kb_features import (
    KNOWN_DEFECT_TAG,
    PARALLEL_FALSE_TAG,
    known_defect_scenario_count,
    parse_feature,
    unsafe_parallel_scenarios,
)

FEATURE = """@smoke @amq
Feature: POST /api/deals

Background:
  * def uid = java.util.UUID.randomUUID() + ''
  * call read('classpath:common/reset.feature') { watch: ['deal.created'] }

Scenario: creates a deal
  Given url appBaseUrl
  When method post
  Then status 201

@error @parallel=false
Scenario: pricing outage returns 503
  * Stubs.load('classpath:stubs/pricing/outage.json')
  Then status 503
  * Stubs.reset()

@error
Scenario: stale reset without the tag
  * Stubs.reset()

@known-defect
Scenario: quarantined
  Then status 500

@rules
Scenario Outline: validation rule <rule_id> on <field>
  Then status <expected_status>

  Examples:
    | read('classpath:rules/post-api-deals.csv') |
"""


def test_parse_feature_splits_tags_background_and_blocks() -> None:
    parsed = parse_feature(FEATURE)
    assert parsed.tags == {"@smoke", "@amq"}
    assert [b.kind for b in parsed.blocks] == [
        "Background", "Scenario", "Scenario", "Scenario", "Scenario", "Scenario Outline",
    ]
    names = [b.name for b in parsed.scenarios()]
    assert names == ["creates a deal", "pricing outage returns 503", "stale reset without the tag",
                     "quarantined", "validation rule <rule_id> on <field>"]
    outage = parsed.scenarios()[1]
    assert outage.tags == {"@error", PARALLEL_FALSE_TAG}
    assert parsed.effective_tags(outage) == {"@smoke", "@amq", "@error", PARALLEL_FALSE_TAG}
    assert "Stubs.load('classpath:stubs/pricing/outage.json')" in outage.text()
    assert "reset.feature" in parsed.background_text()


def test_unsafe_parallel_scenarios_names_untagged_exclusive_calls_only() -> None:
    assert unsafe_parallel_scenarios(FEATURE) == ["stale reset without the tag"]


def test_unsafe_parallel_scenarios_blames_every_scenario_for_an_unsafe_background() -> None:
    text = (
        "Feature: x\n\nBackground:\n"
        "  * call read('classpath:common/reset.feature') { truncate: ['deals'] }\n\n"
        "Scenario: a\n  Then status 200\n\n@parallel=false\nScenario: b\n  Then status 200\n"
    )
    assert unsafe_parallel_scenarios(text) == ["a"]
    tagged = "@parallel=false\n" + text
    assert unsafe_parallel_scenarios(tagged) == []


def test_unsafe_parallel_scenarios_ignores_data_only_features() -> None:
    text = "Feature: y\n\nScenario: read\n  * def row = Db.row('deals', { id: uid })\n"
    assert unsafe_parallel_scenarios(text) == []


def test_known_defect_scenario_count_counts_scenario_and_feature_tags() -> None:
    assert KNOWN_DEFECT_TAG == "@known-defect"
    assert known_defect_scenario_count(FEATURE) == 1
    assert known_defect_scenario_count("@known-defect\nFeature: z\n\nScenario: a\n\n"
                                       "Scenario Outline: b\n") == 2
    assert known_defect_scenario_count("Feature: clean\n\nScenario: a\n") == 0
