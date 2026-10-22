import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { agenticClient } from '../../services/agenticApi';
vi.mock('../../services/agenticApi', () => ({agenticClient:{post:vi.fn(),get:vi.fn()}}));
import OntologyInferenceWorkbench from './OntologyInferenceWorkbench';

test('inference evidence distinguishes declarations and rule support from confidence or execution', () => {
  render(<OntologyInferenceWorkbench selectedOntologyApi="ontology" inferenceRules={{domain_range_typing:true}} swrlExpression="A(?x) -> B(?x)" inferenceLimit={25}
    swrlValidation={{valid:true,preview:'Supported syntax'}}
    inferenceResult={{summary:{truncated:true},inferences:[{rule:'equivalence',subject:'a',predicate:'skos:exactMatch',object:'b',support:'structural rule',confidence:.95}],constraints:[{property:'urn:property',kind:'range',class:'urn:Target'}]}} />);
  expect(screen.getByRole('region',{name:'Domain and range declarations'})).toHaveTextContent('urn:Target');
  expect(screen.getByText('skos:exactMatch')).toBeInTheDocument();
  expect(screen.getByText('structural rule')).toBeInTheDocument();
  expect(screen.queryByText('95%')).not.toBeInTheDocument();
  expect(screen.getByText('Supported syntax — not executed')).toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent('preview is incomplete');
});

test('idle preview does not claim zero results and disabled rules cannot run',()=>{
 render(<OntologyInferenceWorkbench selectedOntologyApi="ontology" inferenceRules={{}} swrlExpression="" inferenceLimit={25} />);
 expect(screen.getByText('Candidates: Not run')).toBeVisible();
 expect(screen.getByText('Classes: Unavailable')).toBeVisible();
 expect(screen.getByRole('button',{name:'Run preview'})).toBeDisabled();
 expect(screen.getByLabelText('Inference preview limit')).toHaveValue(25);
});


test('inference advisor sends the selected ontology and rules to a retained read goal',async()=>{
 sessionStorage.clear();
 agenticClient.post.mockResolvedValue({data:{run_id:'goal-inference-run',status:'completed',goal:'Explain hierarchy',plans:[{revision:1,subtasks:['Inspect selected ontology']}],observations:[{id:'observation-2',tool_id:'ontology.inference.preview',status:'completed',result:{ontology_id:'selected',inferences:[]}}],result:{summary:'No additional class closure found',evidence_steps:['observation-2']}}});
 render(<OntologyInferenceWorkbench selectedOntologyApi="selected" inferenceRules={{transitive_subclass:true}} swrlExpression="" inferenceLimit={25}/>);
 fireEvent.change(screen.getByLabelText('What would you like to understand?'),{target:{value:'Explain hierarchy'}});
 fireEvent.click(screen.getByRole('button',{name:'Start read-only investigation'}));
 expect(await screen.findByText('No additional class closure found')).toBeVisible();
 expect(agenticClient.post).toHaveBeenCalledWith(expect.stringContaining('/agents/ontology-inference/goals'),expect.objectContaining({task:'Explain hierarchy',submission_id:expect.any(String),context:expect.objectContaining({ontology_id:'selected',rules:{transitive_subclass:true},limit:25})}),expect.anything());
 expect(screen.getByText('Inspect selected ontology')).toBeVisible();
});
