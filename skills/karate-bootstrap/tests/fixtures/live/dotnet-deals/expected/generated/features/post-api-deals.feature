@smoke
@parallel=false
Feature: POST /api/deals

Background:
  * def uid = java.util.UUID.randomUUID() + ''
  * call read('classpath:common/reset.feature') { watch: ['deal.created'], stubs: ['classpath:stubs/pricing/default.json'] }
  * def base = read('classpath:seed/examples/post-api-deals.json')
  * set base.externalId = 'EXT-' + uid

Scenario: creates a deal, writes deals and publishes deal.created
  Given url appBaseUrl
  And path '/api/deals'
  And request base
  When method post
  Then status 201
  And match response contains { externalId: '#(base.externalId)', status: 'PENDING' }
  * def row = Db.row('deals', { external_id: base.externalId })
  * match row.status == 'PENDING'
  * def msg = Jms.await('deal.created', 10000, { externalId: base.externalId })
  * match msg.body.status == 'PENDING'
  * Stubs.verify('GET', '/pricing/quotes/' + base.currency, 1)

@error
Scenario: rejects a deal over the quantity limit
  * set base.quantity = 15000
  Given url appBaseUrl
  And path '/api/deals'
  And request base
  When method post
  Then status 400

@rules
Scenario Outline: validation rule <rule_id> on <field>
  * def payload = mutate(base, '<field>', '<mutation>', '<value>')
  Given url appBaseUrl
  And path '/api/deals'
  And request payload
  When method post
  Then status <expected_status>
  * match checkError(response, '<expected_code>', '<expected_message_contains>') == []

  Examples:
    | karate.filter(read('classpath:rules/post-api-deals.csv'), function(r){ return r.mutation != 'cross_field' }) |
