import React from 'react';
import {render,screen,fireEvent,act} from '@testing-library/react';
import ReportingReplica from './ReportingReplica';
import {apiClient,dataPipelineAPI} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({apiClient:{get:vi.fn(),post:vi.fn()},dataPipelineAPI:{definitions:vi.fn(),graphSnapshotSources:vi.fn(),runDefinition:vi.fn(),createDefinition:vi.fn(),scheduleDefinition:vi.fn()}}));
vi.mock('../config',()=>({buildUrl:path=>path}));
vi.mock('../services/serviceAuth',()=>({getCredentialProfile:()=> 'scope'}));
const feed={feed_id:'a'.repeat(64),name:'Engineering reporting',status:'approved',freshness:'tracked_feed_caught_up',definition:{ontology_ids:['v1']},state:{trs_after:4,last_assessed_at:'2026-11-12T00:00:00Z'},coverage:'Selected tracked events only'};
const result={feed,total_resources:2,recorded_links:1,metrics_scope:'Recorded counts',types:[{type:'urn:Part',records:2}],resources:[{resource_uri:'urn:one',source_iri:'urn:part:one',name:'Bearing',description:'Bearing assembly'}]};
beforeEach(()=>{vi.clearAllMocks();apiClient.get.mockImplementation(path=>Promise.resolve({data:path.endsWith('/feeds')?{feeds:[feed],scheduling_enabled:false}:result}));dataPipelineAPI.definitions.mockResolvedValue({data:{definitions:[]}});dataPipelineAPI.graphSnapshotSources.mockResolvedValue({data:{sources:[]}});});
test('reporting visualization loads database reports without requesting the graph',async()=>{
 render(<ReportingReplica/>);await screen.findByRole('option',{name:/Engineering reporting/});
 expect(dataPipelineAPI.graphSnapshotSources).not.toHaveBeenCalled();
 fireEvent.change(screen.getByLabelText('Reporting dataset'),{target:{value:feed.feed_id}});
 expect(await screen.findByText('Bearing assembly')).toBeVisible();
 expect(screen.getByText(/Freshness: Tracked changes applied/)).toBeVisible();
 expect(screen.getByLabelText('Part record count')).toHaveAttribute('value','2');
});
test('wrong reporting identity is rejected instead of displayed',async()=>{
 apiClient.get.mockImplementation(path=>Promise.resolve({data:path.endsWith('/feeds')?{feeds:[feed]}:{...result,feed:{...feed,feed_id:'wrong'}}}));
 render(<ReportingReplica/>);await screen.findByRole('option',{name:/Engineering reporting/});
 fireEvent.change(screen.getByLabelText('Reporting dataset'),{target:{value:feed.feed_id}});
 expect(await screen.findByRole('alert')).toHaveTextContent('does not match');
 expect(screen.queryByText('Bearing assembly')).toBeNull();
});
test('reconnect clears selected reporting state and late responses',async()=>{
 let finish;apiClient.get.mockImplementation(path=>path.endsWith('/feeds')?Promise.resolve({data:{feeds:[feed]}}):new Promise(resolve=>{finish=resolve;}));
 render(<ReportingReplica/>);await screen.findByRole('option',{name:/Engineering reporting/});fireEvent.change(screen.getByLabelText('Reporting dataset'),{target:{value:feed.feed_id}});
 await act(async()=>window.dispatchEvent(new Event('depo:credentials-cleared')));
 await act(async()=>finish({data:result}));expect(screen.queryByText('Bearing assembly')).toBeNull();
});
