// Display metadata only: imported servers never change routing or credentials.
export function openApiPreview(document, filename = '') {
  if (!document || typeof document !== 'object' || Array.isArray(document) ||
      !/^3\.[01]\./.test(document.openapi || '') || !document.paths ||
      typeof document.paths !== 'object' || Array.isArray(document.paths)) {
    throw new Error('Select an OpenAPI 3.0 or 3.1 JSON document with a paths object.');
  }
  const methods = new Set(['get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'trace']);
  const operations = [];
  for (const [path, item] of Object.entries(document.paths)) {
    if (!path.startsWith('/') || !item || typeof item !== 'object') continue;
    for (const [method, operation] of Object.entries(item)) {
      if (!methods.has(method) || !operation || typeof operation !== 'object' || Array.isArray(operation)) continue;
      operations.push({ method: method.toUpperCase(), path, operation_id: String(operation.operationId || ''), summary: String(operation.summary || '') });
      if (operations.length > 10000) throw new Error('OpenAPI preview exceeds 10,000 operations.');
    }
  }
  return { title: String(document.info?.title || filename || 'OpenAPI contract'),
    summary: { operations: operations.length, schemas: Object.keys(document.components?.schemas || {}).length }, operations };
}
