@ignore
Feature: per-scenario setup shared by every generated feature

  Called as: call read('classpath:common/reset.feature') { watch: ['deal.created'], seed: 'classpath:seed/x.sql' }
  Arguments, applied in this order: watch (destinations to subscribe before the request),
  truncate (tables), seed (additive SQL, parallel-safe) and stubs (mapping documents to import),
  so a truncate never wipes the rows the same call just seeded. stubs and truncate mutate shared
  state, so the calling scenario must carry @parallel=false (design spec 5.6).

Scenario:
  * def args = __arg || {}
  * def watch = args.watch || []
  * def stubs = args.stubs || []
  * karate.forEach(watch, function(d){ Jms.watch(d) })
  * eval if (args.truncate) Db.truncate(args.truncate)
  * eval if (args.seed) Db.run(args.seed)
  * karate.forEach(stubs, function(p){ Stubs.load(p) })
