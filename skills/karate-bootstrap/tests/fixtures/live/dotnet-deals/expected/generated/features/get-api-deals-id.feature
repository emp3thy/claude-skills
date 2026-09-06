@smoke
@parallel=false
Feature: GET /api/deals/{id}

Background:
  * def uid = java.util.UUID.randomUUID() + ''
  * call read('classpath:common/reset.feature') { stubs: ['classpath:stubs/pricing/default.json'] }
  * def base = read('classpath:seed/examples/post-api-deals.json')
  * set base.externalId = 'EXT-' + uid
  * set base.currency = 'EUR'

Scenario: returns a deal by id
  Given url appBaseUrl
  And path '/api/deals'
  And request base
  When method post
  Then status 201
  * def created = response
  Given url appBaseUrl
  And path '/api/deals/' + created.id
  When method get
  Then status 200
  And match response.externalId == base.externalId

@error
Scenario: returns 404 for an unknown id
  Given url appBaseUrl
  And path '/api/deals/11111111-2222-3333-4444-555555555555'
  When method get
  Then status 404
