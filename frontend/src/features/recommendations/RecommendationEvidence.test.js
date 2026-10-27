import React from 'react';
import {render,screen,fireEvent} from '@testing-library/react';
import {SimilarPartsResult} from './SimilarPartsResult';
import {ScoreBar} from './RecommendationPrimitives';
import {AIInsightBanner} from './AIInsightBanner';
import DependencyPathGraph from './DependencyPathGraph';
import {ManufacturingResult} from './ManufacturingResult';

test('unassessed relationships are not presented as negative findings',()=>{
 render(<SimilarPartsResult data={{source_part:{name:'Motor'},similar_parts:[{name:'Other',similarity_score:75,source_tag_match:true,type_match:false,shared_assembly:null,rflp_layer_match:null,traceability_link:null}]}}/>);
 fireEvent.click(screen.getByText('Similar Parts'));
 fireEvent.click(screen.getByText('Review properties and missing evidence'));
 expect(screen.getByText('Not assessed')).toBeVisible();
 expect(screen.getByText(/Assembly compatibility: Not assessed/)).toBeVisible();
 expect(screen.queryByText('lexical + graph-type match')).toBeNull();
});

test('evidence volume is never labelled impact severity',()=>{
 render(<ScoreBar score={100}/>);
 expect(screen.getByText(/severity not assessed/)).toBeVisible();
 expect(screen.queryByText(/High Impact/)).toBeNull();
});

test('missing impact evidence is not described as low risk',()=>{
 render(<AIInsightBanner service="change-impact" data={{change_entity:{name:'Change'},evidence_status:'insufficient',impact_score:null}}/>);
 expect(screen.getByText('Impact is not established')).toBeVisible();
 expect(screen.queryByText('Low impact')).toBeNull();
});

test('dependency graph shows the retained business path and supports keyboard inspection',()=>{
 const data={change_entity:{node_id:'change',name:'ECR 42'},realization_chain:[{node_id:'part',name:'Bearing',path_names:['ECR 42','Bearing'],review_status:'configuration_conflict',path:[{relationship_id:'edge',start_id:'change',end_id:'part',relationship_type:'IMPACTS'}]}]};
 render(<DependencyPathGraph data={data}/>);
 fireEvent.keyDown(screen.getByRole('button',{name:'Inspect Bearing'}),{key:'Enter'});
 expect(screen.getByRole('status')).toHaveTextContent('ECR 42 → Bearing');
 expect(screen.getByRole('status')).toHaveTextContent('Configuration evidence conflicts');
});

test('property comparisons and compatibility conflicts are visible in result rows',()=>{
 render(<SimilarPartsResult data={{source_part:{name:'Reference'},similar_parts:[{node_id:'other',name:'Candidate',similarity_score:20,conflicts:['diameter'],score_evidence:{engineering_assessed:1},engineering_comparisons:[{property:'diameter',source:['10 mm'],candidate:['11 mm'],status:'conflict',reason:'Compared after conversion to SI units'}]}]}}/>);
 fireEvent.click(screen.getByText('Similar Parts'));
 expect(screen.getByText('Conflicts: diameter')).toBeVisible();
 fireEvent.click(screen.getByText('Review properties and missing evidence'));
 expect(screen.getByText('10 mm')).toBeVisible();
 expect(screen.getByText('11 mm')).toBeVisible();
});

test('process context exposes limited coverage and does not imply an ordered manufacturing plan',()=>{
 const data={part:{name:'Bearing'},coverage:{limit_reached:true},direct_processes:[],process_summary:{total_direct:0}};
 render(<><AIInsightBanner service="manufacturing" data={data}/><ManufacturingResult data={data}/></>);
 expect(screen.getByText(/neighbor limit was reached/)).toBeVisible();
 expect(screen.getByText(/do not establish manufacturing sequence/)).toBeVisible();
 expect(screen.queryByText('Analysis completed')).toBeNull();
});
