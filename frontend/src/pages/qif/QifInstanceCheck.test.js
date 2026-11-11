import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import QifInstanceCheck from './QifInstanceCheck';

const { qifAPI } = vi.hoisted(() => ({ qifAPI: { checkInstance: vi.fn(), checkBoc: vi.fn() } }));
vi.mock('../../services/apiClient', () => ({ qifAPI }));

function chooseQif(name = 'part.xml') {
  const file = new File(['<QIFDocument/>'], name, { type: 'text/xml' });
  fireEvent.change(document.getElementById('qif-instance-file'), { target: { files: [file] } });
  return file;
}

function chooseAp242(name = 'part.stp') {
  const file = new File(['ISO-10303-21;'], name, { type: 'application/octet-stream' });
  fireEvent.change(document.getElementById('qif-ap242-file'), { target: { files: [file] } });
  return file;
}

describe('QifInstanceCheck', () => {
  afterEach(() => {
    qifAPI.checkInstance.mockReset();
    qifAPI.checkBoc.mockReset();
  });

  it('keeps the run button disabled until a QIF file is chosen', () => {
    render(<QifInstanceCheck />);
    expect(screen.getByRole('button', { name: 'Run QIF checks' })).toBeDisabled();
  });

  it('shows check findings returned by the backend', async () => {
    qifAPI.checkInstance.mockResolvedValue({ data: {
      filename: 'part.xml', check_finding_count: 1,
      check_findings: [{ report: 'Quality limit exceeded', node: '/QIFDocument[1]/Product[1]' }],
    } });
    render(<QifInstanceCheck />);
    const file = chooseQif();
    fireEvent.click(screen.getByRole('button', { name: 'Run QIF checks' }));
    await waitFor(() => expect(screen.getByText(/1 QIF check finding/)).toBeInTheDocument());
    expect(qifAPI.checkInstance).toHaveBeenCalledWith(file);
    expect(screen.getByText(/Quality limit exceeded/)).toBeInTheDocument();
    expect(qifAPI.checkBoc).not.toHaveBeenCalled();
  });

  it('runs the BOC comparison and shows matched and unmatched items when an AP242 file is chosen', async () => {
    qifAPI.checkInstance.mockResolvedValue({ data: { filename: 'part.xml', check_finding_count: 0, check_findings: [] } });
    qifAPI.checkBoc.mockResolvedValue({ data: {
      summary: { matched: 1, ambiguous: 0, ap242_dimensions: 2, qif_characteristics: 1, ap242_tolerances: 1 },
      matched: [{ ap242: { id: 'ap:6', name: 'Hole diameter' }, qif: { id: 'qif:C-1', name: 'C-1' }, nominal_value: 25, qif_unit: 'mm' }],
      ambiguous: [],
      ap242_dimensions_unmatched: [{ id: 'ap:9', name: 'Slot width', reason: 'no QIF characteristic with this nominal value' }],
      qif_characteristics_unmatched: [],
      ap242_tolerances_for_review: [{ id: 'ap:5', name: 'Position tolerance' }],
      scope_notes: ['AP242 tolerance values are not extracted; tolerances are listed for manual review.'],
    } });
    render(<QifInstanceCheck />);
    const qif = chooseQif();
    const ap242 = chooseAp242();
    fireEvent.click(screen.getByRole('button', { name: 'Run QIF checks and BOC comparison' }));
    await waitFor(() => expect(screen.getByText(/1 matched, 0 ambiguous/)).toBeInTheDocument());
    expect(qifAPI.checkBoc).toHaveBeenCalledWith(qif, ap242);
    expect(screen.getByText(/Hole diameter/)).toBeInTheDocument();
    expect(screen.getByText(/Slot width/)).toBeInTheDocument();
    expect(screen.getByText(/Position tolerance/)).toBeInTheDocument();
    expect(screen.getByText(/tolerance values are not extracted/)).toBeInTheDocument();
  });

  it('shows the backend refusal message when the instance is not supported', async () => {
    qifAPI.checkInstance.mockImplementation(() => Promise.reject(Object.assign(new Error('Request failed with status code 422'), { response: { status: 422, data: { detail: 'Instances with external QIF document references are not supported by this check.' } } })));
    render(<QifInstanceCheck />);
    chooseQif();
    fireEvent.click(screen.getByRole('button', { name: 'Run QIF checks' }));
    await waitFor(() => expect(qifAPI.checkInstance).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole('alert')).toHaveTextContent('external QIF document references');
  });
});
