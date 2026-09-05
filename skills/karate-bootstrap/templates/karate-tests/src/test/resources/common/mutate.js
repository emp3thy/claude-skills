function fn(base, field, mutation, value) {
  var copy = JSON.parse(JSON.stringify(base));
  var v = (value === undefined || value === null) ? '' : String(value);
  var n = parseInt(v, 10);
  switch (mutation) {
    case 'missing':
      delete copy[field];
      break;
    case 'null':
      copy[field] = null;
      break;
    case 'empty':
      copy[field] = '';
      break;
    case 'too_long':
      copy[field] = 'x'.repeat(isNaN(n) ? 1 : n);
      break;
    case 'too_short':
      copy[field] = 'x'.repeat(isNaN(n) || n < 0 ? 0 : n);
      break;
    case 'invalid_format':
      copy[field] = v === '' ? '!!' : v;
      break;
    case 'out_of_range':
      copy[field] = (v !== '' && !isNaN(Number(v))) ? Number(v) : v;
      break;
    case 'invalid_enum':
      copy[field] = v === '' ? 'NOT_A_VALUE' : v;
      break;
    case 'cross_field':
      copy[field] = v;
      break;
    default:
      throw new Error('unknown mutation: ' + mutation);
  }
  return copy;
}
