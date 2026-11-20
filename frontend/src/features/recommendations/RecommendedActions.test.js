import React from 'react';
import {render,screen,within,fireEvent} from '@testing-library/react';
import RecommendedActions from './RecommendedActions';
import {ManufacturingResult} from './ManufacturingResult';

test('conflicted comparisons are excluded from substitution recommendations',()=>{
 render(<RecommendedActions service="similar-parts" data={{similar_parts:[
  {name:'Bearing candidate',similarity_score:50.31,conflicts:[]},
  {name:'Shaft revision B',similarity_score:22.5,conflicts:['material','revision'],compatibility:'conflicting_evidence'}
 ]}}/>);
 const candidate=screen.getByRole('row',{name:/Bearing candidate/});
 expect(within(candidate).getByText(/before considering reuse/)).toBeVisible();
 const conflict=screen.getByRole('row',{name:/Shaft revision B/});
 expect(within(conflict).getByText('Do not propose substitution; resolve the recorded conflicts.')).toBeVisible();
 expect(within(conflict).getByText('Conflicting evidence: material, revision.')).toBeVisible();
 expect(within(conflict).queryByText(/before considering reuse/)).not.toBeInTheDocument();
});

test('an explicit conflicting verdict holds substitution even without a property list',()=>{
 render(<RecommendedActions service="similar-parts" data={{similar_parts:[{name:'Held candidate',compatibility:'conflicting_evidence'}]}}/>);
 expect(screen.getByText('Do not propose substitution; resolve the recorded conflicts.')).toBeVisible();
});

test('no candidates produces no contradictory recommendation task panel',()=>{
 render(<RecommendedActions service="similar-parts" data={{similar_parts:[]}}/>);
 expect(screen.queryByRole('heading',{name:'Recommended CO review tasks'})).not.toBeInTheDocument();
});


test('manufacturing evidence labels source provenance as Source rather than an engineering type',()=>{
 render(<ManufacturingResult data={{part:{name:'Bearing A'},process_summary:{total_direct:1},direct_processes:[{process_name:'Finish bore',source_tag:'engineering-ods-v1'}]}}/>);
 fireEvent.click(screen.getByRole('tab',{name:'Direct Processes',exact:true}));
 expect(screen.getByRole('columnheader',{name:'Source',exact:true})).toBeVisible();
 expect(screen.queryByRole('columnheader',{name:'Type',exact:true})).not.toBeInTheDocument();
 expect(screen.getByRole('cell',{name:'engineering-ods-v1',exact:true})).toBeVisible();
});
