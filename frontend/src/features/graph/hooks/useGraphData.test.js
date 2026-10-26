import { act, renderHook } from '@testing-library/react';
import useGraphData from './useGraphData';
const api=vi.hoisted(()=>({getOntologyGraph:vi.fn(),getArchitectureGraph:vi.fn()}));
vi.mock('../../../services/graphApi',()=>({graphApi:api}));
vi.mock('../../../utils/logger',()=>({logger:{render:vi.fn(),ontology:vi.fn(),error:vi.fn()}}));
function options(){return {initialData:{nodes:[],links:[]},commitGraphSlice:vi.fn(),searchModeRef:{current:false},setStepParts:vi.fn(),setSelectedStepPart:vi.fn(),scopeKey:'ontology:A',limit:100};}
const payload=id=>({data:{nodes:[{elementId:id,labels:['Class'],properties:{name:id}}],relationships:[]}});
beforeEach(()=>vi.clearAllMocks());

test('an unavailable process response is not presented as an empty model', async()=>{
 api.getArchitectureGraph.mockResolvedValue({data:{status:'unavailable',nodes:[],relationships:[]}});
 const props=options(),view=renderHook(()=>useGraphData(props));
 await act(async()=>{await view.result.current.fetchArchitectureGraph();});
 expect(view.result.current.ontologyGraphMessage).toContain('Process graph unavailable');
 expect(view.result.current.ontologyGraphMessage).not.toContain('Import an ArchiMate');
});
test('new graph scope aborts old reads and only the current scope commits',async()=>{
 const pending=[];api.getOntologyGraph.mockImplementation((id,limit,signal)=>new Promise(resolve=>pending.push({id,signal,resolve})));
 const props=options(),view=renderHook(p=>useGraphData(p),{initialProps:props});
 let first,second;
 act(()=>{first=view.result.current.fetchOntologyGraph('A');second=view.result.current.fetchOntologyGraph('B');});
 expect(pending[0].signal.aborted).toBe(true);
 props.commitGraphSlice.mockClear();
 await act(async()=>{pending[1].resolve(payload('B'));await second;});
 await act(async()=>{pending[0].resolve(payload('A'));await first;});
 expect(props.commitGraphSlice).toHaveBeenCalledTimes(1);
 expect(props.commitGraphSlice.mock.calls[0][0].nodes[0].elementId).toBe('B');
});
test('route unmount aborts the read and prevents a late graph commit',async()=>{
 let resolve,signal;api.getArchitectureGraph.mockImplementation((id,limit,s)=>{signal=s;return new Promise(r=>{resolve=r;});});
 const props=options(),view=renderHook(()=>useGraphData(props));let pending;
 act(()=>{pending=view.result.current.fetchArchitectureGraph();});
 props.commitGraphSlice.mockClear();
 view.unmount();expect(signal.aborted).toBe(true);
 await act(async()=>{resolve(payload('late'));await pending;});
 expect(props.commitGraphSlice).not.toHaveBeenCalled();
});
test('callback updates do not restart graph loading and use the current commit handler',async()=>{
 let resolve;api.getOntologyGraph.mockImplementation(()=>new Promise(r=>{resolve=r;}));
 const props=options(),view=renderHook(p=>useGraphData(p),{initialProps:props});const load=view.result.current.fetchOntologyGraph;
 let pending;act(()=>{pending=load('A');});
 props.commitGraphSlice.mockClear();
 const next=vi.fn();view.rerender({...props,commitGraphSlice:next});
 expect(view.result.current.fetchOntologyGraph).toBe(load);
 await act(async()=>{resolve(payload('A'));await pending;});
 expect(next).toHaveBeenCalledTimes(1);expect(props.commitGraphSlice).not.toHaveBeenCalled();
});

test('loading a different ontology never leaves the previous graph visible after failure',async()=>{
 let reject;api.getOntologyGraph.mockImplementation(()=>new Promise((resolve,r)=>{reject=r;}));
 const props=options();let visible={nodes:[{elementId:'old-ontology'}],links:[]};
 props.commitGraphSlice.mockImplementation(graph=>{visible=graph;});
 const view=renderHook(()=>useGraphData(props));let pending;
 act(()=>{pending=view.result.current.fetchOntologyGraph('new-ontology');});
 expect(visible.nodes).toHaveLength(0);
 await act(async()=>{reject(new Error('Graph service unavailable'));await pending;});
 expect(visible.nodes).toHaveLength(0);
 expect(view.result.current.ontologyGraphMessage).toContain('Graph service unavailable');
});
