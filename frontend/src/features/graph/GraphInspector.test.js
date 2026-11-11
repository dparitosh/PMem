import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import GraphInspector from './GraphInspector';
import { ChangeImpactResult } from '../recommendations/ChangeImpactResult';

const insufficient = {
  change_entity: { name: 'Bearing noise' }, impact_score: null,
  evidence_status: 'insufficient',
  message: 'Impact is unknown; review the affected business records.',
};

test('graph inspector explains missing evidence without a zero or high impact score', () => {
  render(<GraphInspector recPanel={{open: true, service: 'change-impact', nodeName: 'Bearing noise', result: insufficient}}
    setRecPanel={vi.fn()} setActiveTab={vi.fn()} />);
  expect(screen.getByText('Impact is unknown; review the affected business records.')).toBeVisible();
  expect(screen.queryByText(/\/100/)).not.toBeInTheDocument();
});

test('recommendations keeps unknown impact distinct from a safety conclusion', () => {
  render(<ChangeImpactResult data={insufficient} />);
  expect(screen.getByRole('status')).toHaveTextContent('Bearing noise');
  expect(screen.getByRole('status')).toHaveTextContent('Impact is unknown');
  expect(screen.queryByText(/Impact Score/)).not.toBeInTheDocument();
});

test('full review handoff keeps the exact graph identity and ontology scope',()=>{
 render(<GraphInspector recPanel={{open:true,service:'similar-parts',nodeName:'Motor',context:{nodeId:'revision-b',ontologyId:'plant'}}} setRecPanel={vi.fn()} setActiveTab={vi.fn()}/>);
 fireEvent.click(screen.getByRole('link',{name:'Open full engineering review'}));
 expect(window.__dt_rec_prefill).toMatchObject({node_id:'revision-b',ontology_id:'plant',service:'similar-parts'});
 delete window.__dt_rec_prefill;
});

test('recommendation highlights use graph identities when business names repeat',()=>{
 const handler=vi.fn();window.addEventListener('dt-highlight-nodes',handler);
 render(<GraphInspector recPanel={{open:true,service:'similar-parts',nodeName:'Motor',result:{source_part:{node_id:'a',name:'Motor'},similar_parts:[{node_id:'b',name:'Motor',similarity_score:20}]}}} setRecPanel={vi.fn()} setActiveTab={vi.fn()}/>);
 fireEvent.click(screen.getByRole('button',{name:'Highlight in graph'}));
 expect(handler.mock.calls[0][0].detail).toEqual({ids:['a','b']});
 window.removeEventListener('dt-highlight-nodes',handler);
});
