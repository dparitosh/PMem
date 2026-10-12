import { setCredentialProfile } from '../services/serviceAuth';
import React from 'react';
import { act } from 'react';
import { vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import DataImportPipeline from './DataImportPipeline';
import { apiClient, API_METHODS } from '../services/apiClient';

const mockOntologyContextValue = {
  ontologies: [],
};

vi.mock('../config', () => ({
  API: {
    import: {
      upload: '/api/v1/import/upload',
      status: '/api/v1/import/{task_id}/status',
      preview: '/api/v1/import/{task_id}/preview',
      preCommit: '/api/v1/import/{task_id}/pre-commit',
      commit: '/api/v1/import/{task_id}/commit',
      cancel: '/api/v1/import/{task_id}/cancel',
      owlExport: '/api/v1/import/{task_id}/export',
    },
    workflow: {
      options: '/api/v1/workflow/options',
      execute: '/api/v1/workflow/execute',
      artifactFile: '/api/v1/workflow/{task_id}/artifact/{artifact_path}',
    },
    ontology: {
      registered: '/api/v1/ontology/registered',
      upload: '/api/v1/ontology/upload',
      merge: '/api/v1/ontology/merge',
    },
  },
  config: { semanticServiceUrls: {}, gatewayUrl: '' },
  buildSemanticServiceUrl: (service, path) => path,
  buildUrl: (value) => value,
  replaceParams: (endpoint, params = {}) => Object.keys(params).reduce((result, key) => result.replace(`{${key}}`, params[key]), endpoint),
}));

vi.mock('../contexts/OntologyContext', () => ({
  useOntologies: () => mockOntologyContextValue,
}));

const mockListRegistered = jest.fn();
const mockWorkflowOptions = jest.fn();
const mockOntologyUpload = jest.fn();
const flushAsyncEffects = () => new Promise((resolve) => setTimeout(resolve, 0));

const renderPipeline = async () => {
  let result;
  await act(async () => {
    result = render(<DataImportPipeline />);
    await flushAsyncEffects();
  });
  return result;
};

vi.mock('../services/apiClient', () => ({
  dataPipelineAPI: { getRun: vi.fn() },
  API_METHODS: {
    ontology: {
      listRegistered: (...args) => mockListRegistered(...args),
      upload: (...args) => mockOntologyUpload(...args),
      merge: jest.fn(),
    },
    workflow: {
      getOptions: (...args) => mockWorkflowOptions(...args),
      execute: jest.fn(),
      artifactUrl: jest.fn(),
    },
    import: {
      exportOWL: jest.fn(),
    },
    document: { submitJob: jest.fn(), getJob: jest.fn() },
  },
  apiClient: {
    get: jest.fn(),
    post: jest.fn(),
  },
}));

describe('DataImportPipeline workflow routing', () => {
  let consoleErrorSpy;

  beforeAll(() => {
    consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation((...args) => {
      const message = String(args[0] || '');
      if (message.includes('ReactDOMTestUtils.act` is deprecated')) {
        return;
      }
      // eslint-disable-next-line no-console
      console.warn(...args);
    });
  });

  afterAll(() => {
    consoleErrorSpy?.mockRestore();
  });

  beforeEach(() => {
    mockListRegistered.mockResolvedValue({ data: { ontologies: [] } });
    mockWorkflowOptions.mockResolvedValue({ data: { workflows: [] } });
    mockOntologyUpload.mockReset();
    window.localStorage.clear();
  });

  it('auto-routes XSD files from instance import into ontology registration and shows the filename', async () => {
    await renderPipeline();

    const input = document.querySelector('input[type="file"]');
    const file = new File(['schema'], 'bom.xsd', { type: 'application/xml' });

    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
      await flushAsyncEffects();
    });

    await waitFor(() => {
      expect(screen.getByText(/Ontology Metadata/i)).toBeInTheDocument();
    });

    expect(screen.queryByText(/Import instance graph only accepts source data files/i)).not.toBeInTheDocument();
    expect(screen.getAllByText('bom.xsd').length).toBeGreaterThan(0);
  });

  it('auto-routes CSV files from ontology workflow back into instance import and shows the filename', async () => {
    await renderPipeline();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Create ontology/i }));
    });

    const input = document.querySelector('input[type="file"]');
    const file = new File(['a,b\n1,2'], 'parts.csv', { type: 'text/csv' });

    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
      await flushAsyncEffects();
    });

    await waitFor(() => {
      expect(screen.getAllByText('parts.csv').length).toBeGreaterThan(0);
    });

    expect(screen.queryByText(/Create ontology only accepts ontology or schema sources/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Ontology Metadata/i)).not.toBeInTheDocument();
  });

  it('saves ontology details, closes the popup, and waits for Start before uploading', async () => {
    mockOntologyUpload.mockResolvedValue({
      data: {
        task_id: 'task-1',
        ontology_id: 'ontology-1',
        source_namespace: 'http://example.com/bom',
        base_uri: 'http://example.com/bom#',
      },
    });

    await renderPipeline();
    // This case intentionally tests source-only SHACL registration.
    fireEvent.click(screen.getByLabelText(/Register XSD/));

    const input = document.querySelector('input[type="file"]');
    const file = new File(['schema'], 'bom.xsd', { type: 'application/xml' });

    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
      await flushAsyncEffects();
    });

    await waitFor(() => {
      expect(screen.getByText(/Ontology Metadata/i)).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.change(screen.getByPlaceholderText(/e.g., Product Model/i), { target: { value: 'BOM Ontology' } });
      fireEvent.change(screen.getByPlaceholderText(/e.g., myprefix/i), { target: { value: 'bom' } });
      fireEvent.change(screen.getByRole('combobox'), { target: { value: 'shacl' } });
      fireEvent.click(screen.getByRole('button', { name: /Upload and Parse/i }));
      await flushAsyncEffects();
    });

    await waitFor(() => {
      expect(screen.queryByText(/Ontology Metadata/i)).not.toBeInTheDocument();
    });

    expect(mockOntologyUpload).not.toHaveBeenCalled();
    expect(screen.getByText(/Metadata saved for 'BOM Ontology'. Click Start to register ontology./i)).toBeInTheDocument();

    setCredentialProfile('INGESTION_WRITE_TOKEN', 'fixture-write');
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /^Start$/i }));
      await flushAsyncEffects();
    });

    await waitFor(() => {
      expect(mockOntologyUpload).toHaveBeenCalledTimes(1);
    });

    expect(mockOntologyUpload).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'bom.xsd' }),
      expect.objectContaining({
        ontologyName: 'BOM Ontology',
        prefix: 'bom',
        generationType: 'shacl',
      }),
      'fixture-write'
    );
  });

  it('defaults to Neo4j publication and makes register-only behavior explicit', async () => {
    await renderPipeline();
    const publication = screen.getByLabelText(/Register XSD/);
    expect(publication).toBeChecked();
    expect(screen.getByText(/Publication is confirmed only by a graph receipt/)).toBeInTheDocument();
    fireEvent.click(publication);
    expect(publication).not.toBeChecked();
    expect(screen.getByText(/Register only: the source is retained, but Neo4j is not updated/)).toBeInTheDocument();
  });

  it('offers only OWL generation when schema publication is enabled', async () => {
    await renderPipeline();
    const input = document.querySelector('input[type="file"]');
    await act(async () => {
      fireEvent.change(input, { target: { files: [new File(['schema'], 'demo.xsd', { type: 'application/xml' })] } });
      await flushAsyncEffects();
    });
    const select = document.getElementById('ontology-generation-select');
    expect(select).toHaveValue('owl');
    expect(Array.from(select.options).map(option => option.value)).not.toContain('shacl');
    expect(Array.from(select.options).map(option => option.value)).not.toContain('both');
    apiClient.post.mockResolvedValueOnce({ data: {
      status: 'published', ontology_registration: { ontology_id: 'published-schema' },
      graph_publication: { status: 'success', resources: 123, relationships: 45 },
    } });
    fireEvent.change(screen.getByPlaceholderText(/e.g., Product Model/i), { target: { value: 'Published schema' } });
    fireEvent.change(screen.getByPlaceholderText(/e.g., myprefix/i), { target: { value: 'published_schema' } });
    fireEvent.click(screen.getByRole('button', { name: /Upload and Parse/i }));
    setCredentialProfile('INGESTION_WRITE_TOKEN', 'fixture-write');
    fireEvent.click(screen.getByRole('button', { name: /^Start$/i }));
    await waitFor(() => expect(apiClient.post).toHaveBeenCalled());
    expect(apiClient.post.mock.calls.at(-1)[1].get('publish')).toBe('true');
    await waitFor(() => expect(screen.getByText('123')).toBeInTheDocument());
  });

  it('keeps an explicit governance rejection separate from uncertain publication', async () => {
    await renderPipeline();
    const input = document.querySelector('input[type="file"]');
    await act(async () => {
      fireEvent.change(input, { target: { files: [new File(['schema'], 'demo.xsd', { type: 'application/xml' })] } });
      await flushAsyncEffects();
    });
    const select = document.getElementById('ontology-generation-select');
    expect(select).toHaveValue('owl');
    expect(Array.from(select.options).map(option => option.value)).not.toContain('shacl');
    expect(Array.from(select.options).map(option => option.value)).not.toContain('both');
    apiClient.post.mockResolvedValueOnce({ data: {
      status: 'policy_blocked', message: 'Publication blocked by policy checks.',
    } });
    fireEvent.change(screen.getByPlaceholderText(/e.g., Product Model/i), { target: { value: 'Published schema' } });
    fireEvent.change(screen.getByPlaceholderText(/e.g., myprefix/i), { target: { value: 'published_schema' } });
    fireEvent.click(screen.getByRole('button', { name: /Upload and Parse/i }));
    setCredentialProfile('INGESTION_WRITE_TOKEN', 'fixture-write');
    fireEvent.click(screen.getByRole('button', { name: /^Start$/i }));
    await waitFor(() => expect(apiClient.post).toHaveBeenCalled());
    expect(apiClient.post.mock.calls.at(-1)[1].get('publish')).toBe('true');
    await screen.findAllByText(/Publication blocked by policy checks/);
    expect(screen.queryByText(/Publication outcome is unverified/)).not.toBeInTheDocument();
  });

  it('sends multiple companion schemas through the engineering workflow in selected order', async () => {
    await renderPipeline();
    fireEvent.click(screen.getByLabelText(/Register XSD/));
    apiClient.post.mockClear();
    apiClient.post.mockResolvedValueOnce({ data: {
      status: 'registered', ontology_registration: { ontology_id: 'bom-bundle' },
    } });
    await act(async () => {
      fireEvent.change(document.querySelector('input[type="file"]'), { target: { files: [new File(['root'], 'bom.xsd')] } });
      await flushAsyncEffects();
    });
    fireEvent.change(screen.getByPlaceholderText(/e.g., Product Model/i), { target: { value: 'BOM bundle' } });
    fireEvent.change(screen.getByPlaceholderText(/e.g., myprefix/i), { target: { value: 'bom' } });
    fireEvent.change(document.getElementById('ontology-generation-select'), { target: { value: 'owl' } });
    fireEvent.click(screen.getByRole('button', { name: /Upload and Parse/i }));
    fireEvent.change(screen.getByLabelText('Companion XSD files'), { target: { files: [
      new File(['common'], 'common.xsd'), new File(['part'], 'part.xsd'),
    ] } });
    fireEvent.change(screen.getByLabelText(/Companion relative paths/), { target: { value: 'common.xsd\ntypes/part.xsd' } });
    setCredentialProfile('INGESTION_WRITE_TOKEN', 'fixture-write');
    const start = screen.getByRole('button', { name: /^Start$/i });
    fireEvent.click(start);
    fireEvent.click(start);
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledTimes(1));
    const [url, form] = apiClient.post.mock.calls[0];
    expect(url).toBe('/api/v1/engineering-workflows');
    expect(form.getAll('dependencies').map(file => file.name)).toEqual(['common.xsd', 'part.xsd']);
    expect(JSON.parse(form.get('dependency_paths'))).toEqual(['common.xsd', 'types/part.xsd']);
    expect(form.get('publish')).toBe('false');
  });

  it('combines multiple XSD selections into one metadata prompt and registration', async () => {
    await renderPipeline();
    fireEvent.click(screen.getByLabelText(/Register XSD/));
    const xml = '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:test"/>';
    const selected = ['bom.xsd', 'assembly.xsd'].map(name => {
      const file = new File([xml], name);
      file.text = async () => xml;
      return file;
    });
    await act(async () => {
      fireEvent.change(document.querySelector('input[type="file"]'), { target: { files: selected } });
      await flushAsyncEffects();
    });
    expect(screen.getByText('uploaded-schema-set.xsd')).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText(/e.g., Product Model/i), { target: { value: 'Combined Ontology' } });
    fireEvent.change(screen.getByPlaceholderText(/e.g., myprefix/i), { target: { value: 'combined' } });
    fireEvent.change(document.getElementById('ontology-generation-select'), { target: { value: 'owl' } });
    fireEvent.click(screen.getByRole('button', { name: /Upload and Parse/i }));
    apiClient.post.mockClear();
    apiClient.post.mockResolvedValueOnce({ data: { status: 'registered', ontology_registration: { ontology_id: 'combined' } } });
    setCredentialProfile('INGESTION_WRITE_TOKEN', 'fixture-write');
    fireEvent.click(screen.getByRole('button', { name: /^Start$/i }));
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledTimes(1));
    const form = apiClient.post.mock.calls[0][1];
    expect(form.get('ontology_name')).toBe('Combined Ontology');
    expect(form.getAll('dependencies').map(file => file.name)).toEqual(['bom.xsd', 'assembly.xsd']);
    expect(screen.getByRole('region', { name: 'Import job history' })).toHaveStyle({ overflowX: 'auto' });
    expect(screen.getByText('Processing details')).toBeInTheDocument();
    await screen.findAllByText(/registered; graph publication has not run/);
    expect(screen.getByText('Review, approve and publish this ontology to Neo4j')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Clear finished/failed history' }));
    await waitFor(() => expect(screen.queryByText('uploaded-schema-set.xsd')).not.toBeInTheDocument());
  });

  it('register-only RDF uses the retained draft workflow without requesting graph publication', async () => {
    await renderPipeline();
    fireEvent.click(screen.getByLabelText(/Register XSD/));
    apiClient.post.mockClear();
    apiClient.post.mockResolvedValueOnce({ data: {
      status: 'registered', ontology_registration: { ontology_id: 'rdf-source' },
    } });
    await act(async () => {
      fireEvent.change(document.querySelector('input[type="file"]'), { target: { files: [new File(['<urn:a> <urn:b> <urn:c> .'], 'evidence.ttl')] } });
      await flushAsyncEffects();
    });
    fireEvent.change(screen.getByPlaceholderText(/e.g., Product Model/i), { target: { value: 'RDF evidence' } });
    fireEvent.change(screen.getByPlaceholderText(/e.g., myprefix/i), { target: { value: 'evidence' } });
    fireEvent.click(screen.getByRole('button', { name: /Upload and Parse/i }));
    setCredentialProfile('INGESTION_WRITE_TOKEN', 'fixture-write');
    fireEvent.click(screen.getByRole('button', { name: /^Start$/i }));
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledTimes(1));
    const [url, form] = apiClient.post.mock.calls[0];
    expect(url).toBe('/api/v1/engineering-workflows');
    expect(form.get('publish')).toBe('false');
    await screen.findAllByText(/registered; graph publication has not run/);
  });
  it('a failed document job does not claim indexing succeeded', async () => {
    await renderPipeline();
    API_METHODS.document.submitJob.mockResolvedValue({data:{task_id:'failed-document',status:'failed',result:{processed_documents:0}}});
    await act(async () => {
      fireEvent.change(document.querySelector('input[type="file"]'), {target:{files:[new File(['text'],'evidence.txt')]}});
      await flushAsyncEffects();
    });
    setCredentialProfile('INGESTION_WRITE_TOKEN', 'fixture-write');
    fireEvent.click(screen.getByRole('button', {name:/^Start$/i}));
    await screen.findByText(/Document processing did not complete successfully/);
    expect(screen.queryByText('Document retained and indexed for GraphRAG search.')).not.toBeInTheDocument();
  });

});
