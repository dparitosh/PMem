import React from 'react';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import MappingReviewTable from './MappingReviewTable';

afterEach(cleanup);
const candidate = {candidate_id:'first', source_term:'id1', source_type:'Relationship', import_id:'import', import_row_key:'id1', ontology_term:'Header', target_ontology_type:'ObjectProperty', target_ontology_iri:'urn:one:Header', confidence:1, eligible:true, evidence:['element_type']};
test('held high scores stay held in compact rows; evidence opens only on demand', () => {
  render(<MappingReviewTable candidates={[candidate,{...candidate,candidate_id:'second',target_ontology_iri:'urn:two:Header'}]} decisions={[{candidate_id:'first',decision:'hold',reasons:['validation_warning','ambiguous_target']}]} />);
  expect(screen.getByText('Multiple matching targets')).toBeVisible();
  expect(screen.getAllByText('100%')).toHaveLength(2);
  expect(screen.getByText('urn:one:Header')).toBeVisible();
  expect(screen.getByText('urn:two:Header')).toBeVisible();
  expect(screen.queryByText('What is being mapped')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:/Evidence for.*\(first\)/}));
  expect(screen.getByText('What is being mapped')).toBeVisible();
  expect(screen.getAllByRole('article')).toHaveLength(1);
  fireEvent.change(screen.getByLabelText('Show mappings'),{target:{value:'Held'}});
  expect(screen.queryByText('urn:two:Header')).not.toBeInTheDocument();
});
test('pagination retains all proposals and shows truthful unassessed status', () => {
  render(<MappingReviewTable candidates={Array.from({length:26},(_,index)=>({...candidate,candidate_id:String(index),import_row_key:String(index),source_term:`source-${index}`}))} />);
  expect(screen.getByText('source-24')).toBeVisible();
  expect(screen.queryByText('source-25')).not.toBeInTheDocument();
  expect(screen.getAllByText('Not assessed')).toHaveLength(26); // rows plus filter option
  fireEvent.click(screen.getByRole('button',{name:'Next'}));
  expect(screen.getByText('source-25')).toBeVisible();
  expect(screen.queryByText('source-24')).not.toBeInTheDocument();
});
test('groups competing targets by retained identity and separates mapping categories', () => {
  render(<MappingReviewTable candidates={[candidate, {...candidate,candidate_id:'alternative',ontology_term:'Alternative'}, {...candidate,candidate_id:'revision',import_row_key:'id2'}, {...candidate,candidate_id:'entity',source_type:'Entity',import_row_key:'id3'}]} />);
  expect(screen.getByRole('rowgroup',{name:'Source id1'})).toHaveTextContent('2 targets');
  expect(screen.getByRole('rowgroup',{name:'Source id2'})).toHaveTextContent('1 target');
  expect(screen.getByRole('rowgroup',{name:'Source id3'})).toBeVisible();
  fireEvent.change(screen.getByLabelText('Mapping category'),{target:{value:'Entity classification'}});
  expect(screen.queryByRole('rowgroup',{name:'Source id1'})).not.toBeInTheDocument();
  expect(screen.getByRole('rowgroup',{name:'Source id3'})).toBeVisible();
});
test('collapsing sources preserves their summary and reveals evidence only after reopening', () => {
  render(<MappingReviewTable candidates={[candidate]} decisions={[{candidate_id:'first',decision:'hold',reasons:['ambiguous_target']}]} />);
  fireEvent.click(screen.getByRole('button',{name:'Collapse all sources'}));
  expect(screen.queryByText('urn:one:Header')).not.toBeInTheDocument();
  expect(screen.getByRole('rowgroup',{name:'Source id1'})).toHaveTextContent('1 held');
  fireEvent.click(screen.getByRole('button',{name:/id1.*1 target/}));
  expect(screen.getByText('urn:one:Header')).toBeVisible();
  fireEvent.click(screen.getByRole('button',{name:'Collapse all sources'}));
  fireEvent.click(screen.getByRole('button',{name:'Expand all sources'}));
  expect(screen.getByText('urn:one:Header')).toBeVisible();
});
