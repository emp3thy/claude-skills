@smoke
Feature: GET /healthz

Background:
  * call read('classpath:common/reset.feature')

Scenario: readiness endpoint reports ok
  Given url appBaseUrl
  And path '/healthz'
  When method get
  Then status 200
  And match response == { status: 'ok' }
