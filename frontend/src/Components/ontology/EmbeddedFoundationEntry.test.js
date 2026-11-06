import React from 'react';
import {render,screen} from '@testing-library/react';
import {vi} from 'vitest';
import {apiClient} from '../../services/apiClient';
import EmbeddedFoundationEntry from './EmbeddedFoundationEntry';
vi.mock('../../services/apiClient',()=>({apiClient:{get:vi.fn()}}));
test('verified foundation is visible independently of imported ontology records',async()=>{
 apiClient.get.mockResolvedValue({data:{embedded:true,version:'4.2',version_iri:'urn:ido:4.2',depo_module_version:'1.0.0',class_count:42,status:'Public PCA FDIS proposal'}});
 render(<EmbeddedFoundationEntry/>);
 expect(await screen.findByText('PCA Industrial Data Ontology (IDO) 4.2')).toBeVisible();
 expect(screen.getByText(/Bundled offline reference/)).toBeVisible();
 expect(screen.queryByText('Published')).toBeNull();
});
test('failed availability check does not claim foundation is verified',async()=>{
 apiClient.get.mockRejectedValue(new Error('Foundation unavailable'));
 render(<EmbeddedFoundationEntry/>);
 expect(await screen.findByRole('alert')).toHaveTextContent('Foundation unavailable');
 expect(screen.queryByText(/Bundled offline reference/)).toBeNull();
});
