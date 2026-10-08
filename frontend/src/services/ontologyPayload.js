export function dictionaryPayload(body) {
  const payload = body?.data ?? body;
  const keys = ['entities','properties','relationships'];
  if (!payload || typeof payload !== 'object' || Array.isArray(payload) ||
      !keys.some(key => Object.prototype.hasOwnProperty.call(payload,key)) ||
      keys.some(key => Object.prototype.hasOwnProperty.call(payload,key) && (payload[key] == null || typeof payload[key] !== 'object' || Array.isArray(payload[key])))) {
    throw new Error('The service returned an invalid dictionary. Refresh the source or check service versions.');
  }
  return payload;
}
