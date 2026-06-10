import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import OntologyMetadataForm from './OntologyMetadataForm';

describe('OntologyMetadataForm Component', () => {
  const mockFile = new File(['test content'], 'Domain_model.xsd', { type: 'application/xml' });
  const mockOnSubmit = jest.fn();
  const mockOnCancel = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Rendering', () => {
    it('should render modal with title when shown', () => {
      render(
        <OntologyMetadataForm
          selectedFile={mockFile}
          onSubmit={mockOnSubmit}
          onCancel={mockOnCancel}
          formTitle="Test Ontology Form"
        />
      );

      expect(screen.getByText(/Test Ontology Form/i)).toBeInTheDocument();
    });

    it('should display file information correctly', () => {
      render(
        <OntologyMetadataForm
          selectedFile={mockFile}
          onSubmit={mockOnSubmit}
          onCancel={mockOnCancel}
        />
      );

      expect(screen.getByText(/Domain_model.xsd/)).toBeInTheDocument();
      expect(screen.getByText(/^XSD$/)).toBeInTheDocument();
    });

    it('should render form inputs for ontology name, prefix, and generation type', () => {
      render(
        <OntologyMetadataForm
          selectedFile={mockFile}
          onSubmit={mockOnSubmit}
          onCancel={mockOnCancel}
        />
      );

      expect(screen.getByLabelText(/Ontology Name/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Namespace Prefix/i)).toBeInTheDocument();
      expect(screen.getByRole('combobox')).toBeInTheDocument();
    });

    it('should show correct generation type options for XSD files', () => {
      render(
        <OntologyMetadataForm
          selectedFile={mockFile}
          onSubmit={mockOnSubmit}
          onCancel={mockOnCancel}
        />
      );

      const selectElement = screen.getByRole('combobox');
      expect(selectElement).toBeInTheDocument();
      // Options should be in select dropdown
      fireEvent.click(selectElement);
      // SHACL should be recommended for XSD
      expect(screen.getAllByText(/SHACL.*Recommended/i).length).toBeGreaterThan(0);
    });
  });

  describe('Form Validation', () => {
    it('should show error when ontology name is empty', async () => {
      render(
        <OntologyMetadataForm
          selectedFile={mockFile}
          onSubmit={mockOnSubmit}
          onCancel={mockOnCancel}
        />
      );

      const submitButton = screen.getByRole('button', { name: /Upload and Parse/i });
      await userEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/Ontology name is required/i)).toBeInTheDocument();
      });
      expect(mockOnSubmit).not.toHaveBeenCalled();
    });

    it('should show error when prefix is empty', async () => {
      render(
        <OntologyMetadataForm
          selectedFile={mockFile}
          onSubmit={mockOnSubmit}
          onCancel={mockOnCancel}
        />
      );

      const ontologyNameInput = screen.getByPlaceholderText(/e.g., Product Model/i);
      await userEvent.type(ontologyNameInput, 'Test Ontology');

      const submitButton = screen.getByRole('button', { name: /Upload and Parse/i });
      await userEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/Prefix is required/i)).toBeInTheDocument();
      });
      expect(mockOnSubmit).not.toHaveBeenCalled();
    });

    it('should show error when prefix contains invalid characters', async () => {
      render(
        <OntologyMetadataForm
          selectedFile={mockFile}
          onSubmit={mockOnSubmit}
          onCancel={mockOnCancel}
        />
      );

      const ontologyNameInput = screen.getByPlaceholderText(/e.g., Product Model/i);
      await userEvent.type(ontologyNameInput, 'Test Ontology');

      const prefixInput = screen.getByPlaceholderText(/e.g., myprefix/i);
      await userEvent.type(prefixInput, 'Test-Prefix'); // Invalid: contains hyphen

      const submitButton = screen.getByRole('button', { name: /Upload and Parse/i });
      await userEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/Prefix must start with a lowercase/i)).toBeInTheDocument();
      });
      expect(mockOnSubmit).not.toHaveBeenCalled();
    });

    it('should preselect recommended generation type for XSD files', async () => {
      render(
        <OntologyMetadataForm
          selectedFile={mockFile}
          onSubmit={mockOnSubmit}
          onCancel={mockOnCancel}
        />
      );

      await waitFor(() => {
        expect(screen.getByRole('combobox')).toHaveValue('shacl');
      });
    });

    it('should accept valid form data and call onSubmit', async () => {
      render(
        <OntologyMetadataForm
          selectedFile={mockFile}
          onSubmit={mockOnSubmit}
          onCancel={mockOnCancel}
        />
      );

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
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            ontologyName: 'Domain Model',
            prefix: 'domain',
            generationType: 'shacl'
          })
        );
      });
    });
  });

  describe('User Interactions', () => {
    it('should convert prefix to lowercase automatically', async () => {
      render(
        <OntologyMetadataForm
          selectedFile={mockFile}
          onSubmit={mockOnSubmit}
          onCancel={mockOnCancel}
        />
      );

      const prefixInput = screen.getByPlaceholderText(/e.g., myprefix/i);
      await userEvent.type(prefixInput, 'TestPrefix');

      expect(prefixInput.value).toBe('testprefix');
    });

    it('should call onCancel when cancel button is clicked', async () => {
      render(
        <OntologyMetadataForm
          selectedFile={mockFile}
          onSubmit={mockOnSubmit}
          onCancel={mockOnCancel}
        />
      );

      const cancelButton = screen.getByRole('button', { name: /Cancel/i });
      await userEvent.click(cancelButton);

      expect(mockOnCancel).toHaveBeenCalled();
    });

    it('should disable buttons while loading', () => {
      render(
        <OntologyMetadataForm
          selectedFile={mockFile}
          onSubmit={mockOnSubmit}
          onCancel={mockOnCancel}
          isLoading={true}
        />
      );

      const cancelButton = screen.getByRole('button', { name: /Cancel/i });
      const submitButton = screen.getByRole('button', { name: /Processing/i });

      expect(cancelButton).toBeDisabled();
      expect(submitButton).toBeDisabled();
    });

    it('should accept optional description field', async () => {
      render(
        <OntologyMetadataForm
          selectedFile={mockFile}
          onSubmit={mockOnSubmit}
          onCancel={mockOnCancel}
        />
      );

      const ontologyNameInput = screen.getByPlaceholderText(/e.g., Product Model/i);
      await userEvent.type(ontologyNameInput, 'Domain Model');

      const prefixInput = screen.getByPlaceholderText(/e.g., myprefix/i);
      await userEvent.type(prefixInput, 'domain');

      const descriptionInput = screen.getByPlaceholderText(/Optional description/i);
      await userEvent.type(descriptionInput, 'Test description');

      const selectElement = screen.getByRole('combobox');
      await userEvent.selectOptions(selectElement, 'shacl');

      const submitButton = screen.getByRole('button', { name: /Upload and Parse/i });
      await userEvent.click(submitButton);

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            description: 'Test description'
          })
        );
      });
    });
  });

  describe('XMI File Handling', () => {
    it('should show OWL as recommended for XMI files', () => {
      const xmiFile = new File(['test content'], 'Domain_model.xmi', { type: 'application/xml' });
      
      render(
        <OntologyMetadataForm
          selectedFile={xmiFile}
          onSubmit={mockOnSubmit}
          onCancel={mockOnCancel}
        />
      );

      const selectElement = screen.getByRole('combobox');
      fireEvent.click(selectElement);
      
      // OWL should be recommended for XMI
      expect(screen.getAllByText(/OWL.*Recommended/i).length).toBeGreaterThan(0);
    });
  });
});
