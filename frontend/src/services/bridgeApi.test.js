import {vi} from 'vitest';
vi.mock('./agenticApi',()=>({default:{runAgent:vi.fn()}}));
import agenticAPI from './agenticApi';
import {bridgeApi} from './bridgeApi';

test('Semantic Bridge accepts only the completed Steward decision for its saved preview',async()=>{
 const result={preview_id:'saved',policy:'validated-only-v1',status:'held',accepted_ids:[],held_count:1,decisions:[{candidate_id:'a',decision:'hold',reasons:['ambiguous_target']}]};
 const envelope={agent_id:'ontology-steward',tool_id:'bridge.mapping.evaluate',run_id:'steward',status:'completed',result};
 agenticAPI.runAgent.mockResolvedValue({data:envelope});
 expect((await bridgeApi.evaluate('saved')).data.held_count).toBe(1);
 for(const patch of [{status:'running'},{run_id:''},{agent_id:'ontology-governor'},{result:{...result,preview_id:'stale'}}]){
  agenticAPI.runAgent.mockResolvedValue({data:{...envelope,...patch}});
  await expect(bridgeApi.evaluate('saved')).rejects.toThrow('incompatible');
 }
});
