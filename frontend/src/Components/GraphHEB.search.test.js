import React from 'react';
import {act,render,screen,fireEvent,waitFor} from '@testing-library/react';
import GraphHEB, {sanitizeContextualGraph, normalizeGraphDataset} from "../features/graph/GraphWorkspace.js";
import {graphApi} from '../services/graphApi';
import {apiClient} from '../services/apiClient';
// This suite exercises request and display-state ownership. D3/SVG lifecycle is
// covered in GraphCanvas.test.js; jsdom does not implement SVG viewBox.baseVal.
vi.mock('../features/graph/GraphCanvas.js',async()=>{
 const {forwardRef}=await import('react');
 return {default:forwardRef(({model,actions},ref)=><><output data-testid="rendered-node-count">{model.activeDisplayData.nodes.length}</output><button onClick={()=>actions.openTooltipRecommendation('change-impact','Motor',{nodeId:'revision-a',ontologyId:'selected'})}>Test impact A</button><button onClick={()=>actions.openTooltipRecommendation('change-impact','Motor',{nodeId:'revision-b',ontologyId:'selected'})}>Test impact B</button></>)};
});
const catalog = vi.hoisted(()=>({rows:[]}));
vi.mock('../contexts/OntologyContext',()=>({useOntologies:()=>({ontologies:catalog.rows,loading:false,error:null})}));
vi.mock('../services/apiClient',()=>({apiClient:{post:vi.fn()},platformAPI:{health:vi.fn().mockResolvedValue({data:{status:'ok'}})}}));
vi.mock('../services/graphApi',()=>{
 const api={getOverview:vi.fn(),getOntologyGraph:vi.fn(),getArchitectureGraph:vi.fn(),getStepParts:vi.fn(),searchUniversal:vi.fn()};
 api.getContextualSubgraph=vi.fn((params,signal)=>api.searchUniversal(params.search,{instances_only:true,...(params.ontologyPrefix?{scope:params.ontologyPrefix}:{})},signal));
 api.getTraversal=vi.fn(async()=>api.searchUniversal.mock.results.at(-1)?.value || {data:{nodes:[],relationships:[]}});
 return {graphApi:api};
});
vi.mock('../utils/logger',()=>({logger:{error:vi.fn(),warn:vi.fn(),info:vi.fn(),debug:vi.fn(),data:vi.fn(),render:vi.fn(),ontology:vi.fn(),api:vi.fn()}}));
test('overview search keeps the query visible and requests connected business context',async()=>{
 const empty={data:{nodes:[],relationships:[],view:{}}};
 graphApi.getOverview.mockResolvedValue(empty);graphApi.getOntologyGraph.mockResolvedValue(empty);
 graphApi.searchUniversal.mockResolvedValue(empty);
 const update=vi.fn();
 render(<GraphHEB setData={update} setSearchResults={update} setActiveTab={update} setVisibleRelationships={update}/>);
 const input=await screen.findByRole('textbox',{name:'Search graph'});
 await screen.findByText('No Graph Data Available');
 fireEvent.change(input,{target:{value:'PART_OF'}});
 fireEvent.click(screen.getByRole('button',{name:'Search'}));
 await waitFor(()=>expect(graphApi.getContextualSubgraph).toHaveBeenCalledWith(expect.objectContaining({search:'PART_OF',searchMode:'best',limit:24}),expect.anything()),{timeout:2000});
 expect(input).toHaveValue('PART_OF');
});

test('graph recommendation requests preserve identity without invalid nested scope and ignore late results',async()=>{
 graphApi.getOverview.mockResolvedValue({data:{nodes:[{elementId:'node',labels:['Part'],properties:{name:'Motor'}}],relationships:[],view:{}}});
 let resolveA,resolveB;
 apiClient.post.mockImplementationOnce(()=>new Promise(resolve=>{resolveA=resolve;})).mockImplementationOnce(()=>new Promise(resolve=>{resolveB=resolve;}));
 render(<GraphHEB setData={vi.fn()} setSearchResults={vi.fn()} setActiveTab={vi.fn()} setVisibleRelationships={vi.fn()}/>);
 fireEvent.click(await screen.findByRole('button',{name:'Entity graph'}));
 fireEvent.click(await screen.findByRole('button',{name:'Test impact A'}));
 const first=apiClient.post.mock.calls.at(-1);
 expect(first[1]).toMatchObject({node_id:'revision-a',scope:{ontology_id:'selected'}});
 expect(first[1].scope).not.toHaveProperty('node_id');
 fireEvent.click(screen.getByRole('button',{name:'Test impact B'}));
 expect(first[2].signal.aborted).toBe(true);
 await act(async()=>resolveB({data:{message:'Evidence for revision B'}}));
 await screen.findByText('Evidence for revision B');
 await act(async()=>resolveA({data:{message:'Wrong revision A'}}));
 expect(screen.queryByText('Wrong revision A')).toBeNull();
});

