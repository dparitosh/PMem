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

  const renderForm = (props = {}) => {
    render(
      <OntologyMetadataForm
        selectedFile={mockFile}
        onSubmit={mockOnSubmit}
        onCancel={mockOnCancel}
        {...props}
      />
    );
  };

  describe('Rendering', () => {
    it('should render modal with title when shown', () => {
      renderForm({ formTitle: 'Test Ontology Form' });

      expect(screen.getByText(/Test Ontology Form/i)).toBeInTheDocument();
    });

    it('should display file information correctly', () => {
      renderForm();

      expect(screen.getByText(/Domain_model.xsd/)).toBeInTheDocument();
      expect(screen.getByText(/^XSD$/)).toBeInTheDocument();
    });

    it('should render form inputs for ontology name, prefix, and generation type', () => {
      renderForm();

      expect(screen.getByLabelText(/Ontology Name/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Namespace Prefix/i)).toBeInTheDocument();
      expect(screen.getByRole('combobox')).toBeInTheDocument();
    });

    it('should show correct generation type options for XSD files', async () => {
      renderForm();

      const selectElement = screen.getByRole('combobox');
      expect(selectElement).toBeInTheDocument();
      await userEvent.click(selectElement);
      // SHACL should be recommended for XSD
      expect(screen.getAllByText(/SHACL.*Recommended/i).length).toBeGreaterThan(0);
    });
  });

  describe('Form Validation', () => {
    it('should show error when ontology name is empty', async () => {
      renderForm();

      const submitButton = screen.getByRole('button', { name: /Upload and Parse/i });
      await userEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/Ontology name is required/i)).toBeInTheDocument();
      });
      expect(mockOnSubmit).not.toHaveBeenCalled();
    });

    it('should derive a prefix when the field is empty', async () => {
      renderForm();

      const ontologyNameInput = screen.getByPlaceholderText(/e.g., Product Model/i);
      await userEvent.type(ontologyNameInput, 'Test Ontology');

      const submitButton = screen.getByRole('button', { name: /Upload and Parse/i });
      await userEvent.click(submitButton);

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(expect.objectContaining({ prefix: '' }));
      });
    });

    it('should show error when prefix contains invalid characters', async () => {
      renderForm({ selectedFile: new File([''], 'model.xmi') });

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
      renderForm();

      await waitFor(() => {
        expect(screen.getByRole('combobox')).toHaveValue('shacl');
      });
    });

    it('should accept valid form data and call onSubmit', async () => {
      renderForm();

      const ontologyNameInput = screen.getByPlaceholderText(/e.g., Product Model/i);
      await userEvent.type(ontologyNameInput, 'Domain Model');

      expect(screen.getByPlaceholderText(/e.g., myprefix/i)).toBeInTheDocument();

      const selectElement = screen.getByRole('combobox');
      await userEvent.selectOptions(selectElement, 'shacl');

      const submitButton = screen.getByRole('button', { name: /Upload and Parse/i });
      await userEvent.click(submitButton);

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            ontologyName: 'Domain Model',
            prefix: '',
            generationType: 'shacl'
          })
        );
      });
    });
  });

  describe('User Interactions', () => {
    it('should convert prefix to lowercase automatically', async () => {
      renderForm({ selectedFile: new File([''], 'model.xmi') });

      const prefixInput = screen.getByPlaceholderText(/e.g., myprefix/i);
      await userEvent.type(prefixInput, 'TestPrefix');

      expect(prefixInput.value).toBe('testprefix');
    });

    it('should call onCancel when cancel button is clicked', async () => {
      renderForm();

      const cancelButton = screen.getByRole('button', { name: /Cancel/i });
      await userEvent.click(cancelButton);

      expect(mockOnCancel).toHaveBeenCalled();
    });

    it('should disable buttons while loading', () => {
      renderForm({ isLoading: true });

      const cancelButton = screen.getByRole('button', { name: /Cancel/i });
      const submitButton = screen.getByRole('button', { name: /Processing/i });

      expect(cancelButton).toBeDisabled();
      expect(submitButton).toBeDisabled();
    });

    it('should accept optional description field', async () => {
      renderForm();

      const ontologyNameInput = screen.getByPlaceholderText(/e.g., Product Model/i);
      await userEvent.type(ontologyNameInput, 'Domain Model');

      expect(screen.getByPlaceholderText(/e.g., myprefix/i)).toBeInTheDocument();

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
    it('should show OWL as recommended for XMI files', async () => {
      const xmiFile = new File(['test content'], 'Domain_model.xmi', { type: 'application/xml' });
      renderForm({ selectedFile: xmiFile });

      const selectElement = screen.getByRole('combobox');
      await userEvent.click(selectElement);

      // OWL should be recommended for XMI
      expect(screen.getAllByText(/OWL.*Recommended/i).length).toBeGreaterThan(0);
    });
  });
});


