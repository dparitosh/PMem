import React from 'react';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {API_METHODS} from '../../services/apiClient';
import RetainedRuleAssessment from './RetainedRuleAssessment';
vi.mock('../../services/apiClient',()=>({API_METHODS:{ontology:{assessRetainedRules:vi.fn()}}}));
const result={ontology_id:'selected',status:'completed',summary:{rules:1,executed:1,conclusions:1},shacl:{targeted_subjects:1000},rules:[{rule_id:'rule',name:'Shaft above limit',truncated:false,rows:[{subject_label:'INS-0987',conclusion_label:'Above limit',inputs:[{predicate:'urn:inspection:value',value:'30.0243666073137'},{predicate:'urn:inspection:unit',value:'mm/s'}]}]}]};
test('displays the measured evidence without truncating literal units',async()=>{
 API_METHODS.ontology.assessRetainedRules.mockResolvedValue({data:result});
 render(<RetainedRuleAssessment ontologyId="selected"/>);
 fireEvent.click(screen.getByRole('button',{name:'Assess retained rules'}));
 expect(await screen.findByText('INS-0987')).toBeVisible();
 fireEvent.click(screen.getByText('Source evidence'));
 expect(screen.getByText(/30.0243666073137/)).toBeVisible();
 expect(screen.getByText(/mm\/s/)).toBeVisible();
});
test('rejects mismatched ontology evidence and clears it on scope change',async()=>{
 API_METHODS.ontology.assessRetainedRules.mockResolvedValue({data:{...result,ontology_id:'other'}});
 const view=render(<RetainedRuleAssessment ontologyId="selected"/>);
 fireEvent.click(screen.getByRole('button',{name:'Assess retained rules'}));
 expect(await screen.findByRole('alert')).toBeVisible();
 expect(screen.queryByText('INS-0987')).toBeNull();
 view.rerender(<RetainedRuleAssessment ontologyId="another"/>);
 await waitFor(()=>expect(screen.queryByRole('alert')).toBeNull());
});
test('malformed row evidence does not crash rendering',async()=>{
 API_METHODS.ontology.assessRetainedRules.mockResolvedValue({data:{...result,rules:[{rows:[{inputs:null}],truncated:false}]}});
 render(<RetainedRuleAssessment ontologyId="selected"/>);
 fireEvent.click(screen.getByRole('button',{name:'Assess retained rules'}));
 expect(await screen.findByRole('alert')).toBeVisible();
});
