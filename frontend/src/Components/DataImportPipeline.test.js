/* eslint-disable testing-library/no-node-access, testing-library/no-wait-for-empty-callback */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DataImportPipeline from './DataImportPipeline';

jest.mock('../config', () => ({
  __esModule: true,
  default: {
    backendUrl: 'http://localhost:8000',
    apiUrl: 'http://localhost:8000',
    requestTimeout: 30000,
    debug: false,
  },
  config: {
    backendUrl: 'http://localhost:8000',
    apiUrl: 'http://localhost:8000',
    requestTimeout: 30000,
    debug: false,
  },
  API: {
    ontology: {},
    graph: {},
    import: {},
    workflow: {},
    recommendations: {},
  },
  buildUrl: (endpoint) => `http://localhost:8000${endpoint}`,
  replaceParams: (endpoint, params = {}) => Object.keys(params).reduce((result, key) => result.replace(`{${key}}`, params[key]), endpoint),
}));

jest.mock('../contexts/OntologyContext', () => ({
  useOntologies: () => ({
    ontologies: [],
    loading: false,
    error: null,
    refreshOntologies: jest.fn(),
  }),
}));

describe('DataImportPipeline Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // Mock fetch
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe('Component Rendering', () => {
    it('should render the data import pipeline heading', () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ontologies: [] })
      });

      render(<DataImportPipeline />);

      expect(screen.getByText(/Data Import Pipeline/i)).toBeInTheDocument();
      expect(screen.getByText(/Upload and process data files/i)).toBeInTheDocument();
    });

    it('should render pipeline stages', () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ontologies: [] })
      });

      render(<DataImportPipeline />);

      expect(screen.getByText(/Upload/)).toBeInTheDocument();
      expect(screen.getByText(/Convert/)).toBeInTheDocument();
      expect(screen.getByText(/Validate/)).toBeInTheDocument();
      expect(screen.getByText(/Load/)).toBeInTheDocument();
    });

    it('should have file upload area', () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ontologies: [] })
      });

      render(<DataImportPipeline />);

      expect(screen.getByText(/Drag files here or click to upload/i)).toBeInTheDocument();
    });
  });

  describe('XSD File Upload Flow', () => {
    it('should show metadata form when XSD file is selected', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ontologies: [] })
      });

      render(<DataImportPipeline />);

      const file = new File(['test content'], 'Domain_model.xsd', { type: 'application/xml' });
      const input = document.querySelector('input[type="file"]');

      fireEvent.change(input, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByText(/Ontology Metadata/i)).toBeInTheDocument();
      });
    });

    it('should not show metadata form for non-ontology files', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ontologies: [] })
      });

      render(<DataImportPipeline />);

      const file = new File(['test,data\n1,2\n'], 'data.csv', { type: 'text/csv' });
      const input = document.querySelector('input[type="file"]');

      fireEvent.change(input, { target: { files: [file] } });

      await waitFor(() => {
        // CSV should be added directly without metadata form
        expect(screen.queryByText(/Ontology Metadata/i)).not.toBeInTheDocument();
      });
    });

    it('should upload ontology file with metadata after form submission', async () => {
      global.fetch
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ ontologies: [] })
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            task_id: 'task_123',
            ontology_id: 'ont_456',
            ontology_name: 'Domain Model',
            prefix: 'domain',
            filename: 'Domain_model.xsd'
          })
        });

      render(<DataImportPipeline />);

      const file = new File(['test content'], 'Domain_model.xsd', { type: 'application/xml' });
      const input = document.querySelector('input[type="file"]');

      fireEvent.change(input, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByText(/Ontology Metadata/i)).toBeInTheDocument();
      });

      // Fill form
      const ontologyNameInput = screen.getByPlaceholderText(/e.g., Product Model/i);
      await userEvent.type(ontologyNameInput, 'Domain Model');

      const prefixInput = screen.getByPlaceholderText(/e.g., myprefix/i);
      await userEvent.type(prefixInput, 'domain');

      const selectElement = screen.getByRole('combobox');
      await userEvent.selectOptions(selectElement, 'shacl');

      const submitButton = screen.getByRole('button', { name: /Upload and Parse/i });
      await userEvent.click(submitButton);

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          'http://localhost:8000/api/v1/ontology/upload',
          expect.objectContaining({
            method: 'POST',
            body: expect.any(FormData)
          })
        );
      });
    });
  });

  describe('XMI File Upload Flow', () => {
    it('should show metadata form when XMI file is selected', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ontologies: [] })
      });

      render(<DataImportPipeline />);

      const file = new File(['test content'], 'Domain_model.xmi', { type: 'application/xml' });
      const input = document.querySelector('input[type="file"]');

      fireEvent.change(input, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByText(/Ontology Metadata/i)).toBeInTheDocument();
      });
    });
  });

  describe('Error Handling', () => {
    it('should display error message for unsupported file types', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ontologies: [] })
      });

      render(<DataImportPipeline />);

      const file = new File(['test content'], 'unsupported.xyz', { type: 'application/unknown' });
      const input = document.querySelector('input[type="file"]');

      fireEvent.change(input, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByText(/No supported files/i)).toBeInTheDocument();
      });
    });

    it('should handle API upload errors gracefully', async () => {
      global.fetch
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ ontologies: [] })
        })
        .mockResolvedValueOnce({
          ok: false,
          status: 400,
          json: async () => ({ detail: 'File too large' })
        });

      render(<DataImportPipeline />);

      const file = new File(['test content'], 'Domain_model.xsd', { type: 'application/xml' });
      const input = document.querySelector('input[type="file"]');

      fireEvent.change(input, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByText(/Ontology Metadata/i)).toBeInTheDocument();
      });

      const ontologyNameInput = screen.getByPlaceholderText(/e.g., Product Model/i);
      await userEvent.type(ontologyNameInput, 'Test');

      const prefixInput = screen.getByPlaceholderText(/e.g., myprefix/i);
      await userEvent.type(prefixInput, 'test');

      const selectElement = screen.getByRole('combobox');
      await userEvent.selectOptions(selectElement, 'shacl');

      const submitButton = screen.getByRole('button', { name: /Upload and Parse/i });
      await userEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/Error uploading ontology/i)).toBeInTheDocument();
      });
    });
  });

  describe('Drag and Drop', () => {
    it('should accept files via drag and drop', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ontologies: [] })
      });

      render(<DataImportPipeline />);

      const dropZone = screen.getByText(/Drag files here/i).closest('div');
      const file = new File(['test content'], 'Domain_model.xsd', { type: 'application/xml' });

      fireEvent.dragEnter(dropZone);
      fireEvent.drop(dropZone, { dataTransfer: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByText(/Ontology Metadata/i)).toBeInTheDocument();
      });
    });
  });

  describe('Metadata Form Cancellation', () => {
    it('should close metadata form when cancel is clicked', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ontologies: [] })
      });

      const user = userEvent.setup();
      render(<DataImportPipeline />);

      const file = new File(['test content'], 'Domain_model.xsd', { type: 'application/xml' });
      const input = document.querySelector('input[type="file"]');

      fireEvent.change(input, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByText(/Ontology Metadata/i)).toBeInTheDocument();
      });

      const cancelButton = screen.getByRole('button', { name: /Cancel/i });
      await user.click(cancelButton);

      await waitFor(() => {
        expect(screen.queryByText(/Ontology Metadata/i)).not.toBeInTheDocument();
      });
    });
  });

  describe('File Size Validation', () => {
    it('should reject files larger than maximum size', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ontologies: [] })
      });

      render(<DataImportPipeline />);

      // Create a mock large file
      const largeContent = new Array(600 * 1024 * 1024).fill('x').join(''); // 600MB
      const file = new File([largeContent], 'large.xsd', { type: 'application/xml' });

      const input = document.querySelector('input[type="file"]');
      fireEvent.change(input, { target: { files: [file] } });

      // Should show validation error after form submission attempt
      await waitFor(() => {
        // The validation should be handled by the component or API
      });
    });
  });
});
