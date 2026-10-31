import React from 'react';
import { vi } from 'vitest';
import { render, screen, waitFor, fireEvent, act, cleanup } from '@testing-library/react';
import DataProductsPage from './DataProductsPage';
import { readProductCollection } from '../services/productService';
import { dataPipelineAPI, apiClient } from '../services/apiClient';
vi.mock('@siemens/ix-react', () => ({IxButton: ({children, ...props}) => <button {...props}>{children}</button>}));
vi.mock('../widgets/RegistryWidget', () => ({default: ({title,rows=[],onRowClicked}) => <><h3>{title}</h3>{rows.map(row=><button key={row.product_id+row.version} onClick={()=>onRowClicked?.(row)}>Open row {row.product_id}</button>)}</>}));
vi.mock('../contexts/OntologyContext', () => ({useOntologies: () => ({ontologies:[],loading:false})}));
vi.mock('../services/apiClient', () => ({apiClient:{get:vi.fn()},dataPipelineAPI:{getRun:vi.fn()}}));
vi.mock('../services/productService', () => ({readProductCollection:vi.fn(),PRODUCT_REFRESH_MS:15000,PRODUCT_CHANGED_EVENT:'depo:products-changed'}));
vi.mock('../Components/SchemaProductPublisher', () => ({default: ({draft}) => draft ? <div data-testid="retained-draft">{JSON.stringify(draft)}</div> : null}));
vi.mock('../Components/AgentProposalPanel', () => ({default: ({context}) => <div data-testid="governor-context">{JSON.stringify(context)}</div>}));
beforeEach(() => { vi.clearAllMocks(); window.location.hash = '#/data-products'; });
afterEach(() => cleanup());
it('hides empty collection and discovery controls until the list finishes loading', async () => {
  let resolve;
  readProductCollection.mockReturnValue(new Promise(done => { resolve = done; }));
  render(<DataProductsPage />);
  expect(screen.getByText('Loading products…')).toBeVisible();
  expect(screen.queryByLabelText('Discover product versions')).toBeNull();
  await act(async () => resolve({rows:[],total:0,warning:''}));
  expect(screen.getByLabelText('Discover product versions')).toBeVisible();
  expect(screen.getByRole('link',{name:'Connect publication access'})).toBeVisible();
});
it('session replacement reloads run evidence and discards an older response', async () => {
  window.location.hash = '#/data-products?run_id=loaded';
  readProductCollection.mockResolvedValue({rows:[],total:0,warning:''});
  let oldResolve;
  dataPipelineAPI.getRun.mockReturnValueOnce(new Promise(done => { oldResolve = done; }))
    .mockResolvedValue({data:{run_id:'loaded',status:'completed',output_manifest:{ods_receipt:{schema:'current_schema',counts:{entities:2},business_views:[]}}}});
  render(<DataProductsPage />);
  await waitFor(() => expect(dataPipelineAPI.getRun).toHaveBeenCalledTimes(1));
  await act(async () => window.dispatchEvent(new Event('depo:session-replaced')));
  expect(await screen.findByText('current_schema')).toBeVisible();
  await act(async () => oldResolve({data:{run_id:'loaded',status:'completed',output_manifest:{ods_receipt:{schema:'old_schema',counts:{entities:1}}}}}));
  expect(screen.queryByText('old_schema')).toBeNull();
  expect(dataPipelineAPI.getRun.mock.calls.length).toBeGreaterThanOrEqual(2);
});
it.each(['removed', 'retained', 'failed'])('background refresh handles a %s product snapshot', async (outcome) => {
  let poll;
  const visibility = vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
  const originalInterval = window.setInterval.bind(window);
  const interval = vi.spyOn(window, 'setInterval').mockImplementation((callback, delay, ...args) => {
    if (delay === 15000) { poll = callback; return 123; }
    return originalInterval(callback, delay, ...args);
  });
  readProductCollection.mockResolvedValueOnce({rows:[{product_id:'a',version:'1'}],total:1,warning:''});
  if (outcome === 'failed') readProductCollection.mockRejectedValue(new Error('List unavailable'));
  else readProductCollection.mockResolvedValue({rows:outcome === 'retained' ? [{product_id:'a',version:'1'}] : [],total:outcome === 'retained' ? 1 : 0,warning:''});
  apiClient.get.mockResolvedValueOnce({data:{product_id:'a',version:'1',name:'old-package-details'}})
    .mockResolvedValue({data:{product_id:'a',version:'1',name:'refreshed-package-details'}});
  render(<DataProductsPage />);
  await screen.findByText('Data Products (1 total; 1 loaded)');
  fireEvent.change(screen.getByLabelText('Product details and versions'), {target:{value:'a:1'}});
  await screen.findByRole('heading',{name:'old-package-details'});
  try {
    await act(async () => { poll(); });
    expect(screen.queryByText(/old-package-details/)).toBeNull();
    expect(screen.getByLabelText('Product details and versions')).toHaveValue(outcome === 'retained' ? 'a:1' : '');
    if (outcome === 'retained') expect(await screen.findByRole('heading',{name:'refreshed-package-details'})).toBeVisible();
  } finally { cleanup(); interval.mockRestore(); visibility.mockRestore(); }
});
it('shows declared totals separately from a partial collection', async () => {
  readProductCollection.mockResolvedValue({rows:[{product_id:'a',version:'1'}],total:3,warning:'Partial collection'});
  render(<DataProductsPage mode="catalog" />);
  fireEvent.click(screen.getByRole('tab',{name:'Published products'}));
  expect(await screen.findByText('Data Catalog (3 total; 1 loaded)')).toBeVisible();
  expect(screen.getByText('Partial collection')).toBeVisible();
});
it('reloads retained Data Flow evidence through the pipeline service', async () => {
  window.location.hash = '#/data-products?run_id=run-1';
  readProductCollection.mockResolvedValue({rows:[],total:0,warning:''});
  dataPipelineAPI.getRun.mockResolvedValue({data:{run_id:'run-1',status:'completed',output_manifest:{partition_artifacts:{accepted:'retained-1'}}}});
  render(<DataProductsPage />);
  await waitFor(() => expect(screen.getByTestId('retained-draft')).toHaveTextContent('retained-1'));
  expect(dataPipelineAPI.getRun).toHaveBeenCalledWith('run-1', expect.objectContaining({timeout:15000}));
  expect(screen.getByTestId('retained-draft')).toHaveTextContent('requires_review');
});

