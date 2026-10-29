import React from 'react';
import {render,screen,fireEvent,within} from '@testing-library/react';
import {vi,test,expect} from 'vitest';
vi.mock('../../widgets/DataGridWidget',()=>({default:({title,rows,onRowClicked})=><section aria-label={title} data-row-ids={JSON.stringify(rows.map(row=>row.id))}><h3>{title}</h3>{onRowClicked&&rows.length>0&&<button onClick={()=>onRowClicked(rows[0])}>Inspect first term</button>}</section>}));
import {ProtegeOntologyBrowser} from './OntologyBrowser';

test('flat ontology browser keeps keyboard tabs and selected-term inspection usable',()=>{
 const nodes=[{term_id:'urn:Product',label:'Product',kind:'class',source:'rdf-class',definition:'A product definition.'}];
 render(<ProtegeOntologyBrowser nodes={nodes} edges={[]} filter="" taxonomy={{nodes,edges:[]}} reasoning={null}/>);
 expect(screen.queryByText('Hierarchy',{exact:true})).toBeNull();
 expect(screen.queryByText('Semantic Tables',{exact:true})).toBeNull();
 expect(screen.queryByRole('region',{name:'Selected term details'})).toBeNull();
 expect(screen.getByRole('tabpanel')).toHaveAccessibleName('Classes');
 fireEvent.click(screen.getByRole('button',{name:'Inspect first term'}));
 expect(within(screen.getByRole('region',{name:'Selected term details'})).getByText('A product definition.')).toBeVisible();
 fireEvent.keyDown(screen.getByRole('tab',{name:'Classes'}),{key:'ArrowRight'});
 expect(screen.getByRole('tab',{name:'Properties'})).toHaveFocus();
 expect(screen.getByRole('tabpanel')).toHaveAccessibleName('Properties');
});

test('same-name terms in different namespaces keep distinct grid identities before taxonomy loads',()=>{
 const reasoning={classes:[
   {iri:'https://one.example/Part',local_name:'Part',label:'Part',ontology_prefix:'product'},
   {iri:'https://two.example/Part',local_name:'Part',label:'Part',ontology_prefix:'product'},
 ]};
 const {container}=render(<ProtegeOntologyBrowser nodes={[]} edges={[]} filter="" taxonomy={{ontology_prefix:'product'}} reasoning={reasoning}/>);
 const ids=[...container.querySelectorAll('[data-row-ids]')].map(grid=>JSON.parse(grid.getAttribute('data-row-ids'))).find(rows=>rows.length===2);
 expect(ids).toBeDefined();
 expect(new Set(ids).size).toBe(2);
});
