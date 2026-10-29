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
