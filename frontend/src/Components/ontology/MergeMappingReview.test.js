import React from 'react';
import {render,screen,fireEvent} from '@testing-library/react';
import MergeMappingReview from './MergeMappingReview';
const candidate={source_label:'Diameter',source_iri:'urn:source:Diameter',target_label:'DiameterType',target_iri:'urn:target:Diameter',kind:'class',confidence_score:.72};
const props={sourceId:'ap242',targetId:'qif',onSelect:vi.fn()};
test('one compact decision section keeps details closed and removes vocabulary browsers',()=>{render(<MergeMappingReview compact {...props} suggestions={[candidate]} preview={{conflicts:[],publish_recommended:false}}/>);expect(screen.getByText('Mean proposal similarity: 72%')).toBeVisible();expect(screen.getByText('Merge needs review')).toBeVisible();expect(screen.queryByText('Browse source and target vocabularies')).toBeNull();expect(screen.getByText('View merge details').closest('details')).not.toHaveAttribute('open');fireEvent.click(screen.getByText('View merge details'));expect(screen.getByRole('button',{name:'Select for consolidation'})).toBeVisible();});
test('retains exact identities and reviewed selection without approving equivalence',()=>{render(<MergeMappingReview {...props} suggestions={[candidate]} preview={{conflicts:[]}}/>);expect(screen.getByText(candidate.source_iri)).toBeVisible();expect(screen.getByText(candidate.target_iri)).toBeVisible();fireEvent.click(screen.getByRole('button',{name:'Select for consolidation'}));expect(props.onSelect).toHaveBeenCalledWith(candidate);expect(screen.getByText('Equivalence not established')).toBeVisible();});
test('selection and search preserve distinct alternatives',()=>{const second={...candidate,target_iri:'urn:target:other'};render(<MergeMappingReview {...props} suggestions={[candidate,second]} selectedMappings={[candidate]} preview={{conflicts:[]}}/>);expect(screen.getAllByText('72% similarity')).toHaveLength(2);fireEvent.change(screen.getByLabelText('Search proposed mappings'),{target:{value:'missing'}});expect(screen.queryByRole('button',{name:'Select for consolidation'})).toBeNull();});
test('invalid scores cannot inflate overall similarity',()=>{render(<MergeMappingReview compact {...props} suggestions={[candidate,{...candidate,confidence_score:99},{...candidate,confidence_score:NaN}]} preview={{conflicts:[]}}/>);expect(screen.getByText('Mean proposal similarity: 72%')).toBeVisible();});
test('dirty selection cannot claim readiness',()=>{render(<MergeMappingReview compact {...props} suggestions={[candidate]} dirty preview={{conflicts:[],publish_recommended:true}}/>);expect(screen.getByText('Selection needs validation')).toBeVisible();expect(screen.queryByText('Merge available for CR/CO review')).toBeNull();});

test('class evidence does not present property domain/range as missing class metadata',()=>{
 render(<MergeMappingReview {...props} suggestions={[{...candidate,source_evidence:{definitions:['Source value']},target_evidence:{definitions:['Target type']}}]} preview={{conflicts:[]}}/>);
 fireEvent.click(screen.getByText('Compare concept evidence'));
 expect(screen.queryByText('Declared domains')).toBeNull();expect(screen.queryByText('Declared ranges')).toBeNull();
 expect(screen.getAllByText('Directly declared properties')).toHaveLength(2);
});
test('compact merge summarizes actual consolidations and the recorded blocker',()=>{
 render(<MergeMappingReview compact {...props} sourceLabel="PLMXML" targetLabel="MBSE" suggestions={[candidate]} preview={{conflicts:[],changes:{modified_entity_count:0},semantic_support:{reason:'unparsed_rdf_statements'}}}/>);
 expect(screen.getByText(/combined draft prepared.*0 concept identities consolidated/)).toBeVisible();
 expect(screen.getByText('Publication blocked: logical validation cannot process all statements')).toBeVisible();
 expect(screen.getByText('View merge details').closest('details')).not.toHaveAttribute('open');
});
