import fs from 'node:fs';
import assert from 'node:assert/strict';
const source = fs.readFileSync('frontend/src/workflows/runTracking.js', 'utf8');
const helper = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
assert.throws(() => helper.requireRunManifest({}), /durable run ID/);
assert.throws(() => helper.requireRunManifest({run_manifest: {run_id: 1}}), /durable run ID/);
for (const status of ['queued', 'running']) {
  const state = helper.governedRunStatus({run_id: 'run-1', status});
  assert.equal(state.status, status); assert.ok(state.progress < 100);
}
assert.equal(helper.governedRunStatus({run_id: 'run-1', status: 'completed'}).progress, 100);
assert.equal(helper.governedRunStatus({run_id: 'run-1', status: 'failed'}).error, true);
assert.equal(helper.readRequestedRunId(helper.pipelineRunLink('id/with space')), 'id/with space');
assert.equal(helper.readRequestedRunId('#/data-flow/%E0'), '');
const events = [];
globalThis.CustomEvent = class { constructor(name, options) { this.type = name; this.detail = options.detail; } };
globalThis.window = { dispatchEvent: event => events.push(event) };
const recoverySource = fs.readFileSync('frontend/src/services/runRecovery.js', 'utf8');
const recovery = await import(`data:text/javascript;base64,${Buffer.from(recoverySource).toString('base64')}`);
recovery.reportRunRecovery({response: {headers: {'x-depo-run-id': 'run-1'}}, config: {url: 'http://agent/api/v1/workflow-runs'}});
assert.deepEqual(events[0].detail, {runId: 'run-1', kind: 'workflow'});
recovery.reportRunRecovery({response: {headers: {'x-depo-run-id': '<invalid>'}}});
assert.equal(events.length, 1);
console.log('PASS: durable IDs, queued state, run links, malformed encoding and error recovery headers.');
