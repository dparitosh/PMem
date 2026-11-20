import React from 'react';
import {render,screen,fireEvent,act} from '@testing-library/react';
import {vi} from 'vitest';
import HomeKnowledgeOverview,{KnowledgePreview} from './HomeKnowledgeOverview';
import {graphApi} from '../services/graphApi';
import {apiClient} from '../services/apiClient';
import {agenticClient} from '../services/agenticApi';
vi.mock('../services/graphApi',()=>({graphApi:{getOverview:vi.fn(),getOntologyGraph:vi.fn()}}));
vi.mock('../services/apiClient',()=>({apiClient:{get:vi.fn()}}));
vi.mock('../services/agenticApi',()=>({agenticClient:{get:vi.fn()}}));
vi.mock('../config',()=>({buildSemanticServiceUrl:(service,path)=>path}));
const graph={nodes:[{elementId:'class:1',label:'Component',type:'class',labels:['Class']},{elementId:'part:1',label:'Bearing',type:'part',properties:{name:'Bearing'}}],links:[{elementId:'link:1',source:'part:1',target:'class:1',type:'rdf:type'}]};
beforeEach(()=>{vi.clearAllMocks();graphApi.getOverview.mockResolvedValue({data:graph});graphApi.getOntologyGraph.mockResolvedValue({data:graph});apiClient.get.mockResolvedValue({data:{records:[{record_key:'merges:1',source_kind:'merges',identifier:'1',title:'Housing change review',review_state:'held',execution_state:'not_started',workspace:'#/change-control'}],coverage:[]}});agenticClient.get.mockResolvedValue({data:{records:[{job_id:'turn:1',user_request:'What requirements apply to Bearing?',graph_context:{ontology:'v1'}}]}});});

test('uses retained reviews and conversations, and real graph records',async()=>{
 render(<HomeKnowledgeOverview/>);
 expect(await screen.findByRole('link',{name:'Housing change review'})).toHaveAttribute('href','#/change-control?source=merges&record=1');
 expect(await screen.findByText('What requirements apply to Bearing?')).toBeVisible();
 expect(await screen.findByRole('button',{name:/Node Bearing\./})).toBeVisible();
 expect(screen.queryByText('DW-60')).toBeNull();
 expect(graphApi.getOverview).toHaveBeenCalledWith(40,expect.any(AbortSignal));
});

test('graph selection and views do not invent classifications',()=>{
 render(<KnowledgePreview data={graph}/>);
 fireEvent.click(screen.getByRole('button',{name:/Node Bearing\./}));
 expect(screen.getByRole('status')).toHaveTextContent('Bearing');
 expect(screen.queryByText(/Select this record in Graph Explorer/)).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Classes',exact:true}));
 expect(screen.getByRole('button',{name:/Node Component\./})).toBeInTheDocument();
 expect(screen.queryByRole('button',{name:/Node Bearing\./})).toBeNull();
});

test('service failures are unavailable rather than fabricated empty data',async()=>{
 graphApi.getOverview.mockRejectedValue(new Error('offline'));apiClient.get.mockRejectedValue(new Error('offline'));agenticClient.get.mockRejectedValue(new Error('offline'));
 render(<HomeKnowledgeOverview/>);
 expect(await screen.findByText('Review evidence unavailable.')).toBeVisible();
 expect(await screen.findByText('Conversation memory unavailable.')).toBeVisible();
 expect(await screen.findByText(/No empty-graph conclusion/)).toBeVisible();
});

test('session changes immediately abort and discard old conversation responses',async()=>{
 let finish;agenticClient.get.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
 const {unmount}=render(<HomeKnowledgeOverview/>);
 await screen.findByText('Housing change review');
 const oldSignal=agenticClient.get.mock.calls[0][1].signal;
 fireEvent(window,new Event('depo:session-replaced'));
 expect(oldSignal.aborted).toBe(true);
 await act(async()=>finish({data:{records:[{job_id:'stale',user_request:'Old private question'}]}}));
 expect(screen.queryByText('Old private question')).toBeNull();unmount();
});

test('shared canvas keeps a connected readable bounded preview and retains the scope link',()=>{
 const nodes=Array.from({length:15},(_,i)=>({elementId:`part:${i}`,labels:['Part'],properties:{name:`Part ${i}`}}));
 const data={nodes,links:[{elementId:'rel:1',source:'part:0',target:'part:14',type:'PART_OF'}]};
 render(<KnowledgePreview data={data} ontologyId="scope/one"/>);
 expect(screen.getAllByRole('button',{name:/^Node Part /})).toHaveLength(10);
 expect(screen.getByRole('link',{name:'Open full graph →'})).toHaveAttribute('href','#/graph?ontology_id=scope%2Fone');
 expect(document.querySelectorAll('.link').length).toBeGreaterThan(0);
 expect(nodes[0].x).toBeUndefined();
 expect(data.links[0].source).toBe('part:0');
});

test('zoom toolbar changes the existing canvas transform without replacing its nodes',()=>{
 render(<KnowledgePreview data={graph}/>);
 const svg=document.querySelector('svg.graph-canvas');
 const node=screen.getByRole('button',{name:/Node Bearing\./});
 const initial=svg.__zoom.k;
 fireEvent.click(screen.getByRole('button',{name:'Zoom in',exact:true}));
 expect(svg.__zoom.k).toBeCloseTo(initial*1.4);
 expect(screen.getByRole('button',{name:/Node Bearing\./})).toBe(node);
 fireEvent.click(screen.getByRole('button',{name:'Zoom out',exact:true}));
 expect(svg.__zoom.k).toBeCloseTo(initial);
});


test('filter labels describe actual resource membership and selected nodes propagate',()=>{
 const selected=vi.fn();
 const data={nodes:[...graph.nodes,{elementId:'property:1',labels:['ObjectProperty'],properties:{name:'hasPart'}}],links:graph.links};
 render(<KnowledgePreview data={data} onSelectNode={selected}/>);
 expect(screen.queryByRole('button',{name:'Bridge view'})).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:/Node Bearing\./}));
 expect(selected).toHaveBeenLastCalledWith(expect.objectContaining({elementId:'part:1'}));
 fireEvent.click(screen.getByRole('button',{name:'Other resources',exact:true}));
 expect(screen.getByRole('button',{name:/Node hasPart\./})).toBeVisible();
 expect(selected).toHaveBeenLastCalledWith(null);
 expect(screen.queryByRole('button',{name:/Node Component\./})).toBeNull();
});

test('memory uses server-side scope and a small summary; retained entries carry exact identity',async()=>{
 render(<HomeKnowledgeOverview ontologyId="v1"/>);
 const link=await screen.findByRole('link',{name:'What requirements apply to Bearing?'});
 expect(link).toHaveAttribute('href','#/reports?view=memory&job_id=turn%3A1&ontology_id=v1');
 expect(agenticClient.get).toHaveBeenCalledWith(expect.any(String),expect.objectContaining({params:{ontology_id:'v1',limit:3,summary:true}}));
});

test('compact graph labels stay readable at auto-fit scale',()=>{
 render(<KnowledgePreview data={graph}/>);
 const svg=document.querySelector('svg.graph-canvas'),label=svg.querySelector('.node-label');
 expect(parseFloat(label.style.fontSize)*svg.__zoom.k).toBeGreaterThanOrEqual(10.99);
});
