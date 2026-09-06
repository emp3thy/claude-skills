function fn() {
  var skip = karate.properties['kb.skipContainers'] === 'true';
  var config = { skipContainers: skip };
  config.mutate = karate.read('classpath:common/mutate.js');
  config.checkError = karate.read('classpath:common/check-error.js');
  if (!skip) {
    var Containers = Java.type('kb.harness.Containers');
    Containers.start();
    config.appBaseUrl = Containers.appBaseUrl();
    config.Db = Java.type('kb.harness.Db');
    config.Jms = Java.type('kb.harness.Jms');
    config.Stubs = Java.type('kb.harness.Stubs');
    config.Jwt = Java.type('kb.harness.Jwt');
  }
  karate.configure('connectTimeout', 10000);
  karate.configure('readTimeout', 30000);
  return config;
}
