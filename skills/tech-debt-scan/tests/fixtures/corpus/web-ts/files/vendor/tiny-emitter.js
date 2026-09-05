// tiny-emitter 2.1.0 (vendored)
function E() {}
E.prototype = { on: function (name, cb) { (this.e || (this.e = {}))[name] = cb; return this; } };
module.exports = E;
