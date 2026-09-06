@harness
Feature: harness self-test that needs no containers

Scenario: mutate helper covers every mutation kind
  * def base = { name: 'abc', qty: 5, kind: 'A' }
  * match mutate(base, 'name', 'missing', '') == { qty: 5, kind: 'A' }
  * match mutate(base, 'name', 'null', '') == { name: null, qty: 5, kind: 'A' }
  * match mutate(base, 'name', 'empty', '') == { name: '', qty: 5, kind: 'A' }
  * match mutate(base, 'name', 'too_long', '4').name == 'xxxx'
  * match mutate(base, 'name', 'too_short', '2').name == 'xx'
  * match mutate(base, 'name', 'invalid_format', '').name == '!!'
  * match mutate(base, 'qty', 'out_of_range', '0').qty == 0
  * match mutate(base, 'kind', 'invalid_enum', '').kind == 'NOT_A_VALUE'
  * match mutate(base, 'qty', 'cross_field', 'gt:limit').qty == 'gt:limit'

Scenario: checkError helper skips empty expectations and reports the rest
  * def body = { code: 'VALIDATION', message: 'reference is required' }
  * match checkError(body, '', '') == []
  * match checkError(body, 'VALIDATION', 'is required') == []
  * match checkError(body, 'OTHER', '') == ['#regex expected error code .*']
  * match checkError(body, '', 'missing text') == ['#regex expected message containing .*']
  * match checkError('plain text body', '', 'text') == []

Scenario: runtime configuration is on the classpath
  * def Runtime = Java.type('kb.harness.KbRuntime')
  * def rt = Runtime.load()
  * match rt.repo() == '#string'
  * match rt.appPort() == '#number'
  * match skipContainers == '#boolean'

Scenario Outline: dynamic outline from csv works: <rule_id>
  * def payload = mutate({ a: 'x', b: 2 }, '<field>', '<mutation>', '<value>')
  * match payload.<field> == <expected>

  Examples:
    | read('classpath:rules/harness-smoke.csv') |

Scenario: reset feature accepts empty arguments without containers
  * def bare = call read('classpath:common/reset.feature')
  * match bare.watch == []
  * def empty = call read('classpath:common/reset.feature') { watch: [], stubs: [] }
  * match empty.stubs == []
