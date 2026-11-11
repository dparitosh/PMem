import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import QifInstanceCheck from './QifInstanceCheck';

const { qifAPI } = vi.hoisted(() => ({ qifAPI: { checkInstance: vi.fn() } }));
vi.mock('../../services/apiClient', () => ({ qifAPI }));

function chooseFile(name = 'part.xml') {
  const input = document.getElementById('qif-instance-file');
  const file = new File(['<QIFDocument/>'], name, { type: 'text/xml' });
  fireEvent.change(input, { target: { files: [file] } });
  return file;
}

describe('QifInstanceCheck', () => {
  afterEach(() => { qifAPI.checkInstance.mockReset(); });

  it('keeps the run button disabled until a file is chosen', () => {
    render(<QifInstanceCheck />);
    expect(screen.getByRole('button', { name: 'Run QIF checks' })).toBeDisabled();
  });

  it('shows schema status and check findings returned by the backend', async () => {
    qifAPI.checkInstance.mockResolvedValue({ data: {
      filename: 'part.xml', xsd_valid: false, check_finding_count: 1,
      xsd_errors: [{ line: 3, message: "The attribute 'versionQIF' is required but missing." }],
      check_findings: [{ report: 'Quality limit exceeded', node: '/QIFDocument[1]/Product[1]' }],
    } });
    render(<QifInstanceCheck />);
    const file = chooseFile();
    fireEvent.click(screen.getByRole('button', { name: 'Run QIF checks' }));
    await waitFor(() => expect(screen.getByText(/schema invalid, 1 check finding/)).toBeInTheDocument());
    expect(qifAPI.checkInstance).toHaveBeenCalledWith(file);
    expect(screen.getByText(/versionQIF/)).toBeInTheDocument();
    expect(screen.getByText(/Quality limit exceeded/)).toBeInTheDocument();
  });

  it('shows the backend refusal message when the instance is not supported', async () => {
    qifAPI.checkInstance.mockImplementation(() => Promise.reject(Object.assign(new Error('Request failed with status code 422'), { response: { status: 422, data: { detail: 'Instances with external QIF document references are not supported by this check.' } } })));
    render(<QifInstanceCheck />);
    chooseFile();
    fireEvent.click(screen.getByRole('button', { name: 'Run QIF checks' }));
    await waitFor(() => expect(qifAPI.checkInstance).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole('alert')).toHaveTextContent('external QIF document references');
  });
});