describe('XSD namespace and prefix capture', () => {
  const schema = new File(['<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="http://www.plmxml.org/Schemas/PLMXMLSchema"/>'], 'teamcenter.xsd', {type: 'application/xml'});
  it('shows the authoritative source namespace and submits the requested alias', async () => {
    const submit = vi.fn();
    render(<OntologyMetadataForm selectedFile={schema} onSubmit={submit} onCancel={() => {}} publicationMode />);
    const namespace = await screen.findByLabelText('Source namespace (from XSD)');
    await waitFor(() => expect(namespace).toHaveValue('http://www.plmxml.org/Schemas/PLMXMLSchema'));
    expect(namespace).toHaveAttribute('readonly');
    await userEvent.type(screen.getByLabelText(/Ontology Name/), 'Teamcenter PLM Ontology');
    await userEvent.clear(screen.getByLabelText(/Namespace Prefix/));
    await userEvent.type(screen.getByLabelText(/Namespace Prefix/), 'custom');
    await userEvent.click(screen.getByRole('button', {name: 'Upload and Parse'}));
    expect(submit).toHaveBeenCalledWith(expect.objectContaining({prefix: 'custom', fileType: 'xsd', generationType: 'owl'}));
    expect(await new Promise(resolve => {const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.readAsText(schema);})).toContain('targetNamespace="http://www.plmxml.org/Schemas/PLMXMLSchema"');
  });
  it('rejects invalid XSD aliases before submission', async () => {
    const submit = vi.fn();
    render(<OntologyMetadataForm selectedFile={schema} onSubmit={submit} onCancel={() => {}} />);
    await userEvent.type(screen.getByLabelText(/Ontology Name/), 'Teamcenter');
    await userEvent.type(screen.getByLabelText(/Namespace Prefix/), 'bad-prefix');
    await userEvent.click(screen.getByRole('button', {name: 'Upload and Parse'}));
    expect(screen.getByText(/Prefix must start/)).toBeVisible();
    expect(submit).not.toHaveBeenCalled();
  });
});

 describe('automatic namespace aliases', () => {
   it.each([
     ['https://example.org/Product#', 'xmlns:product="https://example.org/Product#"', 'product'],
     ['http://www.plmxml.org/Schemas/PLMXMLSchema', '', 'plmxmlschema'],
     ['urn:example:2026-model', '', 'ns_2026_model'],
   ])('derives the alias for %s', async (namespace, binding, expected) => {
     const source = new File([`<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" ${binding} targetNamespace="${namespace}"/>`], 'source.xsd');
     render(<OntologyMetadataForm selectedFile={source} onSubmit={() => {}} onCancel={() => {}} />);
     await waitFor(() => expect(screen.getByLabelText(/Namespace Prefix/)).toHaveValue(expected));
   });
   it('preserves an initial user override', async () => {
     const source = new File(['<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:example:product"/>'], 'source.xsd');
     render(<OntologyMetadataForm selectedFile={source} initialValues={{prefix:'chosen'}} onSubmit={() => {}} onCancel={() => {}} />);
     await waitFor(() => expect(screen.getByLabelText('Source namespace (from XSD)')).toHaveValue('urn:example:product'));
     expect(screen.getByLabelText(/Namespace Prefix/)).toHaveValue('chosen');
   });
 });

 test('EXPRESS accepts OWL metadata in publication mode', async () => {
  const submit = jest.fn();
  render(<OntologyMetadataForm selectedFile={new File(['SCHEMA demo; END_SCHEMA;'], 'demo.exp')} onSubmit={submit} onCancel={() => {}} publicationMode />);
  expect(document.getElementById('ontology-generation-select')).toHaveValue('owl');
  fireEvent.change(screen.getByPlaceholderText(/e.g., Product Model/), {target:{value:'Demo'}});
  fireEvent.click(screen.getByRole('button', {name:/Upload and Parse/i}));
  expect(submit).toHaveBeenCalledWith(expect.objectContaining({fileType:'exp',generationType:'owl'}));
 });
