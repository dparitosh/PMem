import React from 'react';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import IngestorCapabilities from './IngestorCapabilities';
import {dataPipelineAPI as api} from '../services/apiClient';
vi.mock('../services/apiClient',()=>({dataPipelineAPI:{ingestorCapabilities:vi.fn()}}));
const result={data:{contract:'ingestor-capabilities-v1',semantica_version:'0.6.7',ingestors:[{id:'rest',name:'RESTIngestor',integration:'configured-adapter',configurable:true,postgres_namespace:'rest_sources',workspace:'#/admin',description:'HTTP(S)'},{id:'email',name:'EmailIngestor',integration:'not-integrated',description:'No adapter'}]}};
beforeEach(()=>vi.resetAllMocks());
test('shows actual connector support and filters unsupported source types',async()=>{
 api.ingestorCapabilities.mockResolvedValue(result);render(<IngestorCapabilities/>);
 expect(await screen.findByText('REST')).toBeVisible();expect(screen.getByText('Email')).toBeVisible();
 fireEvent.change(screen.getByRole('combobox',{name:'Show connectors'}),{target:{value:'configured-adapter'}});
 expect(screen.queryByText('Email')).not.toBeInTheDocument();expect(screen.getByRole('button',{name:'Configure REST source below'})).toBeVisible();
});
test('late response after reconnect cannot restore the earlier inventory',async()=>{
 let resolve;api.ingestorCapabilities.mockImplementationOnce(()=>new Promise(r=>{resolve=r;})).mockResolvedValue(result);
 render(<IngestorCapabilities/>);fireEvent(window,new Event('depo:session-replaced'));
 await screen.findByText('REST');resolve({data:{...result.data,ingestors:[{id:'old',integration:'not-integrated',name:'ObsoleteIngestor'}]}});
 await waitFor(()=>expect(api.ingestorCapabilities).toHaveBeenCalledTimes(2));expect(screen.queryByText('Obsolete')).not.toBeInTheDocument();
});
test('malformed response displays an error instead of a success inventory',async()=>{
 api.ingestorCapabilities.mockResolvedValue({data:{contract:'wrong'}});render(<IngestorCapabilities/>);
 expect(await screen.findByRole('alert')).toHaveTextContent('Invalid connector inventory');
});

test.each([
 [{id:'rest',integration:'configured-adapter',description:'Missing name'}],
 [{...result.data.ingestors[0],workspace:'javascript:alert(1)'}],
 [result.data.ingestors[0],result.data.ingestors[0]],
])('rejects malformed connector records without rendering actionable links',async(ingestors)=>{
 api.ingestorCapabilities.mockResolvedValue({data:{...result.data,ingestors}});render(<IngestorCapabilities/>);
 expect(await screen.findByRole('alert')).toHaveTextContent('Invalid connector inventory');
 expect(screen.queryByRole('button',{name:'Configure REST source below'})).not.toBeInTheDocument();
});

test('isolated runtime details do not imply that acquisition requires Semantica in the API environment',async()=>{
 api.ingestorCapabilities.mockResolvedValue({data:{...result.data,semantica_version:null,acquisition_runtime:'ontology'}});
 render(<IngestorCapabilities/>);await screen.findByText('REST');
 fireEvent.click(screen.getByText('Runtime and connection checks'));
 expect(screen.getByText(/REST acquisition uses the existing semantic runtime/)).toBeVisible();
 expect(screen.getByText(/acquisition runtime is checked separately/)).toBeVisible();
});
