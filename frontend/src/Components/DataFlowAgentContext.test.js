import React from 'react';
import {render,screen,waitFor,fireEvent} from '@testing-library/react';
import {vi} from 'vitest';
import DataFlowAgentContext from './DataFlowAgentContext';
import {dataPipelineAPI as api} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({dataPipelineAPI:{getRun:vi.fn(),speedReview:vi.fn()}}));
vi.mock('./AgentControlPanel',()=>({default:()=> <p>Central workflow controls</p>}));
beforeEach(()=>{vi.clearAllMocks();window.history.replaceState(null,'','#/admin?view=agents&source=data-flow&run_id=run-one');});
test('verifies the source before showing central controls without a question form',async()=>{
 api.getRun.mockResolvedValue({data:{run_id:'run-one',run_number:'RUN-2026-000001',status:'completed'}});
 render(<DataFlowAgentContext/>);await screen.findByText('Central workflow controls');
 expect(screen.getByText('RUN-2026-000001 - completed')).toBeInTheDocument();
 expect(screen.getByRole('link',{name:'Back to Data Flow'})).toHaveAttribute('href','#/data-flow?view=runs&run_id=run-one');
 expect(screen.queryByRole('textbox')).toBeNull();
});
test('foreign record response cannot activate controls',async()=>{
 api.getRun.mockResolvedValue({data:{run_id:'other',status:'completed'}});render(<DataFlowAgentContext/>);
 expect(await screen.findByRole('alert')).toHaveTextContent('verified');expect(screen.queryByText('Central workflow controls')).toBeNull();
});
test('credential replacement discards a late prior-session response',async()=>{
 let finish;api.getRun.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;})).mockRejectedValue(new Error('Reconnect required'));
 render(<DataFlowAgentContext/>);fireEvent(window,new Event('depo:session-replaced'));
 finish({data:{run_id:'run-one',status:'completed'}});await waitFor(()=>expect(api.getRun).toHaveBeenCalledTimes(2));
 expect(await screen.findByRole('alert')).toHaveTextContent('Reconnect');expect(screen.queryByText('Central workflow controls')).toBeNull();
});
test('event handoff uses verified event evidence rather than treating it as an agent run',async()=>{
 window.history.replaceState(null,'','#/admin?view=agents&source=data-flow&reconciliation_id=event-one');
 api.speedReview.mockResolvedValue({data:{reconciliation_id:'event-one',status:'held',advisory_only:true,standard:'ap242'}});
 render(<DataFlowAgentContext/>);await screen.findByText('Central workflow controls');expect(api.getRun).not.toHaveBeenCalled();
});
