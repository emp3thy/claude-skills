@smoke
@parallel=false
Feature: POST /api/orders

Background:
  * def uid = java.util.UUID.randomUUID() + ''
  * call read('classpath:common/reset.feature') { watch: ['order.created'], stubs: ['classpath:stubs/inventory/default.json'] }
  * def base = read('classpath:seed/examples/post-api-orders.json')
  * set base.reference = 'REF-' + uid

Scenario: creates an order, writes orders and publishes order.created
  Given url appBaseUrl
  And path '/api/orders'
  And request base
  When method post
  Then status 201
  And match response contains { reference: '#(base.reference)', status: 'PENDING' }
  * def row = Db.row('orders', { reference: base.reference })
  * match row.status == 'PENDING'
  * def msg = Jms.await('order.created', 10000, { reference: base.reference })
  * match msg.body.status == 'PENDING'
  * Stubs.verify('GET', '/stock/' + base.sku, 1)

@error
Scenario: rejects an order over the quantity limit
  * set base.quantity = 501
  Given url appBaseUrl
  And path '/api/orders'
  And request base
  When method post
  Then status 422

@rules
Scenario Outline: validation rule <rule_id> on <field>
  * def payload = mutate(base, '<field>', '<mutation>', '<value>')
  Given url appBaseUrl
  And path '/api/orders'
  And request payload
  When method post
  Then status <expected_status>
  * match checkError(response, '<expected_code>', '<expected_message_contains>') == []

  Examples:
    | karate.filter(read('classpath:rules/post-api-orders.csv'), function(r){ return r.mutation != 'cross_field' }) |
