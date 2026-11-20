import React from 'react';
import {render,screen,fireEvent} from '@testing-library/react';
import {vi,it,expect} from 'vitest';
vi.mock('../../widgets/DataGridWidget',()=>({default:({rows=[]})=><div>{rows.map((row,i)=><span key={i}>{row.domain} {row.range} {row.parents}{row.axiomCount != null && <em>{row.axiomCount} domain/range axioms</em>}</span>)}</div>}));
import {ProtegeOntologyBrowser} from './OntologyBrowser';
it('keeps property domain and range labels even when their classes lie outside the page',()=>{
 const taxonomy={page:{},nodes:[{term_id:'p',kind:'property',source:'object-property',label:'hasPart',browse_declarations:{complete:true,domain:[{term_id:'a',label:'Business Assembly'}],range:[{term_id:'b',label:'Business Part'}]}}],edges:[]};
 render(<ProtegeOntologyBrowser taxonomy={taxonomy} filter=""/>);
 fireEvent.click(screen.getByRole('tab',{name:'Properties',exact:true}));
 expect(screen.getByText(/Business Assembly Business Part/)).toBeVisible();
 expect(screen.getByText('2 domain/range axioms')).toBeVisible();
});

it('keeps inventory totals stable when the server returns a different table slice',()=>{
 const summary={total_classes:1200,total_properties:230,total_taxonomy_links:3100,total_terms:1500};
 const {rerender,container}=render(<ProtegeOntologyBrowser taxonomy={{page:{},summary,nodes:[{term_id:'c',kind:'class',label:'Part'}],edges:[]}} filter=""/>);
 const stats=()=>Array.from(container.querySelectorAll('[class*="stat"]')).map(el=>el.textContent).join(' ');
 const before=stats();
 fireEvent.click(screen.getByRole('tab',{name:'Properties',exact:true}));
 rerender(<ProtegeOntologyBrowser taxonomy={{page:{},summary,nodes:[{term_id:'p',kind:'property',label:'hasPart'}],edges:[]}} filter=""/>);
 expect(stats()).toBe(before);
 expect(screen.getByText('1200',{exact:true})).toBeVisible();
 expect(screen.getByText('230',{exact:true})).toBeVisible();
 fireEvent.click(screen.getByRole('tab',{name:'Axioms',exact:true}));
 expect(stats()).toBe(before);
 expect(screen.getByText('3100',{exact:true})).toBeVisible();
});

it('does not classify a typed class as a property through a property_of edge',()=>{
 render(<ProtegeOntologyBrowser taxonomy={{page:{},summary:{total_classes:1,total_properties:0,total_terms:1,total_taxonomy_links:1},nodes:[{term_id:'c',kind:'class',label:'Part',browse_declarations:{complete:true}}],edges:[{source_term:'c',target_term:'c',mapping_type:'property_of'}]}} filter=""/>);
 expect(screen.getByRole('tab',{name:'Properties',exact:true})).toBeVisible();
 fireEvent.click(screen.getByRole('tab',{name:'Properties',exact:true}));
 expect(screen.getByText('0',{exact:true})).toBeVisible();
});
