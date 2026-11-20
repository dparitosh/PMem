import React from 'react';
import { render, screen } from '@testing-library/react';
import SemanticSupport from './SemanticSupport';

test('unknown evidence states the next action without implying product approval', () => {
  render(<SemanticSupport report={{status:'unknown',business_summary:'Imports need review.',next_action:'Resolve imports'}}/>);
  expect(screen.getByText('Model check: Unverified')).toBeVisible();
  expect(screen.getByText('Next step: Resolve imports.')).toBeVisible();
  expect(screen.getByText(/does not confirm that your data is correct/)).toBeVisible();
});

test('inconsistent verdict remains explicit and evidence details are expandable', () => {
  render(<SemanticSupport report={{status:'inconsistent',business_summary:'Correct the model.',ontology_id:'model',evidence_id:'r1',artifact_sha256:'abc'}}/>);
  expect(screen.getByText('Model check: Conflicts found')).toBeVisible();
  expect(screen.getByText('Evidence revision').closest('details')).not.toHaveAttribute('open');
});


test('partial parsing cannot display profile findings as a complete audit',()=>{
 render(<SemanticSupport report={{status:'unsupported',unparsed_statement_count:2,profile_complete_for_input:false,profile_violation_count:3}}/>);
 expect(screen.getByText('Profile findings cover parsed statements only.').closest('details')).not.toHaveAttribute('open');
 expect(screen.getByText('Model check: Unsupported logical model')).toBeVisible();
});
