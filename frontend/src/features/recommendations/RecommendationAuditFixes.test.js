// Regression cases reproduced by the recommendation tab audit.
import React from 'react';
import { render, screen, fireEvent, within, cleanup, act } from '@testing-library/react';
import { afterEach, test, expect, vi } from 'vitest';
import { ChangeImpactResult } from './ChangeImpactResult';
import { SimilarPartsResult } from './SimilarPartsResult';
import { ManufacturingResult } from './ManufacturingResult';
import { AIInsightBanner } from './AIInsightBanner';
import { ProcessFlowTimeline } from './RecommendationVisuals';
import { normalizeRecommendationResult } from './services/recommendationPresentation';

afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();});

test('AUDIT-CI-01 canonical assembly names remain visible in Assembly Impact',()=>{
 const row={node_id:'assembly-1',name:'Motor Assembly',depth:1,path:[],path_names:['Part','Motor Assembly'],configuration_review:[]};
 render(<ChangeImpactResult data={{change_entity:{node_id:'part-1',name:'Part'},assembly_impact:[row],realization_chain:[row]}}/>);
 fireEvent.click(screen.getByRole('tab',{name:'Assembly Impact'}));
 const table=screen.getAllByRole('table').at(-1);
 expect(within(table).getAllByRole('row')[1].cells[0]).toHaveTextContent('Motor Assembly');
});

test('AUDIT-SP-01 malformed comparison entries must be rejected before rendering',()=>{
 expect(()=>normalizeRecommendationResult('similar-parts',{source_part:{name:'Part'},similar_parts:[{name:'Candidate',similarity_score:20,engineering_comparisons:[{property:'material',status:'match'}]}]})).toThrow(/invalid evidence/);
});

test('AUDIT-CI-02 malformed configuration entries must be rejected before rendering',()=>{
 expect(()=>normalizeRecommendationResult('change-impact',{change_entity:{name:'Part'},realization_chain:[{name:'Assembly',configuration_review:[{property:'revision',status:'match'}]}]})).toThrow(/invalid evidence/);
});

test('AUDIT-PC-01 unavailable process categories must not claim measured zero',()=>{
 render(<ManufacturingResult data={{part:{name:'Part'},direct_processes:[],process_instances:[],related_part_processes:[],process_summary:{total_direct:0,total_instances:0,total_related:0},traceability:'Direct recorded neighbors only'}}/>);
 fireEvent.click(screen.getByRole('tab',{name:'Process Instances'}));
 expect(within(screen.getByRole('tabpanel')).getByText(/not assessed/i)).toBeVisible();
});

test('AUDIT-PC-03 process summary banner preserves unassessed categories',()=>{
 const {rerender}=render(<AIInsightBanner service="manufacturing" data={{part:{name:'Part'},direct_processes:[],process_summary:{total_direct:0,total_instances:0,total_related:0}}}/>);
 expect(screen.getAllByText('Not assessed')).toHaveLength(2);
 expect(screen.getByText('Recorded direct process links: 0 in this result')).toBeVisible();
 rerender(<AIInsightBanner service="manufacturing" data={{part:{name:'Part'},assessment:{process_instances:'assessed',related_processes:'assessed'},process_summary:{total_direct:0,total_instances:0,total_related:0}}}/>);
 expect(screen.queryByText('Not assessed')).toBeNull();
 expect(screen.getByText('Recorded process links: 0 in this result')).toBeVisible();
});

test('AUDIT-PC-04 empty timeline does not claim that unassessed links are absent',()=>{
 render(<ProcessFlowTimeline data={{part:{name:'Part'},direct_processes:[]}}/>);
 expect(screen.getByText(/Unassessed categories do not establish that process links are absent/)).toBeVisible();
});

test('AUDIT-PC-02 process visualization never creates negative rectangle widths',()=>{
 vi.spyOn(SVGElement.prototype,'clientWidth','get').mockReturnValue(150);
 const {container}=render(<ProcessFlowTimeline data={{part:{name:'Part'},direct_processes:[{process_name:'Machining'}]}}/>);
 expect([...container.querySelectorAll('rect')].every(rect=>Number(rect.getAttribute('width'))>=0)).toBe(true);
});

