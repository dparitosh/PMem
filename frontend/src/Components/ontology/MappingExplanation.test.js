import React from 'react';
import { render, screen, cleanup } from '@testing-library/react';
import MappingExplanation, { matchScore, explainHoldReason } from './MappingExplanation';
afterEach(cleanup);
const candidate={candidate_id:'first',source_term:'id1',source_type:'relationship',import_id:'import',import_row_key:'row1',ontology_term:'Header',target_ontology_type:'ObjectProperty',confidence:1,eligible:true,evidence:['element_type'],validation_warnings:['Domain and range classes are unverified.']};
test('high-score ambiguous mapping explains uncertainty, alternatives and exact publication effect',()=>{
 const other={...candidate,candidate_id:'other',target_ontology_iri:'urn:other:Header'};
 render(<MappingExplanation candidate={candidate} candidates={[candidate,other]} decisions={[{candidate_id:'first',decision:'hold',reasons:['ambiguous_target']}]}/>);
 expect(screen.getByText('Review needed')).toBeInTheDocument();
 expect(screen.getByText(/not a probability of semantic correctness/)).toBeInTheDocument();
 expect(screen.getByText(/source element type contributed/)).toBeInTheDocument();
 expect(screen.getByText(/urn:other:Header/)).toBeInTheDocument();
 expect(screen.getByText(/one unambiguous first-choice/)).toBeInTheDocument();
 expect(screen.getByText(/SEMANTICALLY_MAPPED_TO/)).toBeInTheDocument();
 expect(screen.queryByText(/receives an INSTANCE_OF/)).not.toBeInTheDocument();
 expect(screen.getByText(/Leave this unselected/)).toBeInTheDocument();
});
test('missing evidence and scores are acknowledged; ineligible mappings remain blocked',()=>{
 render(<MappingExplanation candidate={{...candidate,eligible:false,confidence:null,evidence:[]}} candidates={[candidate]}/>);
 expect(screen.getByText(/No supporting rationale was recorded/)).toBeInTheDocument();
 expect(screen.getByText(/publication is blocked/)).toBeInTheDocument();
 expect(screen.getByText(/No alternatives were retained/)).toBeInTheDocument();
 for(const confidence of [undefined,null,NaN,Infinity,2,-1,'1']) expect(matchScore({confidence})).toBe('Not recorded');
 expect(explainHoldReason('new_code')).toContain('additional policy check');
});
test('class publication describes its additional type link without inventing model reasoning',()=>{
 const row={...candidate,target_ontology_type:'Class',validation_warnings:[],validation_status:'auto_approved'};
 render(<MappingExplanation candidate={row} candidates={[row]}/>);
 expect(screen.getByText(/class target also receives an INSTANCE_OF/)).toBeInTheDocument();
 expect(screen.getByText(/does not add model reasoning/)).toBeInTheDocument();
});


test('incomplete source identity does not group unrelated targets as alternatives',()=>{
 const row={...candidate,import_row_key:undefined,validation_warnings:[],validation_status:'auto_approved',rank:1};
 render(<MappingExplanation candidate={row} candidates={[row,{...row,candidate_id:'unrelated',ontology_term:'UNRELATED_TARGET'}]}/>);
 expect(screen.getByText(/source identity is missing/)).toBeInTheDocument();
 expect(screen.queryByText(/UNRELATED_TARGET/)).not.toBeInTheDocument();
 expect(screen.getByText('Review needed')).toBeInTheDocument();
});
test('low score and malformed evidence never imply completed semantic validation',()=>{
 const row={...candidate,confidence:.2,evidence:'unstructured',rank:1,validation_warnings:[],validation_status:'auto_approved'};
 render(<MappingExplanation candidate={row} candidates={[row]}/>);
 expect(screen.getByText('Review needed')).toBeInTheDocument();
 expect(screen.getByText(/No supporting rationale was recorded/)).toBeInTheDocument();
});
