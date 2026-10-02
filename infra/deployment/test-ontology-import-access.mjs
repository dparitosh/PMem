import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync('frontend/src/Components/DataImportPipeline.js', 'utf8');
const start = source.indexOf('  const startOntologyRegistration = async');
const end = source.indexOf('  // Map file extension', start);
const functionSource = source.slice(start, end).trim().replace(/^const startOntologyRegistration = /, '').replace(/;$/, '');
const file = { fileId: 'one', fileObj: {}, fileType: 'xsd', ontologyName: 'Example', prefix: 'example', generationType: 'owl' };
async function execute({ publish = false, response, key = 'write-key' } = {}) {
  let statuses = {}, error = '', request;
  const context = {
    ingestionWriteToken: key, publishOntology: publish, FormData, getCredentialProfile: () => '',
    API_METHODS: { ontology: { upload: async (...args) => { request = args; return { data: { task_id: 'saved', ontology_id: 'saved' } }; } } },
    apiClient: { post: async (...args) => { request = args; return { data: response }; } },
    buildSemanticServiceUrl: (service, path) => `http://ingestion${path}`,
    setError: value => { error = value; },
    setStartedFiles: () => {}, setFiles: () => {},
    setPipelineStatus: updater => { statuses = updater(statuses); },
    setMetadataFormPrefill: () => {}, setPendingFileForMetadata: () => {},
    setPendingMetadataFileId: () => {}, setShowMetadataForm: () => {},
  };
  await vm.runInNewContext(`(${functionSource})`, context)(file);
  return { status: statuses.one, error, request };
}
const saved = await execute();
assert.equal(saved.status.committed, false);
assert.equal(saved.status.registered, true);
assert.equal(saved.request[2], 'write-key');
const published = await execute({ publish: true, response: { status: 'published', ontology_registration: { ontology_id: 'registered' }, graph_publication: { publication_id: 'receipt' } } });
assert.equal(published.status.published, true);
assert.equal(published.request[2].headers.Authorization, 'Bearer write-key');
assert.equal(published.request[1].get('publish'), 'true');
const blocked = await execute({ publish: true, response: { status: 'quality_blocked', message: 'Quality failed' } });
assert.equal(blocked.status.error, true);
assert.match(blocked.error, /Quality failed/);
assert.equal((await execute({ key: '' })).request, undefined);

const shell = fs.readFileSync('frontend/src/app/AppShell.js', 'utf8');
const handler = shell.slice(shell.indexOf('onSubmit={async (event) => {') + 'onSubmit={'.length, shell.indexOf('\n                }}', shell.indexOf('onSubmit={async (event) => {')) + '\n                }'.length);
for (const rejects of [false, true]) {
  let configured = false, refresh = 0, failure = '';
  const context = {
    accessBusy: false, apiKey: 'read-key', subscriptionKey: '', getServiceAuthToken: () => '', getGatewaySubscriptionKey: () => '',
    setAccessBusy: () => {}, setAccessError: value => { failure = value; },
    setServiceAuthToken: () => {}, setGatewaySubscriptionKey: () => {}, clearServiceAuthToken: () => {},
    graphApi: { getOverview: async () => { if (rejects) throw { response: { status: 403 } }; } },
    setApiAccessConfigured: value => { configured = value; }, setShowApiAccess: () => {},
    onServiceAuthChange: () => { refresh++; },
  };
  await vm.runInNewContext(`(${handler})`, context)({ preventDefault() {} });
  assert.equal(configured, !rejects);
  assert.equal(refresh, rejects ? 0 : 1);
  if (rejects) assert.match(failure, /Graph access rejected/);
}
console.log('PASS: actual ontology upload/publication and API access handlers (mocked transports).');