test('AUDIT-SP-02 default overview exposes candidate truncation before opening results',()=>{
 render(<SimilarPartsResult data={{source_part:{name:'Part'},similar_parts:[],coverage:{limit_reached:true},ranking_scope:'Only 200 candidates examined'}}/>);
 expect(screen.getByText(/candidate limit was reached/i)).toBeVisible();
});

test('AUDIT-UX-01 result subtabs expose accessible selected state',()=>{
 render(<SimilarPartsResult data={{source_part:{name:'Part'},similar_parts:[]}}/>);
 expect(screen.getByRole('tab',{name:'Overview',selected:true})).toBeVisible();
});

test('AUDIT-SP-03 normalized partial comparison must render safely',()=>{
 vi.spyOn(console,'error').mockImplementation(()=>{});
 const data={source_part:{name:'Part'},similar_parts:[{name:'Candidate',similarity_score:20,engineering_comparisons:[{property:'material',status:'match'}]}]};
 render(<SimilarPartsResult data={data}/>);
 expect(()=>fireEvent.click(screen.getByRole('tab',{name:'Similar Parts'}))).not.toThrow();
});

test('AUDIT-CI-03 normalized partial configuration must render safely',()=>{
 vi.spyOn(console,'error').mockImplementation(()=>{});
 const data={change_entity:{node_id:'root',name:'Part'},realization_chain:[{name:'Assembly',configuration_review:[{property:'revision',status:'match'}]}]};
 expect(()=>render(<ChangeImpactResult data={data}/>)).not.toThrow();
});

test('all result subtabs render with complete normal evidence',()=>{
 const row={node_id:'child',name:'Assembly',assembly_name:'Assembly',process_name:'Machining',path:[],path_names:['Part','Assembly'],configuration_review:[],engineering_comparisons:[],similarity_score:35};
 for(const [Component,data,labels] of [
  [ChangeImpactResult,{change_entity:{node_id:'root',name:'Part'},realization_chain:[row],impacted_parts:[row],assembly_impact:[row],impacted_requirements:[row],process_impacts:[row]},['Overview','Impacted Parts','Assembly Impact','Requirements','Processes','Realization Chain']],
  [SimilarPartsResult,{source_part:{name:'Part'},similar_parts:[row]},['Overview','Similar Parts']],
  [ManufacturingResult,{part:{name:'Part'},direct_processes:[row],process_instances:[row],related_part_processes:[row],process_summary:{total_direct:1,total_instances:1,total_related:1,by_type:{Machining:[row]}}},['Overview','Direct Processes','Process Instances','Related Processes','Type Summary']],
 ]){
  const view=render(<Component data={data}/>);
  for(const label of labels){fireEvent.click(screen.getByRole('tab',{name:label}));expect(view.container.textContent.length).toBeGreaterThan(0);}
  view.unmount();
 }
});

test('result tabs support keyboard navigation, selection and panel association',()=>{
 render(<SimilarPartsResult data={{source_part:{name:'Part'},similar_parts:[]}}/>);
 const first=screen.getByRole('tab',{name:'Overview'});
 fireEvent.keyDown(first,{key:'ArrowRight'});
 const selected=screen.getByRole('tab',{name:'Similar Parts',selected:true});
 expect(selected).toHaveFocus();
 expect(screen.getByRole('tabpanel')).toHaveAttribute('aria-labelledby',selected.id);
 fireEvent.keyDown(selected,{key:'Home'});
 expect(first).toHaveFocus();
 expect(first).toHaveAttribute('aria-selected','true');
});

test('timeline responds to resize and disconnects its observer',()=>{
 let resize;
 const disconnect=vi.fn();
 vi.stubGlobal('ResizeObserver',class { constructor(callback){resize=callback;}observe(){}disconnect(){disconnect();} });
 let width=400;
 vi.spyOn(SVGElement.prototype,'clientWidth','get').mockImplementation(()=>width);
 const view=render(<ProcessFlowTimeline data={{part:{name:'Part'},direct_processes:[{process_name:'Machining'}]}}/>);
 expect(screen.getByRole('img',{name:'Recorded processes by category'})).toHaveAttribute('width','400');
 width=600;
 // ResizeObserver callbacks are external to React's event handlers.
 act(()=>resize());
 expect(screen.getByRole('img',{name:'Recorded processes by category'})).toHaveAttribute('width','600');
 view.unmount();expect(disconnect).toHaveBeenCalled();
 vi.unstubAllGlobals();
});
