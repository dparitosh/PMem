import React from 'react';
import {render,screen,cleanup} from '@testing-library/react';
import BridgeDecisionReview from './BridgeDecisionReview';
afterEach(cleanup);
test('shows decision outcomes without claiming name matches are validated',()=>{
 render(<BridgeDecisionReview report={{steps:[{result:{issues:[]}},{result:{alignment_items:[{status:'unmatched'},{status:'candidate'}],alignment_candidates:[{source:'Requirement',target_iri:'urn:test#Requirement',status:'review_required',unresolved_checks:['scope_check']} ]}}]}}/>);
 expect(screen.getByText('Mapping suggestions need review')).toBeVisible();
 expect(screen.getByText('1 suggestions · 1 unmatched terms · 0 conflicting or ambiguous terms')).toBeVisible();
 expect(screen.queryByText(/scope_check|No structural issues|steps completed|Review ready/)).toBeNull();
 expect(screen.getByText('Review required')).toBeVisible();
});
test('empty suggestions report no match rather than success',()=>{render(<BridgeDecisionReview report={{steps:[{result:{alignment_items:[],alignment_candidates:[]}}]}}/>);expect(screen.getByText('No name-based match found')).toBeVisible();});
