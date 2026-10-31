import React from 'react';
import { vi } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import RestSourcesPanel from './RestSourcesPanel';
import { dataPipelineAPI as api } from '../services/apiClient';
vi.mock('../services/apiClient',()=>({dataPipelineAPI:{restSources:vi.fn(),definitions:vi.fn(),registerRestSource:vi.fn(),previewRestSource:vi.fn(),createDefinition:vi.fn(),runDefinition:vi.fn()}}));
vi.mock('../services/serviceAuth',()=>({getCredentialProfile:()=> 'session-token'}));
beforeEach(()=>{
  localStorage.clear();
  vi.clearAllMocks();
  api.restSources.mockResolvedValue({data:{sources:[{source_id:'parts-api',name:'PLM parts'}]}});
  api.definitions.mockResolvedValue({data:{definitions:[{job_id:'fetch',version:'1.0.0',name:'Fetch parts',job_type:'rest-source-ingest',lifecycle_state:'approved',enabled:true},{job_id:'draft',version:'1.0.0',name:'Unapproved',job_type:'rest-source-ingest',lifecycle_state:'draft',enabled:true}]}});
});
test('preview and worker submission use selected source and approved definition',async()=>{
  api.previewRestSource.mockResolvedValue({data:{record_count:1,records:[{name:'Part A'}]}});
  api.runDefinition.mockResolvedValue({data:{run_manifest:{run_id:'run-rest'}}});
  render(<RestSourcesPanel/>);
  fireEvent.click(screen.getByText('Refresh sources and jobs'));
  await screen.findByText('PLM parts');
  await waitFor(()=>expect(screen.getByText('Refresh sources and jobs')).not.toBeDisabled());
  expect(screen.queryByText('Unapproved')).toBeNull();
  fireEvent.change(screen.getByLabelText('Registered source'),{target:{value:'parts-api'}});
  fireEvent.click(screen.getByText('Test connection and preview'));
  await screen.findByText('Part A');
  expect(api.previewRestSource).toHaveBeenCalledWith('parts-api','session-token');
  fireEvent.change(screen.getByLabelText('Approved acquisition job'),{target:{value:'fetch@1.0.0'}});
  fireEvent.click(screen.getByText('Fetch records with worker'));
  await screen.findByText(/Run run-rest:/);
  expect(api.runDefinition).toHaveBeenCalledWith('fetch','1.0.0',expect.objectContaining({source_id:'parts-api',idempotency_key:expect.any(String)}),expect.objectContaining({approval_token:'session-token'}));
});
test('late responses after session invalidation cannot restore sources',async()=>{
  let finish;
  api.restSources.mockReturnValue(new Promise(resolve=>{finish=resolve;}));
  render(<RestSourcesPanel/>);
  fireEvent.click(screen.getByText('Refresh sources and jobs'));
  act(()=>window.dispatchEvent(new Event('depo:session-expired')));
  await act(async()=>finish({data:{sources:[{source_id:'old',name:'Old session source'}]}}));
  expect(screen.queryByText('Old session source')).toBeNull();
  expect(screen.getByRole('alert')).toHaveTextContent('Access changed');
});
test('rapid submission only queues one run',async()=>{
  let finish;
  api.runDefinition.mockReturnValue(new Promise(resolve=>{finish=resolve;}));
  render(<RestSourcesPanel/>);
  fireEvent.click(screen.getByText('Refresh sources and jobs'));
  await screen.findByText('PLM parts');
  await waitFor(()=>expect(screen.getByText('Refresh sources and jobs')).not.toBeDisabled());
  fireEvent.change(screen.getByLabelText('Registered source'),{target:{value:'parts-api'}});
  fireEvent.change(screen.getByLabelText('Approved acquisition job'),{target:{value:'fetch@1.0.0'}});
  const button=screen.getByText('Fetch records with worker');
  fireEvent.click(button);fireEvent.click(button);
  expect(api.runDefinition).toHaveBeenCalledTimes(1);
  await act(async()=>finish({data:{run_manifest:{run_id:'one'}}}));
});

test('source paging requests a bounded next page and removes stale selection',async()=>{
  api.restSources.mockResolvedValueOnce({data:{sources:[{source_id:'first',name:'First'}],total:51,next_offset:50}})
    .mockResolvedValueOnce({data:{sources:[{source_id:'last',name:'Last'}],total:51,next_offset:null}});
  render(<RestSourcesPanel/>);
  fireEvent.click(screen.getByText('Refresh sources and jobs'));await screen.findByText('First');
  await waitFor(()=>expect(screen.getByText('Refresh sources and jobs')).not.toBeDisabled());
  fireEvent.change(screen.getByLabelText('Registered source'),{target:{value:'first'}});
  fireEvent.click(screen.getByText('Next sources'));await screen.findByText('Last');
  expect(api.restSources).toHaveBeenLastCalledWith({params:{limit:50,offset:50}});
  expect(screen.getByText('Test connection and preview')).toBeDisabled();
});

test('source preview does not wait for an unresolved job catalog',async()=>{
  let finish;
  api.definitions.mockReturnValue(new Promise(resolve=>{finish=resolve;}));
  api.previewRestSource.mockResolvedValue({data:{record_count:1,records:[{name:'Independent Part'}]}});
  render(<RestSourcesPanel/>);
  fireEvent.click(screen.getByText('Refresh sources and jobs'));await screen.findByText('PLM parts');
  await waitFor(()=>expect(screen.getByLabelText('Registered source')).not.toBeDisabled());
  fireEvent.change(screen.getByLabelText('Registered source'),{target:{value:'parts-api'}});
  fireEvent.click(screen.getByText('Test connection and preview'));await screen.findByText('Independent Part');
  await act(async()=>finish({data:{definitions:[]}}));
});
