import React from 'react';
import {vi} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import BusinessAnalyticsModel from './BusinessAnalyticsModel';
import {dataPipelineAPI as api} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({dataPipelineAPI:{semanticFields:vi.fn()}}));
test('offers vocabulary properties for explicit outgoing business relationships',async()=>{
 api.semanticFields.mockImplementation((dataset,iri)=>Promise.resolve({data:{dataset_id:dataset,class_iri:iri,rows:[{property_iri:'urn:rel',label:'has component'}]}}));
 const changed=vi.fn();render(<BusinessAnalyticsModel datasetId="snapshot" classes={[{iri:'urn:Part',name:'Part',entities:3}]} value={{part_class:'urn:Part'}} onChange={changed}/>);
 const rel=screen.getByLabelText('Part → requirement relationship');await waitFor(()=>expect(rel).not.toBeDisabled());
 fireEvent.change(rel,{target:{value:'urn:rel'}});expect(changed).toHaveBeenCalledWith({part_class:'urn:Part',requirement_property:'urn:rel'});
 expect(screen.getByText(/BOM completeness stays unassessed/)).toBeInTheDocument();
});
