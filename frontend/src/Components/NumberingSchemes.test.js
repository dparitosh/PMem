import React from 'react';
import {vi} from 'vitest';
import {render,screen,fireEvent,waitFor,act} from '@testing-library/react';
import NumberingSchemes from './NumberingSchemes';
import {apiClient} from '../services/apiClient';
import {getCredentialProfile} from '../services/serviceAuth';
vi.mock('../services/apiClient',()=>({apiClient:{get:vi.fn(),put:vi.fn()}}));
vi.mock('../services/serviceAuth',()=>({getCredentialProfile:vi.fn()}));
const schemes=()=>['CR','CO','WF','DS','FILE','RUN'].map(kind=>({kind,label:kind,prefix:kind,digits:6,include_year:true,revision:0,next_preview:kind+'-2026-000001'}));
beforeEach(()=>{vi.clearAllMocks();getCredentialProfile.mockReturnValue('session');apiClient.get.mockResolvedValue({data:{schemes:schemes()}});apiClient.put.mockResolvedValue({data:{}});});
test('numbering saves an exact revision with maintenance access',async()=>{
 render(<NumberingSchemes/>);await screen.findByLabelText('CR prefix');
 fireEvent.change(screen.getByLabelText('CR prefix'),{target:{value:'REQ'}});
 fireEvent.click(screen.getAllByRole('button',{name:'Save'})[0]);
 await waitFor(()=>expect(apiClient.put).toHaveBeenCalledWith(expect.stringContaining('/CR'),{prefix:'REQ',digits:6,include_year:true,expected_revision:0},expect.objectContaining({headers:{'X-API-Key':'session'}})));
 await screen.findByText('CR numbering saved. Existing IDs are unchanged.');
});
test('read access cannot save numbering',async()=>{
 getCredentialProfile.mockImplementation(key=>key==='ADMIN_API_KEY'?'':'reader');
 render(<NumberingSchemes/>);await screen.findByLabelText('CR prefix');
 fireEvent.change(screen.getByLabelText('CR prefix'),{target:{value:'REQ'}});
 expect(screen.getAllByRole('button',{name:'Save'})[0]).toBeDisabled();expect(apiClient.put).not.toHaveBeenCalled();
});
test('a reconnect clears old rows and ignores a late old-session response',async()=>{
 let finish;apiClient.get.mockReturnValueOnce(new Promise(resolve=>{finish=resolve;}));
 render(<NumberingSchemes/>);
 act(()=>window.dispatchEvent(new Event('depo:credentials-cleared')));
 await screen.findByLabelText('CR prefix');
 await act(async()=>finish({data:{schemes:schemes().map(row=>({...row,prefix:'OLD'}))}}));
 expect(screen.getByLabelText('CR prefix')).toHaveValue('CR');
});
