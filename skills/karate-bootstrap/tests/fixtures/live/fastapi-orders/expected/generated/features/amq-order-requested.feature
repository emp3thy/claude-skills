@amq
Feature: amq order.requested

Background:
  * def uid = java.util.UUID.randomUUID() + ''
  * call read('classpath:common/reset.feature')
  * def base = read('classpath:seed/examples/amq-order-requested.json')
  * set base.reference = 'REQ-' + uid

Scenario: a requested message writes a queued order
  * Jms.publish('order.requested', base, {})
  * def row = Db.awaitRow('orders', { reference: base.reference }, 10000)
  * match row.status == 'QUEUED'
