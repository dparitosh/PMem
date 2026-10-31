// Regression tests from the REST source audit.
import React from 'react';
import {vi} from 'vitest';
import {render,screen,fireEvent,act,waitFor} from '@testing-library/react';
import RestSourcesPanel from './RestSourcesPanel';
import {dataPipelineAPI as api} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({dataPipelineAPI:{restSources:vi.fn(),definitions:vi.fn(),previewRestSource:vi.fn(),registerRestSource:vi.fn(),createDefinition:vi.fn(),runDefinition:vi.fn()}}));
vi.mock('../services/serviceAuth',()=>({getCredentialProfile:()=> 'session-token'}));
beforeEach(()=>{
  localStorage.clear();
  vi.clearAllMocks();
  api.restSources.mockResolvedValue({data:{sources:[{source_id:'parts',name:'Parts'}]}});
  api.definitions.mockResolvedValue({data:{definitions:[{job_id:'fetch',version:'1.0.0',name:'Fetch',job_type:'rest-source-ingest',enabled:true,lifecycle_state:'approved'}]}});
});
async function selectSource() {
  fireEvent.click(screen.getByText('Refresh sources and jobs'));
  await screen.findByText('Parts');
  await waitFor(()=>expect(screen.getByText('Refresh sources and jobs')).not.toBeDisabled());
  fireEvent.change(screen.getByLabelText('Registered source'),{target:{value:'parts'}});
}
test('failed preview must remove previous connection-success data',async()=>{
  api.previewRestSource.mockResolvedValueOnce({data:{record_count:1,records:[{name:'Old Part'}]}}).mockRejectedValueOnce(new Error('Connection failed'));
  render(<RestSourcesPanel/>);await selectSource();
  fireEvent.click(screen.getByText('Test connection and preview'));await screen.findByText('Old Part');
  fireEvent.click(screen.getByText('Test connection and preview'));await screen.findByRole('alert');
  expect(screen.queryByText(/Connection succeeded/)).toBeNull();
  expect(screen.queryByText('Old Part')).toBeNull();
});
test('an empty refresh must clear a previously selected job and source',async()=>{
  render(<RestSourcesPanel/>);await selectSource();
  fireEvent.change(screen.getByLabelText('Approved acquisition job'),{target:{value:'fetch@1.0.0'}});
  api.restSources.mockResolvedValueOnce({data:{sources:[]}});
  api.definitions.mockResolvedValueOnce({data:{definitions:[]}});
  fireEvent.click(screen.getByText('Refresh sources and jobs'));
  await screen.findByText(/No approved acquisition job loaded/);
  expect(screen.getByText('Test connection and preview')).toBeDisabled();
});
test('source browsing remains available when only the job catalog fails',async()=>{
  api.definitions.mockRejectedValue(new Error('Job registry unavailable'));
  render(<RestSourcesPanel/>);
  fireEvent.click(screen.getByText('Refresh sources and jobs'));
  await screen.findByRole('alert');
  expect(screen.getByRole('option',{name:'Parts'})).toBeInTheDocument();
});
test('reconnect must not enable a second submission while the first outcome is unknown',async()=>{
  let complete;
  api.runDefinition.mockReturnValue(new Promise(resolve=>{complete=resolve;}));
  render(<RestSourcesPanel/>);await selectSource();
  fireEvent.change(screen.getByLabelText('Approved acquisition job'),{target:{value:'fetch@1.0.0'}});
  fireEvent.click(screen.getByText('Fetch records with worker'));
  act(()=>window.dispatchEvent(new Event('depo:session-replaced')));
  await selectSource();
  fireEvent.change(screen.getByLabelText('Approved acquisition job'),{target:{value:'fetch@1.0.0'}});
  fireEvent.click(screen.getByText('Fetch records with worker'));
  await act(async()=>complete({data:{run_manifest:{run_id:'run-one'}}}));
  expect(api.runDefinition).toHaveBeenCalledTimes(1);
});
