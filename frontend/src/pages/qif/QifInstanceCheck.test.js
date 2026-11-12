import { fireEvent, render, screen, waitFor, act } from '@testing-library/react';
import { vi } from 'vitest';
import QifInstanceCheck from './QifInstanceCheck';

const { qifAPI } = vi.hoisted(() => ({ qifAPI: { checkInstance: vi.fn(), checkBoc: vi.fn() } }));
vi.mock('../../services/apiClient', () => ({ qifAPI }));

beforeEach(()=>{qifAPI.checkInstance.mockReset();qifAPI.checkBoc.mockReset();});

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
    expect(qifAPI.checkInstance).toHaveBeenCalledWith(file,expect.objectContaining({signal:expect.any(AbortSignal)}));
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
    await waitFor(() => expect(screen.getByText(/1 nominally paired, 0 ambiguous/)).toBeInTheDocument());
    expect(qifAPI.checkBoc).toHaveBeenCalledWith(qif, ap242,expect.objectContaining({signal:expect.any(AbortSignal)}));
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

it('shows unit and bounds conflicts with both source values',async()=>{
 qifAPI.checkInstance.mockResolvedValue({data:{filename:'part.xml',check_finding_count:0,check_findings:[]}});
 qifAPI.checkBoc.mockResolvedValue({data:{summary:{matched:1,ambiguous:0,bounds_mismatch:1,unit_mismatch:1},matched:[{ap242:{id:'ap:1',name:'Diameter'},qif:{id:'C1'},nominal_value:25,bounds_status:'mismatch',unit_status:'mismatch',ap242_values:{unit:'inch',bounds:{lower:24,upper:26}},qif_values:{unit:'mm',lower_limit:24.9,upper_limit:25.1}}]}});
 render(<QifInstanceCheck/>);chooseQif();chooseAp242();fireEvent.click(screen.getByRole('button',{name:'Run QIF checks and BOC comparison'}));
 expect(await screen.findByText(/Bounds conflicts: 1; unit conflicts: 1/)).toBeVisible();
 expect(screen.getByText(/Units: mismatch/)).toHaveTextContent('AP242: inch; QIF: mm');
 expect(screen.getByText(/Bounds: mismatch/)).toHaveTextContent('AP242: 24 to 26; QIF: 24.9 to 25.1');
 expect(screen.getByText(/not a conformance verdict/)).toBeVisible();
});
it('replacement input aborts old checks and prevents the old comparison chain',async()=>{
 let resolve;qifAPI.checkInstance.mockImplementation(()=>new Promise(done=>{resolve=done;}));
 render(<QifInstanceCheck/>);chooseQif('first.xml');chooseAp242();fireEvent.click(screen.getByRole('button',{name:'Run QIF checks and BOC comparison'}));
 const signal=qifAPI.checkInstance.mock.calls[0][1].signal;chooseQif('second.xml');expect(signal.aborted).toBe(true);
 await act(async()=>resolve({data:{filename:'first.xml',check_finding_count:0,check_findings:[]}}));
 expect(screen.queryByText('first.xml')).toBeNull();expect(qifAPI.checkBoc).not.toHaveBeenCalled();
});
it('late comparison cannot replace evidence for a different CAD file',async()=>{
 let resolve;qifAPI.checkInstance.mockResolvedValue({data:{filename:'part.xml',check_finding_count:0,check_findings:[]}});
 qifAPI.checkBoc.mockImplementation(()=>new Promise(done=>{resolve=done;}));
 render(<QifInstanceCheck/>);chooseQif();chooseAp242('old.stp');fireEvent.click(screen.getByRole('button',{name:'Run QIF checks and BOC comparison'}));
 await waitFor(()=>expect(qifAPI.checkBoc).toHaveBeenCalledTimes(1));const signal=qifAPI.checkBoc.mock.calls[0][2].signal;
 chooseAp242('new.stp');expect(signal.aborted).toBe(true);
 await act(async()=>resolve({data:{summary:{matched:99},matched:[]}}));
 expect(screen.queryByText(/99 nominally paired/)).toBeNull();
});
it('session replacement and unmount abort pending work',()=>{
 qifAPI.checkInstance.mockReturnValue(new Promise(()=>{}));const {unmount}=render(<QifInstanceCheck/>);chooseQif();
 fireEvent.click(screen.getByRole('button',{name:'Run QIF checks'}));const signal=qifAPI.checkInstance.mock.calls[0][1].signal;
 fireEvent(window,new Event('depo:session-replaced'));expect(signal.aborted).toBe(true);
 fireEvent.click(screen.getByRole('button',{name:'Run QIF checks'}));const next=qifAPI.checkInstance.mock.calls[1][1].signal;unmount();expect(next.aborted).toBe(true);
});
it('rejects a malformed comparison without crashing the page',async()=>{
 qifAPI.checkInstance.mockResolvedValue({data:{filename:'part.xml',check_finding_count:0,check_findings:[]}});qifAPI.checkBoc.mockResolvedValue({data:{summary:null}});
 render(<QifInstanceCheck/>);chooseQif();chooseAp242();fireEvent.click(screen.getByRole('button',{name:'Run QIF checks and BOC comparison'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('valid pairing evidence');
});
