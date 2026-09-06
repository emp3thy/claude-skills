@smoke
@parallel=false
Feature: POST /api/shipments

Background:
  * def uid = java.util.UUID.randomUUID() + ''
  * call read('classpath:common/reset.feature') { watch: ['shipment.created'], stubs: ['classpath:stubs/pricing/default.json'] }
  * def base = read('classpath:seed/examples/post-api-shipments.json')
  * set base.reference = 'REF-' + uid

Scenario: creates a shipment, writes shipments and publishes shipment.created
  Given url appBaseUrl
  And path '/api/shipments'
  And request base
  When method post
  Then status 201
  And match response contains { reference: '#(base.reference)', status: 'PENDING' }
  * def row = Db.row('shipments', { reference: base.reference })
  * match row.status == 'PENDING'
  * def msg = Jms.await('shipment.created', 10000, { reference: base.reference })
  * match msg.body.status == 'PENDING'
  * Stubs.verify('GET', '/pricing/rates/' + base.countryCode, 1)

@error
Scenario: rejects a shipment over the weight limit
  * set base.weightKg = 1500
  Given url appBaseUrl
  And path '/api/shipments'
  And request base
  When method post
  Then status 400

@rules
Scenario Outline: validation rule <rule_id> on <field>
  * def payload = mutate(base, '<field>', '<mutation>', '<value>')
  Given url appBaseUrl
  And path '/api/shipments'
  And request payload
  When method post
  Then status <expected_status>
  * match checkError(response, '<expected_code>', '<expected_message_contains>') == []

  Examples:
    | karate.filter(read('classpath:rules/post-api-shipments.csv'), function(r){ return r.mutation != 'cross_field' }) |