it.each(['available', 'pending'])('shows an existing analytics load when evidence is %s', async (evidenceStatus) => {
  window.location.hash = '#/data-products?run_id=loaded';
  readProductCollection.mockResolvedValue({rows:[],total:0,warning:''});
  dataPipelineAPI.getRun.mockResolvedValue({data:{run_id:'loaded',status:'completed',output_manifest:{evidence_status:evidenceStatus,partition_artifacts:{accepted:'receipt'},ods_receipt:{schema:'analytics_parts',analytics_readiness:'structural-data-loaded',counts:{entities:42},business_views:[]}}}});
  render(<DataProductsPage />);
  expect(await screen.findByText('analytics_parts')).toBeVisible();
  expect(screen.getByText('42')).toBeVisible();
  expect(screen.getByText('Prepare a separate analytics load').closest('details')).not.toHaveAttribute('open');
});

it('resolves older run artifacts using retained input roles and dependency paths', async () => {
  window.location.hash = '#/data-products?run_id=legacy';
  readProductCollection.mockResolvedValue({rows:[],total:0,warning:''});
  dataPipelineAPI.getRun.mockResolvedValue({data:{run_id:'legacy',status:'completed',analytics_inputs:{schema_artifact_id:'schema-old',xml_artifact_id:'xml-old',schema_dependencies:{'types.xsd':'dependency-old'}},output_manifest:{partition_artifacts:{accepted:'receipt-old'}}}});
  render(<DataProductsPage />);
  await waitFor(()=>expect(screen.getByLabelText('Retained XSD artifact ID')).toHaveValue('schema-old'));
  expect(screen.getByLabelText('Retained XML artifact ID')).toHaveValue('xml-old');
  expect(screen.getByLabelText('Schema dependencies (relative path → artifact ID, JSON)')).toHaveValue('{"types.xsd":"dependency-old"}');
});

