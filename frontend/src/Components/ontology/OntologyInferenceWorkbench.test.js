import React from 'react';
import { render, screen } from '@testing-library/react';
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
