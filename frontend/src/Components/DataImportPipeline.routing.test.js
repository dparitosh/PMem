import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DataImportPipeline from './DataImportPipeline';

const mockOntologyContextValue = {
  ontologies: [],
};

jest.mock('../config', () => ({
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
  buildUrl: (value) => value,
  replaceParams: (endpoint, params = {}) => Object.keys(params).reduce((result, key) => result.replace(`{${key}}`, params[key]), endpoint),
}));

jest.mock('../contexts/OntologyContext', () => ({
  useOntologies: () => mockOntologyContextValue,
}));

const mockListRegistered = jest.fn();
const mockWorkflowOptions = jest.fn();
const mockOntologyUpload = jest.fn();

jest.mock('../services/apiClient', () => ({
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
  },
  apiClient: {
    get: jest.fn(),
    post: jest.fn(),
  },
}));

describe('DataImportPipeline workflow routing', () => {
  beforeEach(() => {
    mockListRegistered.mockResolvedValue({ data: { ontologies: [] } });
    mockWorkflowOptions.mockResolvedValue({ data: { workflows: [] } });
    mockOntologyUpload.mockReset();
    window.localStorage.clear();
  });

  it('auto-routes XSD files from instance import into ontology registration and shows the filename', async () => {
    render(<DataImportPipeline />);

    const input = document.querySelector('input[type="file"]');
    const file = new File(['schema'], 'bom.xsd', { type: 'application/xml' });

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText(/Ontology Metadata/i)).toBeInTheDocument();
    });

    expect(screen.queryByText(/Import instance graph only accepts source data files/i)).not.toBeInTheDocument();
    expect(screen.getAllByText('bom.xsd').length).toBeGreaterThan(0);
  });

  it('auto-routes CSV files from ontology workflow back into instance import and shows the filename', async () => {
    render(<DataImportPipeline />);

    fireEvent.click(screen.getByRole('button', { name: /Create ontology/i }));

    const input = document.querySelector('input[type="file"]');
    const file = new File(['a,b\n1,2'], 'parts.csv', { type: 'text/csv' });

    fireEvent.change(input, { target: { files: [file] } });

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

    render(<DataImportPipeline />);

    const input = document.querySelector('input[type="file"]');
    const file = new File(['schema'], 'bom.xsd', { type: 'application/xml' });

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText(/Ontology Metadata/i)).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText(/e.g., Product Model/i), { target: { value: 'BOM Ontology' } });
    fireEvent.change(screen.getByPlaceholderText(/e.g., myprefix/i), { target: { value: 'bom' } });
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'shacl' } });
    fireEvent.click(screen.getByRole('button', { name: /Upload and Parse/i }));

    await waitFor(() => {
      expect(screen.queryByText(/Ontology Metadata/i)).not.toBeInTheDocument();
    });

    expect(mockOntologyUpload).not.toHaveBeenCalled();
    expect(screen.getByText(/Metadata saved for 'BOM Ontology'. Click Start to register ontology./i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^Start$/i }));

    await waitFor(() => {
      expect(mockOntologyUpload).toHaveBeenCalledTimes(1);
    });

    expect(mockOntologyUpload).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'bom.xsd' }),
      expect.objectContaining({
        ontologyName: 'BOM Ontology',
        prefix: 'bom',
        generationType: 'shacl',
      })
    );
  });

  it('queues multiple ontology files and advances the metadata popup file-by-file', async () => {
    render(<DataImportPipeline />);

    const input = document.querySelector('input[type="file"]');
    const fileOne = new File(['schema-one'], 'bom.xsd', { type: 'application/xml' });
    const fileTwo = new File(['schema-two'], 'assembly.xsd', { type: 'application/xml' });

    fireEvent.change(input, { target: { files: [fileOne, fileTwo] } });

    await waitFor(() => {
      expect(screen.getByText(/File:/i)).toBeInTheDocument();
      expect(screen.getByText('bom.xsd')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText(/e.g., Product Model/i), { target: { value: 'BOM Ontology' } });
    fireEvent.change(screen.getByPlaceholderText(/e.g., myprefix/i), { target: { value: 'bom' } });
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'shacl' } });
    fireEvent.click(screen.getByRole('button', { name: /Upload and Parse/i }));

    await waitFor(() => {
      expect(screen.getByText('assembly.xsd')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText(/e.g., Product Model/i), { target: { value: 'Assembly Ontology' } });
    fireEvent.change(screen.getByPlaceholderText(/e.g., myprefix/i), { target: { value: 'assembly' } });
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'shacl' } });
    fireEvent.click(screen.getByRole('button', { name: /Upload and Parse/i }));

    await waitFor(() => {
      expect(screen.queryByText(/Ontology Metadata/i)).not.toBeInTheDocument();
    });

    expect(screen.getAllByRole('button', { name: /^Start$/i }).length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('bom.xsd').length).toBeGreaterThan(0);
    expect(screen.getAllByText('assembly.xsd').length).toBeGreaterThan(0);
  });
});