it('visible evidence actions expand the relevant product workflow',async()=>{
 readProductCollection.mockResolvedValue({rows:[],total:0,warning:''});
 render(<DataProductsPage/>);
 fireEvent.click(screen.getByRole('tab',{name:'Create & review'}));
 fireEvent.click(screen.getByRole('button',{name:'Review structural analytics'}));
 expect(screen.getByText('Structural analytics: schema, dimensions and KPIs').closest('details')).toHaveAttribute('open');
 fireEvent.click(screen.getByRole('tab',{name:'Pipeline evidence'}));
 fireEvent.click(screen.getByRole('button',{name:'Review pipeline evidence'}));
 expect(screen.getByText('Pipeline evidence: create a product from Data Flow').closest('details')).toHaveAttribute('open');
});

it('catalog deep links open structural analytics directly on Products',async()=>{
 window.location.hash='#/data-products?view=structural';
 readProductCollection.mockResolvedValue({rows:[],total:0,warning:''});
 render(<DataProductsPage/>);
 expect(screen.getByText('Structural analytics: schema, dimensions and KPIs').closest('details')).toHaveAttribute('open');
});

it('catalog starts with ingested sources and keeps product creation behind its workspace',async()=>{
 readProductCollection.mockResolvedValue({rows:[],total:0,warning:''});
 render(<DataProductsPage mode="catalog"/>);
 expect(screen.getByRole('tab',{name:'Ingested sources'})).toHaveAttribute('aria-selected','true');
 expect(screen.queryByRole('tab',{name:'Structural analytics'})).toBeNull();
 fireEvent.click(screen.getByRole('tab',{name:'Product opportunities'}));
 expect(screen.getByRole('tab',{name:'Structural analytics'})).toBeVisible();
 fireEvent.click(screen.getByRole('tab',{name:'Published products'}));
 expect(await screen.findByRole('button',{name:'Browse ingested sources'})).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'Browse ingested sources'}));
 expect(screen.getByRole('tab',{name:'Ingested sources'})).toHaveAttribute('aria-selected','true');
});


it.each(['products','catalog'])('table row selection opens %s details using the shared row callback',async mode=>{
  readProductCollection.mockResolvedValue({rows:[{product_id:'selected',version:'1'}],total:1,warning:''});
  apiClient.get.mockResolvedValue({data:{product_id:'selected',version:'1',name:'Selected product details'}});
  render(<DataProductsPage mode={mode}/>);
  if(mode==='catalog') fireEvent.click(screen.getByRole('tab',{name:'Published products'}));
  fireEvent.click(await screen.findByRole('button',{name:'Open row selected'}));
  expect(await screen.findByRole('heading',{name:'Selected product details'})).toBeVisible();
  expect(screen.getByLabelText('Product details and versions')).toHaveValue(mode==='catalog'?'selected':'selected:1');
});

it('rejects a different product identity without forwarding it to Companion',async()=>{
  readProductCollection.mockResolvedValue({rows:[{product_id:'chosen',version:'1'}],total:1,warning:''});
  apiClient.get.mockResolvedValue({data:{product_id:'other',version:'1',name:'Wrong product'}});
  const changed=vi.fn();
  render(<DataProductsPage onCompanionRecordChange={changed}/>);
  fireEvent.click(await screen.findByRole('button',{name:'Open row chosen'}));
  expect(await screen.findByText('Product service returned a different selected identity.')).toBeVisible();
  expect(screen.queryByRole('heading',{name:'Wrong product'})).toBeNull();
  expect(changed.mock.calls.every(([value])=>!value?.product_id)).toBe(true);
});

it('the product governor receives the same selected product version as Companion',async()=>{
  readProductCollection.mockResolvedValue({rows:[{product_id:'chosen',version:'1'}],total:1,warning:''});
  apiClient.get.mockResolvedValue({data:{product_id:'chosen',version:'1',name:'Chosen product'}});
  const changed=vi.fn();render(<DataProductsPage onCompanionRecordChange={changed}/>);
  fireEvent.click(await screen.findByRole('button',{name:'Open row chosen'}));
  await screen.findByRole('heading',{name:'Chosen product'});
  expect(changed).toHaveBeenLastCalledWith({page:'data-products',product_id:'chosen',product_version:'1'});
  fireEvent.click(screen.getByRole('tab',{name:'Governance'}));
  expect(await screen.findByTestId('governor-context')).toHaveTextContent('"product_id":"chosen","product_version":"1"');
});
