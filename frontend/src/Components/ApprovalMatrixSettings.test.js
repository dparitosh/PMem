import React from 'react';
import {render,screen,fireEvent,waitFor,act} from '@testing-library/react';
import {vi} from 'vitest';
import ApprovalMatrixSettings from './ApprovalMatrixSettings';
import {apiClient} from '../services/apiClient';
import {getCredentialProfile} from '../services/serviceAuth';
vi.mock('../services/apiClient',()=>({apiClient:{get:vi.fn(),put:vi.fn()}}));
vi.mock('../services/serviceAuth',()=>({getCredentialProfile:vi.fn()}));
vi.mock('../config',()=>({buildSemanticServiceUrl:()=>'/approval-matrix'}));
const policy={name:'Engineering',revision:1,separate_requester:true,distinct_stage_actors:true,stages:[{action:'accept',function:'Engineering',mode:'ALL',members:['eng-a','eng-b']},{action:'authorize',function:'Release',mode:'ANY',members:['owner']}]};
async function open(){const view=render(<ApprovalMatrixSettings/>);const details=view.container.querySelector('details');details.open=true;fireEvent(details,new Event('toggle'));await screen.findByLabelText('accept principals');return view;}
beforeEach(()=>{vi.clearAllMocks();apiClient.get.mockResolvedValue({data:policy});getCredentialProfile.mockReturnValue('admin-session');apiClient.put.mockResolvedValue({data:{...policy,revision:2}});});
test('configuration is lazy and saves exact version without a typed actor',async()=>{const view=await open();fireEvent.click(screen.getByRole('button',{name:'Save approval matrix'}));await screen.findByText(/Saved for new requests/);expect(apiClient.put).toHaveBeenCalledWith('/approval-matrix',expect.objectContaining({expected_revision:1,stages:policy.stages}),expect.objectContaining({headers:{'X-API-Key':'admin-session'}}));expect(apiClient.put.mock.calls[0][1]).not.toHaveProperty('approved_by');view.unmount();});
test('read access cannot edit approval assignment',async()=>{getCredentialProfile.mockReturnValue('');await open();expect(screen.getByRole('button',{name:'Save approval matrix'})).toBeDisabled();expect(apiClient.put).not.toHaveBeenCalled();});
test('a session change discards a late successful save',async()=>{let resolve;apiClient.put.mockImplementation(()=>new Promise(r=>{resolve=r;}));const view=await open();fireEvent.click(screen.getByRole('button',{name:'Save approval matrix'}));await waitFor(()=>expect(apiClient.put).toHaveBeenCalled());act(()=>window.dispatchEvent(new Event('depo:session-replaced')));await act(async()=>resolve({data:{...policy,revision:2}}));expect(screen.queryByText(/Saved for new requests/)).not.toBeInTheDocument();view.unmount();});
