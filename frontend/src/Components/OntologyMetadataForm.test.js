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
      expect(screen.getByText(/XSD/)).toBeInTheDocument();
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
      expect(screen.getByLabelText(/Generate As/i)).toBeInTheDocument();
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
      expect(screen.getByText(/SHACL.*Recommended/i)).toBeInTheDocument();
    });
  });

  describe('Form Validation', () => {
    it('should show error when ontology name is empty', async () => {
      const user = userEvent.setup();
      render(
        <OntologyMetadataForm
          selectedFile={mockFile}
          onSubmit={mockOnSubmit}
          onCancel={mockOnCancel}
        />
      );

      const submitButton = screen.getByRole('button', { name: /Upload & Parse/i });
      await user.click(submitButton);

      expect(screen.getByText(/Ontology name is required/i)).toBeInTheDocument();
      expect(mockOnSubmit).not.toHaveBeenCalled();
    });

    it('should show error when prefix is empty', async () => {
      const user = userEvent.setup();
      render(
        <OntologyMetadataForm
          selectedFile={mockFile}
          onSubmit={mockOnSubmit}
          onCancel={mockOnCancel}
        />
      );

      const ontologyNameInput = screen.getByPlaceholderText(/e.g., Product Model/i);
      await user.type(ontologyNameInput, 'Test Ontology');

      const submitButton = screen.getByRole('button', { name: /Upload & Parse/i });
      await user.click(submitButton);

      expect(screen.getByText(/Prefix is required/i)).toBeInTheDocument();
      expect(mockOnSubmit).not.toHaveBeenCalled();
    });

    it('should show error when prefix contains invalid characters', async () => {
      const user = userEvent.setup();
      render(
        <OntologyMetadataForm
          selectedFile={mockFile}
          onSubmit={mockOnSubmit}
          onCancel={mockOnCancel}
        />
      );

      const ontologyNameInput = screen.getByPlaceholderText(/e.g., Product Model/i);
      await user.type(ontologyNameInput, 'Test Ontology');

      const prefixInput = screen.getByPlaceholderText(/e.g., myprefix/i);
      await user.type(prefixInput, 'Test-Prefix'); // Invalid: contains hyphen

      const submitButton = screen.getByRole('button', { name: /Upload & Parse/i });
      await user.click(submitButton);

      expect(screen.getByText(/Prefix must start with lowercase/i)).toBeInTheDocument();
      expect(mockOnSubmit).not.toHaveBeenCalled();
    });

    it('should show error when generation type not selected', async () => {
      const user = userEvent.setup();
      render(
        <OntologyMetadataForm
          selectedFile={mockFile}
          onSubmit={mockOnSubmit}
          onCancel={mockOnCancel}
        />
      );

      const ontologyNameInput = screen.getByPlaceholderText(/e.g., Product Model/i);
      await user.type(ontologyNameInput, 'Test Ontology');

      const prefixInput = screen.getByPlaceholderText(/e.g., myprefix/i);
      await user.type(prefixInput, 'testprefix');

      const submitButton = screen.getByRole('button', { name: /Upload & Parse/i });
      await user.click(submitButton);

      expect(screen.getByText(/Please select generation type/i)).toBeInTheDocument();
      expect(mockOnSubmit).not.toHaveBeenCalled();
    });

    it('should accept valid form data and call onSubmit', async () => {
      const user = userEvent.setup();
      render(
        <OntologyMetadataForm
          selectedFile={mockFile}
          onSubmit={mockOnSubmit}
          onCancel={mockOnCancel}
        />
      );

      // Fill form
      const ontologyNameInput = screen.getByPlaceholderText(/e.g., Product Model/i);
      await user.type(ontologyNameInput, 'Domain Model');

      const prefixInput = screen.getByPlaceholderText(/e.g., myprefix/i);
      await user.type(prefixInput, 'domain');

      const selectElement = screen.getByRole('combobox');
      await user.selectOption(selectElement, 'shacl');

      const submitButton = screen.getByRole('button', { name: /Upload & Parse/i });
      await user.click(submitButton);

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
      const user = userEvent.setup();
      render(
        <OntologyMetadataForm
          selectedFile={mockFile}
          onSubmit={mockOnSubmit}
          onCancel={mockOnCancel}
        />
      );

      const prefixInput = screen.getByPlaceholderText(/e.g., myprefix/i);
      await user.type(prefixInput, 'TestPrefix');

      expect(prefixInput.value).toBe('testprefix');
    });

    it('should call onCancel when cancel button is clicked', async () => {
      const user = userEvent.setup();
      render(
        <OntologyMetadataForm
          selectedFile={mockFile}
          onSubmit={mockOnSubmit}
          onCancel={mockOnCancel}
        />
      );

      const cancelButton = screen.getByRole('button', { name: /Cancel/i });
      await user.click(cancelButton);

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
      const user = userEvent.setup();
      render(
        <OntologyMetadataForm
          selectedFile={mockFile}
          onSubmit={mockOnSubmit}
          onCancel={mockOnCancel}
        />
      );

      const ontologyNameInput = screen.getByPlaceholderText(/e.g., Product Model/i);
      await user.type(ontologyNameInput, 'Domain Model');

      const prefixInput = screen.getByPlaceholderText(/e.g., myprefix/i);
      await user.type(prefixInput, 'domain');

      const descriptionInput = screen.getByPlaceholderText(/Optional description/i);
      await user.type(descriptionInput, 'Test description');

      const selectElement = screen.getByRole('combobox');
      await user.selectOption(selectElement, 'shacl');

      const submitButton = screen.getByRole('button', { name: /Upload & Parse/i });
      await user.click(submitButton);

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
      expect(screen.getByText(/OWL.*Recommended/i)).toBeInTheDocument();
    });
  });
});
