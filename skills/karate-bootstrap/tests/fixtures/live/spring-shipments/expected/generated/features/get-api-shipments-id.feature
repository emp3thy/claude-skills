@smoke
@parallel=false
Feature: GET /api/shipments/{id}

Background:
  * def uid = java.util.UUID.randomUUID() + ''
  * call read('classpath:common/reset.feature') { stubs: ['classpath:stubs/pricing/default.json'] }
  * def base = read('classpath:seed/examples/post-api-shipments.json')
  * set base.reference = 'REF-' + uid
  * set base.countryCode = 'FR'

Scenario: returns a shipment by id
  Given url appBaseUrl
  And path '/api/shipments'
  And request base
  When method post
  Then status 201
  * def created = response
  Given url appBaseUrl
  And path '/api/shipments/' + created.id
  When method get
  Then status 200
  And match response.reference == base.reference

@error
Scenario: returns 404 for an unknown id
  Given url appBaseUrl
  And path '/api/shipments/11111111-2222-3333-4444-555555555555'
  When method get
  Then status 404