test('search legend describes the visible result instead of the background overview',async()=>{
 const first={elementId:'bearing',labels:['Part'],properties:{name:'Bearing'}};
 const second={elementId:'motor',labels:['Part'],properties:{name:'Motor'}};
 graphApi.getOverview.mockResolvedValue({data:{nodes:[first,second],relationships:[],view:{}}});
 graphApi.searchUniversal.mockResolvedValue({data:{nodes:[first],relationships:[],view:{}}});
 render(<GraphHEB setData={vi.fn()} setSearchResults={vi.fn()} setActiveTab={vi.fn()} setVisibleRelationships={vi.fn()}/>);
 await screen.findByText('Visible overview slice');
 fireEvent.change(screen.getByRole('textbox',{name:'Search graph'}),{target:{value:'Bearing'}});
 fireEvent.click(screen.getByRole('button',{name:'Search'}));
 await waitFor(()=>expect(graphApi.searchUniversal).toHaveBeenCalledWith('Bearing',expect.anything(),expect.anything()),{timeout:3000});
 const label=await screen.findByText('Search results',{}, {timeout:3000});
 await waitFor(()=>expect(label.parentElement).toHaveTextContent('1 nodes'));
 expect(label.parentElement).not.toHaveTextContent('2 nodes');
});

test('a slow initial overview cannot clear or replace a completed user search',async()=>{
 let resolveOverview;
 graphApi.getOverview.mockImplementation(()=>new Promise(resolve=>{resolveOverview=resolve;}));
 const first={elementId:'bearing',labels:['Part'],properties:{name:'Bearing'}};
 const second={elementId:'motor',labels:['Part'],properties:{name:'Motor'}};
 graphApi.searchUniversal.mockResolvedValue({data:{nodes:[first],relationships:[],view:{}}});
 render(<GraphHEB setData={vi.fn()} setSearchResults={vi.fn()} setActiveTab={vi.fn()} setVisibleRelationships={vi.fn()}/>);
 const input=await screen.findByRole('textbox',{name:'Search graph'});
 fireEvent.change(input,{target:{value:'Bearing'}});
 fireEvent.click(screen.getByRole('button',{name:'Search'}));
 const label=await screen.findByText('Search results',{}, {timeout:3000});
 await waitFor(()=>expect(label.parentElement).toHaveTextContent('1 nodes'));
 await act(async()=>{ resolveOverview({data:{nodes:[first,second],relationships:[],view:{}}}); });
 await waitFor(()=>expect(screen.getByText('Search results').parentElement).toHaveTextContent('1 nodes'));
 expect(input).toHaveValue('Bearing');
 expect(screen.queryByText('Visible overview slice')).not.toBeInTheDocument();
});


test('Instances has no overview grouping controls or hidden preferred ontology filter',async()=>{
 catalog.rows=[{value:'ap242-version',prefix:'domain_model',label:'AP242',relationship_count:0}];
 const empty={data:{nodes:[],relationships:[],view:{}}};
 graphApi.getOverview.mockResolvedValue(empty);graphApi.searchUniversal.mockResolvedValue(empty);
 render(<GraphHEB setData={vi.fn()} setSearchResults={vi.fn()} setActiveTab={vi.fn()} setVisibleRelationships={vi.fn()}/>);
 fireEvent.click(await screen.findByRole('button',{name:'Contextual Instances'}));
 expect(screen.queryByRole('group',{name:'Overview presentation'})).toBeNull();
 fireEvent.change(screen.getByRole('textbox',{name:'Search graph'}),{target:{value:'Bearing issue'}});
 fireEvent.click(screen.getByRole('button',{name:'Search'}));
 await waitFor(()=>expect(graphApi.searchUniversal).toHaveBeenCalledWith('Bearing issue',expect.objectContaining({instances_only:true}),expect.anything()),{timeout:3000});
 const call=graphApi.searchUniversal.mock.calls.find(c=>c[0]==='Bearing issue');
 expect(call[1].scope).toBeUndefined();
 catalog.rows=[];
});


