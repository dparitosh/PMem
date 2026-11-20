import React from 'react';
import {vi} from 'vitest';
import {render,screen,fireEvent,act} from '@testing-library/react';
import AutomationEvidence from './AutomationEvidence';
import {apiClient} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({apiClient:{get:vi.fn()}}));
vi.mock('../services/serviceAuth',()=>({getCredentialProfile:()=> 'reader'}));
const run={run_id:'retained',job_id:'validate',job_version:'1.0.0',run_number:'RUN-2026-000002'};
const plan={uri:'http://local/oslc/automation/plans/validate%3A1.0.0',identifier:'validate:1.0.0',type:'oslc_auto:AutomationPlan',title:'Validate assembly'};
const result={'oslc_auto:reportsOnAutomationPlan':'http://local/oslc/automation/plans/validate%3A1.0.0',identifier:'retained',type:'oslc_auto:AutomationResult','oslc_auto:state':'oslc_auto:complete','oslc_auto:verdict':'oslc_auto:passed'};
beforeEach(()=>vi.clearAllMocks());
test('inspection validates exact run and plan without submitting execution',async()=>{
 apiClient.get.mockImplementation(url=>Promise.resolve({data:url.includes('/plans/')?plan:result}));
 render(<AutomationEvidence run={run}/>);fireEvent.click(screen.getByText('Verify automation evidence'));
 await screen.findByText('Validate assembly · 1.0.0');expect(screen.getByText('RUN-2026-000002')).toBeInTheDocument();expect(screen.getByText('passed')).toBeInTheDocument();expect(apiClient.get).toHaveBeenCalledTimes(2);
});
test('an unrelated result is not presented as evidence',async()=>{
 apiClient.get.mockImplementation(url=>Promise.resolve({data:url.includes('/plans/')?plan:{...result,identifier:'another-run'}}));
 render(<AutomationEvidence run={run}/>);fireEvent.click(screen.getByText('Verify automation evidence'));
 await screen.findByRole('alert');expect(screen.queryByText('passed')).toBeNull();
});
test('a late result after session expiration cannot restore retained evidence',async()=>{
 let finish;apiClient.get.mockImplementation(url=>url.includes('/plans/')?Promise.resolve({data:plan}):new Promise(resolve=>{finish=resolve;}));
 render(<AutomationEvidence run={run}/>);fireEvent.click(screen.getByText('Verify automation evidence'));
 act(()=>window.dispatchEvent(new Event('depo:session-expired')));
 await act(async()=>finish({data:result}));expect(screen.queryByText('passed')).toBeNull();expect(screen.getByText('Verify automation evidence')).not.toBeDisabled();
});
