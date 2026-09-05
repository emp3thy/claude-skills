@probe
Feature: probe failure shapes

Scenario: a failing match
  * def x = { a: 1 }
  * match x == { a: 2 }

@known-defect
Scenario: quarantined scenario is removed by the tag filter
  * match 1 == 2

Scenario Outline: outline row <rule_id>
  * match <a> == <b>

  Examples:
    | rule_id | a | b |
    | R1      | 1 | 1 |
    | R2      | 1 | 3 |
