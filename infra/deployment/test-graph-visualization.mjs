import assert from 'node:assert/strict';
import fs from 'node:fs';
const load = async (path) => import(`data:text/javascript;base64,${Buffer.from(fs.readFileSync(path,'utf8')).toString('base64')}`);
const common = await load('frontend/src/types/commonGraph.js');
const mapped = common.normalizeCommonGraph({nodes:[{id:'a'},{id:'b'}],links:[{source:{elementId:'a'},target:{id:'b'},type:'LINK'}]});
assert.equal(mapped.links.length,1);
assert.equal(mapped.links[0].source,'a');
assert.equal(common.normalizeCommonLink({source:0,target:'b'}).source,'0');
const utils = await load('frontend/src/utils/graphUtils.js');
for (const options of [{},{collapseHiddenBridges:true}]) {
 const graph=utils.normalizeGraphDataset({nodes:[{elementId:'a',labels:['Part']}],relationships:[],counts:{nodes:99},view:'bounded',root:{elementId:'a'},status:'ok'}, options);
 assert.equal(graph.counts.nodes,99);
 assert.equal(graph.root.elementId,'a');
 assert.equal(graph.nodes.length,1);
}
let source=fs.readFileSync('frontend/src/services/graphApi.js','utf8').replace(/^import .*;\r?\n/gm,'');
const responses=[{data:{errors:[{message:'query failed'}]}},{data:{data:{contextualResult:{nodes:[]}}}}];
source='const buildSemanticServiceUrl = (service,path) => path; const apiClient={post:async()=>globalThis.__graphResponse};\n'+source;
const api=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
globalThis.__graphResponse=responses[0];
await assert.rejects(api.graphApi.getContextualSubgraph(),/query failed/);
globalThis.__graphResponse=responses[1];
assert.deepEqual((await api.graphApi.getContextualSubgraph()).data.nodes,[]);
delete globalThis.__graphResponse;
console.log('PASS: object relationship endpoints, zero IDs, preserved graph metadata and explicit GraphQL errors.');
