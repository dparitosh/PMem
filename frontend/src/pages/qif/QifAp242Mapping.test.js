import React from 'react';
import {vi} from 'vitest';
import {act,fireEvent,render,screen} from '@testing-library/react';
import QifAp242Mapping from './QifAp242Mapping';
import {apiClient} from '../../services/apiClient';
vi.mock('../../contexts/OntologyContext',()=>({useOntologies:()=>({ontologies:[{value:'q',label:'QIF'},{value:'a',label:'AP242'}],loading:false,fetchOntologies:vi.fn()})}));
vi.mock('../../services/apiClient',()=>({apiClient:{get:vi.fn()}}));
vi.mock('../../services/agenticApi',()=>({default:{isConfigured:()=>true}}));
test('credential changes clear inspected evidence',async()=>{
 apiClient.get.mockImplementation(url=>Promise.resolve({data:{ontology_id:url.includes('/q/')?'q':'a',scope:'retained-ontology-version',nodes:[{source:'rdf-class',uri:'urn:Part'},{source:'rdf-datatype-property',uri:'urn:name'},{source:'rdf-object-property',uri:'urn:hasPart'}]}}));
 render(<QifAp242Mapping/>);
 fireEvent.change(screen.getByLabelText('QIF ontology'),{target:{value:'q'}});
 fireEvent.change(screen.getByLabelText('AP242 ontology'),{target:{value:'a'}});
 fireEvent.click(screen.getByText('Inspect selected schema inventories'));
 await screen.findByText(/Structural inventories only/);
 expect(screen.getByText('AP242: 1 entities, 1 properties, 1 relationships.')).toBeInTheDocument();
 act(()=>window.dispatchEvent(new Event('depo:credentials-cleared')));
 expect(screen.queryByText(/Structural inventories only/)).not.toBeInTheDocument();
});