test('a no-match instance search clears the previously traversed neighborhood',async()=>{
 catalog.rows=[];
 const empty={data:{nodes:[],relationships:[],view:{}}};
 const hit={data:{nodes:[{elementId:'assembly',labels:['Part'],properties:{name:'Assembly'}}],relationships:[],view:{}}};
 graphApi.getOverview.mockResolvedValue(empty);graphApi.getTraversal.mockResolvedValue(hit);
 graphApi.searchUniversal.mockImplementation(query=>Promise.resolve(query==='Assembly'?hit:empty));
 render(<GraphHEB setData={vi.fn()} setSearchResults={vi.fn()} setActiveTab={vi.fn()} setVisibleRelationships={vi.fn()}/>);
 fireEvent.click(await screen.findByRole('button',{name:'Contextual Instances'}));
 const input=screen.getByRole('textbox',{name:'Search graph'});
 fireEvent.change(input,{target:{value:'Assembly'}});fireEvent.click(screen.getByRole('button',{name:'Search'}));
 await waitFor(()=>expect(screen.getByTestId('rendered-node-count')).toHaveTextContent('1'),{timeout:3000});
 fireEvent.change(input,{target:{value:'No matching record'}});fireEvent.click(screen.getByRole('button',{name:'Search'}));
 await waitFor(()=>expect(screen.getByTestId('rendered-node-count')).toHaveTextContent('0'),{timeout:3000});
 expect(screen.getByText('No Results Found')).toBeVisible();
 expect(screen.queryByText(/Investigate with agent.*Assembly/)).toBeNull();
});


test('context keeps PLMXML master revision trace record and related revision across three source hops',()=>{
 const nodes=[{elementId:'master',labels:['Part']},{elementId:'revision',labels:['Part']},{elementId:'trace',labels:['GeneralRelation'],properties:{name:'FND_TraceLink'}},{elementId:'child',labels:['Part']},{elementId:'unrelated',labels:['Part']},{elementId:'technical-user',labels:['User'],properties:{name:'TCSDTLab_SOL'}}];
 const links=[{elementId:'u',source:'master',target:'technical-user',type:'ACCESS_OWNER'},{elementId:'m',source:'master',target:'revision',type:'MASTER_REF'},{elementId:'t',source:'revision',target:'trace',type:'FND_TRACELINK'},{elementId:'c',source:'trace',target:'child',type:'RELATEDREFS'}];
 const graph=normalizeGraphDataset({nodes,links},{collapseHiddenBridges:true});
 const context=sanitizeContextualGraph(graph,'master');
 expect(context.nodes.map(n=>n.elementId).sort()).toEqual(['child','master','revision']);
 expect(context.links).toHaveLength(2);
 expect(context.links.some(link=>link.type==='SOURCE_PATH'&&link.properties.via_node_id==='trace')).toBe(true);
});


test('AP242 contextual traversal retains typed product and shape objects without admitting substring roles', () => {
 const nodes = [
  {elementId:'root', labels:['Part']},
  {elementId:'definition', labels:['PRODUCT_DEFINITION']},
  {elementId:'shape', labels:['SHAPE_REPRESENTATION']},
  {elementId:'false-flag', labels:['User'], properties:{is_cad_business_object:'false'}},
  {elementId:'substring', labels:['User'], properties:{semantic_role:'department'}},
  {elementId:'disconnected', labels:['PRODUCT_DEFINITION']},
 ];
 const links = ['definition','shape','false-flag','substring'].map(id=>({elementId:`r-${id}`,source:'root',target:id,type:'RELATED_TO'}));
 const context=sanitizeContextualGraph({nodes,links},'root');
 expect(context.nodes.map(n=>n.elementId).sort()).toEqual(['definition','root','shape']);
 expect(context.links).toHaveLength(2);
});
