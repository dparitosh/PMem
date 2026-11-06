import {agentToolResult,validBridgePolicy} from './agentToolResult';

const policy=()=>({preview_id:'saved',policy:'validated-only-v1',status:'ready',accepted_ids:['a'],held_count:1,decisions:[{candidate_id:'a',decision:'publish',reasons:[]},{candidate_id:'b',decision:'hold',reasons:['ambiguous_target']}]});

test('Governor and Steward share the same completed result envelope contract',()=>{
 const response={data:{agent_id:'ontology-steward',tool_id:'bridge.mapping.evaluate',run_id:'r',status:'completed',result:policy()}};
 expect(agentToolResult(response,'ontology-steward','bridge.mapping.evaluate').result.preview_id).toBe('saved');
 for(const patch of [{status:'running'},{status:'failed'},{agent_id:'ontology-governor'},{run_id:''}]){
  expect(()=>agentToolResult({data:{...response.data,...patch}},'ontology-steward','bridge.mapping.evaluate')).toThrow('incompatible');
 }
});

test('Steward decisions must agree with accepted IDs and the saved preview',()=>{
 expect(validBridgePolicy(policy(),'saved')).toBe(true);
 for(const patch of [{preview_id:'stale'},{accepted_ids:['b']},{accepted_ids:['a','a']},{held_count:0},{status:'held'},{decisions:[{candidate_id:'a',decision:'publish',reasons:['blocked']}]}])expect(validBridgePolicy({...policy(),...patch},'saved')).toBe(false);
});
