import React from 'react';
import {vi} from 'vitest';
import {render,screen,fireEvent,act} from '@testing-library/react';
import AvailableAnalytics from './AvailableAnalytics';
import {dataPipelineAPI} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({dataPipelineAPI:{analytics:vi.fn(),analyticsDetail:vi.fn(),analyticsData:vi.fn()}}));
vi.mock('./SemanticDataWorkbench',()=>({default:()=> <p>Catalog-driven analytics</p>}));
beforeEach(()=>vi.resetAllMocks());
test('distinguishes schema designs from loaded and published analytics',async()=>{
 dataPipelineAPI.analytics.mockResolvedValue({data:{datasets:[],total:0,next_offset:null}});
 const prepare=vi.fn();render(<AvailableAnalytics drafts={[{ontology_id:'private-id',label:'Parts design'}]} onPrepare={prepare}/>);
 await screen.findByText('Your reporting data is not ready yet');
 fireEvent.click(screen.getByRole('button',{name:'Prepare data for Parts design'}));expect(prepare).toHaveBeenCalledWith('private-id');
 expect(screen.getByText('Preparing data does not automatically approve or publish it.')).toBeInTheDocument();
});
test('inventory failure is not reported as empty data',async()=>{
 dataPipelineAPI.analytics.mockRejectedValue(new Error('offline'));render(<AvailableAnalytics/>);
 await screen.findByRole('alert');expect(screen.queryByText('Your reporting data is not ready yet')).not.toBeInTheDocument();
});
test('session replacement invalidates late dataset detail',async()=>{
 dataPipelineAPI.analytics.mockResolvedValue({data:{datasets:[{run_id:'r',schema:'parts',business_views:[]}],total:1,next_offset:null}});
 let finish;dataPipelineAPI.analyticsDetail.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
 render(<AvailableAnalytics/>);fireEvent.click(screen.getByText('Other imports and XML analytics'));fireEvent.click(await screen.findByText('Browse data'));
 act(()=>window.dispatchEvent(new Event('depo:session-replaced')));
 await act(async()=>finish({data:{run_id:'r',schema:'OLD',relations:[]}}));
 expect(screen.queryByText('OLD')).not.toBeInTheDocument();
});
