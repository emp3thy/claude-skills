function fn(response, code, message) {
  var body = (typeof response === 'string') ? response : JSON.stringify(response);
  var problems = [];
  if (code && body.indexOf(code) < 0) {
    problems.push('expected error code "' + code + '" in ' + body);
  }
  if (message && body.indexOf(message) < 0) {
    problems.push('expected message containing "' + message + '" in ' + body);
  }
  return problems;
}
