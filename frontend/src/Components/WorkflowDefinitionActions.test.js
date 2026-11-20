import React from 'react';
import {vi} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import WorkflowDefinitionActions from './WorkflowDefinitionActions';
import {dataPipelineAPI as api} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({dataPipelineAPI:{definitions:vi.fn(),runs:vi.fn(),createDefinitionChange:vi.fn()}}));
vi.mock('../services/serviceAuth',()=>({getCredentialProfile:()=> 'workflow-session',publicationRecoveryScope:()=> 'test-connection'}));
beforeEach(()=>{vi.clearAllMocks();sessionStorage.clear();api.definitions.mockResolvedValue({data:{definitions:[{job_id:'validate-source',version:'1.0.0',lifecycle_state:'draft',enabled:true}]}});api.runs.mockResolvedValue({data:{runs:[]}});api.createDefinitionChange.mockImplementation(async payload=>({data:{preview_id:payload.request_id,job_id:payload.job_id,version:payload.version,operation:payload.operation}}));});
async function review(){await screen.findByLabelText('Requested change');fireEvent.change(screen.getByLabelText('Requested change'),{target:{value:'approve'}});fireEvent.change(screen.getByLabelText('Change reason'),{target:{value:'Release reviewed source workflow'}});fireEvent.click(screen.getByLabelText('I reviewed this workflow version and the requested change.'));}
test('submits a credential-bound CR without directly approving the definition',async()=>{render(<WorkflowDefinitionActions jobId="validate-source" version="1.0.0"/>);await review();fireEvent.click(screen.getByText('Submit workflow CR'));await screen.findByText('Review workflow CR / CO');expect(api.createDefinitionChange).toHaveBeenCalledWith(expect.objectContaining({job_id:'validate-source',operation:'approve',reason:'Release reviewed source workflow'}),'workflow-session');});
test('uncertain submission reuses its identity after refresh',async()=>{api.createDefinitionChange.mockRejectedValueOnce(new Error('Connection lost'));const view=render(<WorkflowDefinitionActions jobId="validate-source" version="1.0.0"/>);await review();fireEvent.click(screen.getByText('Submit workflow CR'));await screen.findByRole('alert');const first=api.createDefinitionChange.mock.calls[0][0];view.unmount();render(<WorkflowDefinitionActions jobId="validate-source" version="1.0.0"/>);await screen.findByText(/Previous submission is unconfirmed/);fireEvent.click(screen.getByLabelText('I reviewed this workflow version and the requested change.'));fireEvent.click(screen.getByText('Submit workflow CR'));await screen.findByText('Review workflow CR / CO');expect(api.createDefinitionChange.mock.calls[1][0]).toEqual(first);});
test('confirmed rejection permits correction',async()=>{api.createDefinitionChange.mockRejectedValueOnce({response:{status:422,data:{detail:'Invalid change'}}});render(<WorkflowDefinitionActions jobId="validate-source" version="1.0.0"/>);await review();fireEvent.click(screen.getByText('Submit workflow CR'));await screen.findByRole('alert');await waitFor(()=>expect(screen.getByLabelText('Change reason')).not.toBeDisabled());});


test('new source support is submitted as an exact new version rather than editing the old definition',async()=>{
 api.definitions.mockResolvedValue({data:{definitions:[{job_id:'validate-source',version:'1.0.0',lifecycle_state:'approved',enabled:true,job_type:'validate-semantic-batch',allowed_standards:['ap242']}]}});
 render(<WorkflowDefinitionActions jobId="validate-source" version="1.0.0"/>);
 fireEvent.change(await screen.findByLabelText('Requested change'),{target:{value:'revise'}});
 expect(screen.getByLabelText('New workflow version')).toHaveValue('1.0.1');
 fireEvent.click(screen.getByLabelText('SysML v1'));
 fireEvent.change(screen.getByLabelText('Change reason'),{target:{value:'Enable verified SysML source adapter'}});
 fireEvent.click(screen.getByLabelText('I reviewed this workflow version and the requested change.'));
 fireEvent.click(screen.getByText('Submit workflow CR'));
 await screen.findByText('Review workflow CR / CO');
 expect(api.createDefinitionChange).toHaveBeenCalledWith(expect.objectContaining({version:'1.0.0',operation:'revise',parameters:{version:'1.0.1',allowed_standards:['ap242','sysml-v1']}}),'workflow-session');
});
