import React from 'react';
import {vi} from 'vitest';
import {render,screen,fireEvent,act} from '@testing-library/react';
import AvailableAnalytics from './AvailableAnalytics';
import {dataPipelineAPI} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({dataPipelineAPI:{analytics:vi.fn(),analyticsDetail:vi.fn(),analyticsData:vi.fn()}}));
beforeEach(()=>vi.resetAllMocks());
test('distinguishes schema designs from loaded and published analytics',async()=>{
 dataPipelineAPI.analytics.mockResolvedValue({data:{datasets:[],total:0,next_offset:null}});
 const prepare=vi.fn();render(<AvailableAnalytics drafts={[{ontology_id:'private-id',label:'Parts design'}]} onPrepare={prepare}/>);
 await screen.findByText('No materialized analytics datasets found');
 fireEvent.click(screen.getByText('Prepare this schema'));expect(prepare).toHaveBeenCalledWith('private-id');
 expect(screen.getByText('Publication is a separate governed step')).toBeInTheDocument();
});
test('inventory failure is not reported as empty data',async()=>{
 dataPipelineAPI.analytics.mockRejectedValue(new Error('offline'));render(<AvailableAnalytics/>);
 await screen.findByRole('alert');expect(screen.queryByText('No materialized analytics datasets found')).not.toBeInTheDocument();
});
test('session replacement invalidates late dataset detail',async()=>{
 dataPipelineAPI.analytics.mockResolvedValue({data:{datasets:[{run_id:'r',schema:'parts',business_views:[]}],total:1,next_offset:null}});
 let finish;dataPipelineAPI.analyticsDetail.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
 render(<AvailableAnalytics/>);fireEvent.click(await screen.findByText('Inspect dataset'));
 act(()=>window.dispatchEvent(new Event('depo:session-replaced')));
 await act(async()=>finish({data:{run_id:'r',schema:'OLD',relations:[]}}));
 expect(screen.queryByText('OLD')).not.toBeInTheDocument();
});
