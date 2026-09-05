@ignore
Feature: per-scenario setup shared by every generated feature

  Called as: call read('classpath:common/reset.feature') { watch: ['deal.created'], seed: 'classpath:seed/x.sql' }
  Arguments: watch (destinations to subscribe before the request), seed (additive SQL, parallel-safe),
  stubs (mapping documents to import) and truncate (tables). stubs and truncate mutate shared state,
  so the calling scenario must carry @parallel=false (design spec 5.6).

Scenario:
  * def args = __arg || {}
  * def watch = args.watch || []
  * def stubs = args.stubs || []
  * karate.forEach(watch, function(d){ Jms.watch(d) })
  * eval if (args.seed) Db.run(args.seed)
  * karate.forEach(stubs, function(p){ Stubs.load(p) })
  * eval if (args.truncate) Db.truncate(args.truncate)
