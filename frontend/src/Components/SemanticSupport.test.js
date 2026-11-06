import React from 'react';
import { render, screen } from '@testing-library/react';
import SemanticSupport from './SemanticSupport';

test('unknown evidence states the next action without implying product approval', () => {
  render(<SemanticSupport report={{status:'unknown',business_summary:'Imports need review.',next_action:'Resolve imports'}}/>);
  expect(screen.getByText('Model evidence: unknown')).toBeVisible();
  expect(screen.getByText('Next action: Resolve imports.')).toBeVisible();
  expect(screen.getByText(/does not establish instance conformance/)).toBeVisible();
});

test('inconsistent verdict remains explicit and evidence details are expandable', () => {
  render(<SemanticSupport report={{status:'inconsistent',business_summary:'Correct the model.',ontology_id:'model',evidence_id:'r1',artifact_sha256:'abc'}}/>);
  expect(screen.getByText('Model evidence: inconsistent')).toBeVisible();
  expect(screen.getByText('Evidence revision').closest('details')).not.toHaveAttribute('open');
});
