import { graphApi } from './graphApi';
import { apiClient } from './apiClient';
vi.mock('./apiClient', () => ({ apiClient: {get: vi.fn()} }));
vi.mock('./serviceAuth', () => ({getServiceAuthToken: () => 'fixture-read'}));
vi.mock('../config', () => ({buildSemanticServiceUrl: (service, path) => `http://${service}.test${path}`}));

test('Processes reads architecture instances rather than a registered ontology projection', () => {
  const signal = new AbortController().signal;
  graphApi.getArchitectureGraph('archimate', 150, signal);
  expect(apiClient.get).toHaveBeenCalledWith('http://graph.test/api/v1/graph/view/architecture/archimate',
    {params:{limit:150}, signal, headers:{Authorization:'Bearer fixture-read'}});
});
