import React from 'react';
import {vi} from 'vitest';
import {render,screen,fireEvent,act,waitFor} from '@testing-library/react';
import AvailableAnalytics from './AvailableAnalytics';
import XmlAnalyticsLoader from './XmlAnalyticsLoader';
import {apiClient,dataPipelineAPI} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({apiClient:{get:vi.fn(),post:vi.fn()},dataPipelineAPI:{analytics:vi.fn(),analyticsDetail:vi.fn(),analyticsData:vi.fn()}}));
vi.mock('../config',()=>({buildSemanticServiceUrl:(_service,path)=>path}));
vi.mock('../services/serviceAuth',()=>({getCredentialProfile:()=>''}));
beforeEach(()=>{vi.resetAllMocks();sessionStorage.clear();});
// Regression tests for the confirmed audit defects.
test('AUD-01 source handoff must invalidate an older schema-resolution response',async()=>{
 let finish;apiClient.get.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
 const sources=[{ontology_id:'a',label:'Schema A'},{ontology_id:'b',label:'Schema B'}];
 const view=render(<XmlAnalyticsLoader sources={sources} selectedSchemaId="a"/>);
 fireEvent.click(screen.getByText('Use selected schema'));
 view.rerender(<XmlAnalyticsLoader sources={sources} selectedSchemaId="b"/>);
 await act(async()=>finish({data:{schema_artifact_id:'artifact-A'}}));
 expect(screen.getByLabelText('Source schema')).toHaveValue('b');
 expect(screen.getByLabelText('Retained XSD artifact ID')).not.toHaveValue('artifact-A');
});
test('AUD-02 an out-of-range page must not claim that the database is empty',async()=>{
 dataPipelineAPI.analytics.mockResolvedValueOnce({data:{datasets:[{run_id:'r',schema:'s',business_views:[]}],total:21,next_offset:20}})
 .mockResolvedValueOnce({data:{datasets:[],total:1,next_offset:null}})
 .mockResolvedValueOnce({data:{datasets:[{run_id:'remaining',schema:'remaining-dataset',business_views:[]}],total:1,next_offset:null}});
 render(<AvailableAnalytics/>);await screen.findByText('Inspect dataset');
 fireEvent.click(screen.getByText('Next datasets'));
 await waitFor(()=>expect(dataPipelineAPI.analytics).toHaveBeenCalledTimes(2));
 await screen.findByText('remaining-dataset');
 expect(screen.getByText('Page 1')).toBeInTheDocument();
 expect(screen.queryByText('No materialized analytics datasets found')).not.toBeInTheDocument();
});
