import React from 'react';
import {render,screen} from '@testing-library/react';
import ModelTraceability,{safeReference,collectReferences} from './ModelTraceability';

test('only recorded safe web references are linked and retain their evidence',()=>{
 const element={label:'Drive',properties:{plm_url:'https://plm.example/part/42',cad_file_url:'https://cad.example/file/42',bad_url:'javascript:alert(1)',token_url:'https://example.com/?api_key=secret'}};
 const context={nodes:[{id:'dataset',labels:['Simulation'],properties:{name:'Thermal run',dataset_url:'https://simulation.example/run/7'}}],links:[{source:'part',target:'dataset',type:'VALIDATED_BY'}]};
 render(<ModelTraceability element={element} context={context}/>);
 expect(screen.getAllByRole('link')).toHaveLength(3);
 expect(screen.getByRole('link',{name:/Thermal run/})).toHaveAttribute('href','https://simulation.example/run/7');
 expect(screen.getByText(/Recorded graph relationship: VALIDATED_BY/)).toBeInTheDocument();
 expect(screen.queryByRole('link',{name:/secret/})).toBeNull();
 expect(safeReference('file:///private/model.step')).toBeNull();
 expect(safeReference('https://user:password@example.com/')).toBeNull();
 expect(collectReferences({properties:{iri:'https://ontology.example/Class'}},null)).toHaveLength(0);
});

test('no links or disconnected nodes never fabricate traceability',()=>{
 render(<ModelTraceability element={{properties:{}}} context={{nodes:[{id:'unrelated',properties:{plm_url:'https://plm.example/unrelated'}}],links:[]}}/>);
 expect(screen.queryByRole('link')).toBeNull();
 expect(screen.getAllByText('No recorded web link in the available evidence.')).toHaveLength(4);
});
