@amq
Feature: amq shipment.requested

Background:
  * def uid = java.util.UUID.randomUUID() + ''
  * call read('classpath:common/reset.feature')
  * def base = read('classpath:seed/examples/amq-shipment-requested.json')
  * set base.reference = 'REQ-' + uid

Scenario: a requested message writes a queued shipment
  * Jms.publish('shipment.requested', base, {})
  * def row = Db.awaitRow('shipments', { reference: base.reference }, 10000)
  * match row.status == 'QUEUED'
