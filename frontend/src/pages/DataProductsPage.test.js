import React from 'react';
import { vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import DataProductsPage from './DataProductsPage';
import { readProductCollection } from '../services/productService';
import { dataPipelineAPI } from '../services/apiClient';
vi.mock('@siemens/ix-react', () => ({IxButton: ({children, ...props}) => <button {...props}>{children}</button>}));
vi.mock('../widgets/RegistryWidget', () => ({default: ({title}) => <h3>{title}</h3>}));
vi.mock('../contexts/OntologyContext', () => ({useOntologies: () => ({ontologies:[],loading:false})}));
vi.mock('../services/apiClient', () => ({apiClient:{get:vi.fn()},dataPipelineAPI:{getRun:vi.fn()}}));
vi.mock('../services/productService', () => ({readProductCollection:vi.fn(),PRODUCT_REFRESH_MS:15000,PRODUCT_CHANGED_EVENT:'depo:products-changed'}));
vi.mock('../Components/SchemaProductPublisher', () => ({default: ({draft}) => draft ? <div data-testid="retained-draft">{JSON.stringify(draft)}</div> : null}));
beforeEach(() => { vi.clearAllMocks(); window.location.hash = '#/data-products'; });
it('shows declared totals separately from a partial collection', async () => {
  readProductCollection.mockResolvedValue({rows:[{product_id:'a',version:'1'}],total:3,warning:'Partial collection'});
  render(<DataProductsPage mode="catalog" />);
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
