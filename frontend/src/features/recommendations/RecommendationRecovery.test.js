import React from 'react';
import {act,render,screen,cleanup} from '@testing-library/react';
import ReadGoalPanel from '../../Components/ReadGoalPanel.js';
import {agenticClient} from '../../services/agenticApi.js';
import {normalizeRecommendationResult} from '../../features/recommendations/services/recommendationPresentation.js';
import {ManufacturingResult} from '../../features/recommendations/ManufacturingResult.js';
vi.mock('../../services/agenticApi.js',()=>({agenticClient:{get:vi.fn(),post:vi.fn()}}));
afterEach(()=>{cleanup();vi.useRealTimers();vi.clearAllMocks();sessionStorage.clear();});
test('AG-01 regression: permanent workflow 404 is retried indefinitely',async()=>{
 vi.useFakeTimers();agenticClient.get.mockRejectedValue({response:{status:404,data:{detail:'Goal not found'}}});
 render(<ReadGoalPanel agent="graph-analyst" task="Inspect" initialRunId="goal-deleted"/>);
 await act(async()=>{await vi.advanceTimersByTimeAsync(25000);});
 expect(agenticClient.get).toHaveBeenCalledTimes(1);
 expect(screen.getByRole('button',{name:'Refresh investigation status'})).toBeEnabled();
 expect(screen.getByRole('button',{name:'Start read-only investigation'})).toBeDisabled();
});
class Boundary extends React.Component{state={error:false};static getDerivedStateFromError(){return {error:true};}render(){return this.state.error?<p>Audit rendering failure</p>:this.props.children;}}

test('transient status failures stop after a bounded retry budget and manual refresh does not resubmit',async()=>{
 vi.useFakeTimers();agenticClient.get.mockRejectedValue({response:{status:503,data:{detail:'Unavailable'}}});
 render(<ReadGoalPanel agent="graph-analyst" task="Inspect" initialRunId="goal-recover"/>);
 await act(async()=>{await vi.advanceTimersByTimeAsync(60000);});
 expect(agenticClient.get).toHaveBeenCalledTimes(3);
 agenticClient.get.mockResolvedValue({data:{run_id:'goal-recover',status:'completed',goal:'Inspect',result:{summary:'Recovered'}}});
 await act(async()=>{screen.getByRole('button',{name:'Refresh investigation status'}).click();});
 expect(agenticClient.get).toHaveBeenCalledTimes(4);
 expect(agenticClient.post).not.toHaveBeenCalled();
 expect(screen.queryByRole('button',{name:'Refresh investigation status'})).toBeNull();
});
test('REC-01 regression: malformed process count passes response checks and crashes result rendering',()=>{
 expect(()=>normalizeRecommendationResult('manufacturing',{part:{name:'Bearing'},process_summary:{total_direct:{value:1}}})).toThrow(/invalid evidence/);
});
