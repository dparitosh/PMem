import React from 'react';
import {render,screen,waitFor} from '@testing-library/react';
import {vi} from 'vitest';
import MemoryRecords from './MemoryRecords';
import {agenticClient} from '../services/agenticApi';
vi.mock('../services/agenticApi',()=>({agenticClient:{get:vi.fn()}}));
vi.mock('../config',()=>({buildSemanticServiceUrl:(service,path)=>path}));
beforeEach(()=>{vi.clearAllMocks();window.history.replaceState(null,'','#/reports?view=memory&job_id=old-turn&ontology_id=parts');});
test('opens the exact retained answer using authorized server-side identity and scope',async()=>{
 agenticClient.get.mockResolvedValue({data:{limit:25,records:[{job_id:'old-turn',user_request:'Bearing tolerance?',response:'Recorded tolerance: 0.01 mm',graph_context:{ontology:'parts'}}]}});
 render(<MemoryRecords/>);
 await screen.findByRole('heading',{name:'Bearing tolerance?',exact:true});
 expect(agenticClient.get).toHaveBeenCalledWith(expect.any(String),expect.objectContaining({params:{job_id:'old-turn',ontology_id:'parts'}}));
 expect(screen.getByText('Read retained answer and context').closest('details')).toHaveAttribute('open');
 expect(screen.getByText('This is the retained answer, not a new analysis.')).toBeVisible();
});
test('missing selected identity is explained without substituting another conversation',async()=>{
 agenticClient.get.mockResolvedValue({data:{limit:25,records:[]}});render(<MemoryRecords/>);
 expect(await screen.findByText(/selected retained conversation is unavailable/)).toBeVisible();
});


test('shows evidence identity separately from an unselected search scope',async()=>{
 agenticClient.get.mockResolvedValue({data:{limit:25,records:[{job_id:'old-turn',user_request:'PMI for it?',response:'25 mm',graph_context:{},retrieval:{grounding:{resolved_identity:{resource_id:'bearing-A',label:'BRG-2001-IR/A Inner race',ontology_id:'engineering-ods'}}}}]}});
 render(<MemoryRecords/>);
 expect(await screen.findByText('BRG-2001-IR/A Inner race')).toBeVisible();
 expect(screen.getByText('All available sources (no single ontology selected)')).toBeVisible();
 expect(screen.getByText('bearing-A')).toBeInTheDocument();
 expect(screen.queryByText('No selected business record')).not.toBeInTheDocument();
});
