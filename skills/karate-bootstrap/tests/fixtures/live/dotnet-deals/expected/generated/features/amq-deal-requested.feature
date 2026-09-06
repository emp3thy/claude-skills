@amq
Feature: amq deal.requested

Background:
  * def uid = java.util.UUID.randomUUID() + ''
  * call read('classpath:common/reset.feature')
  * def base = read('classpath:seed/examples/amq-deal-requested.json')
  * set base.externalId = 'REQ-' + uid

Scenario: a requested message writes a queued deal
  * Jms.publish('deal.requested', base, {})
  * def row = Db.awaitRow('deals', { external_id: base.externalId }, 10000)
  * match row.status == 'QUEUED'
