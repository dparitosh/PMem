import {performance} from 'node:perf_hooks';
import {buildOntologyGroups} from '../src/features/graph/ontologyGroups.js';
import {fitGraphViewport} from '../src/features/graph/graphViewport.js';
// CPU-only preparation benchmark; this does not measure browser rendering or FPS.
const results=[];
for (const count of [750,10000,100000]) {
 const nodes=Array.from({length:count},(_,i)=>({elementId:String(i),ontology_id:`ontology-${i%5}`,x:i*3,y:i%80}));
 const links=nodes.slice(1).map((n,i)=>({source:String(i),target:n.elementId,type:'MAPS_TO'}));
 const timings=[];
 for(let repeat=0;repeat<10;repeat++) {
  const start=performance.now();buildOntologyGroups({nodes,links});fitGraphViewport(nodes,1200,600);timings.push(performance.now()-start);
 }
 timings.sort((a,b)=>a-b);
 results.push({nodes:count,links:links.length,median_ms:Number(timings[5].toFixed(2)),max_ms:Number(timings[9].toFixed(2))});
}
console.log(JSON.stringify({scope:'CPU grouping and viewport preparation only; synthetic five-ontology data; no browser/FPS or database certification',results},null,2));
