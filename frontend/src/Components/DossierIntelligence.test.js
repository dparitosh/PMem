import React from 'react';
import {render,screen,fireEvent,waitFor,act} from '@testing-library/react';
import {vi} from 'vitest';
import DossierIntelligence from './DossierIntelligence';
import {apiClient} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({apiClient:{get:vi.fn()}}));
vi.mock('../config',()=>({buildSemanticServiceUrl:(_,path)=>path}));
const record={record_key:'decisions:a',source_kind:'decisions',identifier:'a'};
const data={schema_version:1,record_key:'decisions:a',scope:'Selected record only',persistence:'Retained PostgreSQL evidence',integrity_scope:'Projection only',authorization:'Read-only evidence',snapshot_sha256:'snapshot-digest',provenance_turtle:'@prefix prov: <http://www.w3.org/ns/prov#> .',
 graph:{nodes:[{id:'record',type:'EvidenceRecord',content:'Selected assessment'},{id:'reference',type:'SourceReference',content:'digest-1'}],edges:[{source:'record',target:'reference',type:'HAS_EVIDENCE'}]},
 decisions:[{id:'decision-1',scenario:'Review mapping',outcome:'flagged',decision_maker:'reviewer',reasoning:'Source evidence',confidence:null,timestamp:null}],
 provenance:[{field:'policy_digest',value:'digest-1',source_uri:'https://example/assessment'}]};
beforeEach(()=>apiClient.get.mockReset().mockResolvedValue({data}));
test('context, decisions and provenance use the same selected dossier',async()=>{
 render(<DossierIntelligence record={record}/>);
 expect(await screen.findByRole('group',{name:'Selected dossier context graph'})).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'Inspect SourceReference: digest-1'}));expect(screen.getByText('reference')).toBeVisible();
 fireEvent.click(screen.getByRole('tab',{name:'Decisions'}));
 expect(screen.getByText('Review mapping')).toBeVisible();expect(screen.getByText(/Confidence: Not established/)).toBeVisible();
 fireEvent.click(screen.getByRole('tab',{name:'Provenance'}));expect(screen.getByText('snapshot-digest')).toBeVisible();
 expect(screen.getByRole('button',{name:'Download PROV-O evidence'})).toBeEnabled();
 expect(apiClient.get).toHaveBeenCalledOnce();
});
test('mismatched evidence never becomes a valid semantic view',async()=>{
 apiClient.get.mockResolvedValue({data:{...data,record_key:'decisions:another'}});
 render(<DossierIntelligence record={record}/>);
 expect(await screen.findByRole('alert')).toHaveTextContent('different or invalid evidence');
 expect(screen.queryByRole('group')).toBeNull();
});
test('changing the selected record aborts and ignores late context',async()=>{
 let finish;apiClient.get.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;})).mockResolvedValue({data:{...data,record_key:'decisions:b'}});
 const view=render(<DossierIntelligence record={record}/>);const signal=apiClient.get.mock.calls[0][1].signal;
 view.rerender(<DossierIntelligence record={{...record,identifier:'b',record_key:'decisions:b'}}/>);
 await screen.findByRole('group');expect(signal.aborted).toBe(true);
 await act(async()=>finish({data:{...data,scope:'Wrong old context'}}));expect(screen.queryByText('Wrong old context')).toBeNull();
});
test('evidence tabs support keyboard selection',async()=>{
 render(<DossierIntelligence record={record}/>);await screen.findByRole('group');
 fireEvent.keyDown(screen.getByRole('tab',{name:'Context'}),{key:'ArrowRight'});
 expect(screen.getByRole('tab',{name:'Decisions'})).toHaveFocus();expect(screen.getByText('Review mapping')).toBeVisible();
});

test('a changed retained revision cannot be mixed with the selected dossier',async()=>{
 apiClient.get.mockResolvedValue({data:{...data,source_snapshot:{source_status:'failed'}}});
 render(<DossierIntelligence record={{...record,source_status:'completed'}}/>);
 expect(await screen.findByRole('alert')).toHaveTextContent('changed after selection');
 expect(screen.queryByRole('group',{name:'Selected dossier context graph'})).toBeNull();
});


test('refreshing the same record retrieves its new retained revision',async()=>{
 apiClient.get.mockResolvedValueOnce({data:{...data,source_snapshot:{updated_at:'old'}}})
  .mockResolvedValueOnce({data:{...data,source_snapshot:{updated_at:'new'},scope:'Current refreshed evidence'}});
 const view=render(<DossierIntelligence record={{...record,updated_at:'old'}}/>);
 await screen.findByRole('group');
 view.rerender(<DossierIntelligence record={{...record,updated_at:'new'}}/>);
 expect(await screen.findByText('Current refreshed evidence')).toBeVisible();
 expect(apiClient.get).toHaveBeenCalledTimes(2);
});
