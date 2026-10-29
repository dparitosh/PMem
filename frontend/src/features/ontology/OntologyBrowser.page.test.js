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
