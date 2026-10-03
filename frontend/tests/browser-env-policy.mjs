import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const source = readFileSync(new URL('../vite.config.js', import.meta.url), 'utf8')
  .replace(/^import .*;\r?\n/gm, '').replace('export default defineConfig', 'globalThis.configure = defineConfig');
function configure(env) {
  const context = { process: { cwd: () => '.', env: {} }, defineConfig: value => value, loadEnv: () => env, react: () => ({}), buildReceiptPlugin: () => ({}) };
  vm.runInNewContext(source, context);
  return context.configure({ mode: 'production' });
}
for (const key of ['VITE_GRAPH_READ_TOKEN', 'VITE_APIM_SUBSCRIPTION_KEY', 'REACT_APP_PASSWORD', 'VITE_ADMIN_API_KEY']) {
  assert.throws(() => configure({ [key]: 'test-private-value' }), error => error.message.includes(key) && !error.message.includes('test-private-value'));
}
const safe = configure({ VITE_GRAPH_SERVICE_URL: 'http://example:8013', DEPO_DATABASE_URL: 'server-only' });
assert.ok(!safe.define['process.env'].includes('server-only'));
assert.ok(safe.define['process.env'].includes('http://example:8013'));
console.log('PASS: browser configuration credential policy');

assert.throws(() => configure({VITE_GRAPH_SERVICE_URL: 'http://a:8013', REACT_APP_GRAPH_SERVICE_URL: 'http://b:8013'}), /Conflicting browser settings/);
