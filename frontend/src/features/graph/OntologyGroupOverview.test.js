import React from 'react';
import {render,screen,fireEvent} from '@testing-library/react';
import OntologyGroupOverview from './OntologyGroupOverview';
it('searches group controls and discards selection that no longer exists in a new slice',()=>{
 const view=render(<OntologyGroupOverview data={{nodes:[{id:'a',ontology_id:'alpha',properties:{name:'Part A'}}]}}/>);
 fireEvent.click(screen.getByRole('checkbox',{name:'alpha (1)'}));
 fireEvent.change(screen.getByPlaceholderText('Filter groups'),{target:{value:'missing'}});
 expect(screen.queryByRole('checkbox')).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Show all groups'}));
 view.rerender(<OntologyGroupOverview data={{nodes:[{id:'b',ontology_id:'beta',properties:{name:'Part B'}}]}}/>);
 expect(screen.getByRole('button',{name:'Part B',exact:true})).toBeVisible();
});
it('shows separate ontology entities and recorded cross-ontology mappings with filter controls',()=>{
 const onInspectNode=vi.fn(),onOpenOntology=vi.fn();
 const data={nodes:[{elementId:'a',ontology_id:'ap242-v1',properties:{name:'Product'}},{elementId:'b',ontology_id:'qif-v1',properties:{name:'Part'}}],links:[{elementId:'m',source:'a',target:'b',type:'SEMANTICALLY_MAPPED_TO'}]};
 render(<OntologyGroupOverview data={data} ontologyOptions={[{value:'ap242-v1',label:'AP242'},{value:'qif-v1',label:'QIF'}]} onInspectNode={onInspectNode} onOpenOntology={onOpenOntology}/>);
 expect(screen.getByText(/2 groups/)).toBeInTheDocument();
 fireEvent.click(screen.getByText('Cross-group connections (1 recorded links)'));
 expect(screen.getByText('SEMANTICALLY_MAPPED_TO')).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'Product',exact:true}));
 expect(onInspectNode).toHaveBeenCalledWith('a');
 fireEvent.click(screen.getByRole('button',{name:'Open AP242'}));
 expect(onOpenOntology).toHaveBeenCalledWith('ap242-v1');
 fireEvent.click(screen.getByRole('checkbox',{name:'AP242 (1)'}));
 expect(screen.queryByRole('button',{name:'Part',exact:true})).toBeNull();
 expect(screen.getByText('Cross-group connections (0 recorded links)')).toBeInTheDocument();
});
