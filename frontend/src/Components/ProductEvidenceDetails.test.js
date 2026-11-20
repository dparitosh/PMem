import {vi} from 'vitest';
import {downloadArtifact} from '../services/artifactDownload';
vi.mock('../services/artifactDownload',()=>({downloadArtifact:vi.fn()}));
vi.mock('../config',()=>({buildSemanticServiceUrl:(_service,path)=>path}));
import React from 'react';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import ProductEvidenceDetails from './ProductEvidenceDetails';
test('shows ownership, readiness and pending delivery without requiring raw JSON',()=>{
 render(<ProductEvidenceDetails detail={{product_id:'quality',name:'Inspection results',owner:'Metrology',analytics_readiness:'evidence-only',status:'pending_catalog_registration',sources:[{run_id:'run-1'}],artifacts:[{}]}}/>);
 expect(screen.getByRole('heading',{name:'Inspection results'})).toBeVisible();
 expect(screen.getByText('Metrology')).toBeVisible();
 expect(screen.getByText('evidence-only')).toBeVisible();
 expect(screen.getByRole('status')).toHaveTextContent('Package retained; catalog delivery needs attention');
 expect(screen.queryByText('Technical record')).not.toBeInTheDocument();
 expect(screen.getByRole('link',{name:'View source run'})).toHaveAttribute('href','#/data-flow?run_id=run-1');
});
test('catalog versions retain individual owners and missing values are explicit',()=>{
 render(<ProductEvidenceDetails detail={{product_id:'parts',versions:[{version:'1.0.0',owner:'PLM'},{version:'2.0.0',owner:'Manufacturing'}]}}/>);
 expect(screen.getByText('1.0.0')).toBeVisible();expect(screen.getByText('2.0.0')).toBeVisible();
 expect(screen.getByText('PLM')).toBeVisible();expect(screen.getByText('Manufacturing')).toBeVisible();
 expect(screen.getAllByText('Not recorded').length).toBeGreaterThan(0);
});

test('downloads only the selected immutable product version through the authenticated helper',async()=>{
 downloadArtifact.mockResolvedValue();render(<ProductEvidenceDetails detail={{product_id:'motor',version:'1.0.0',status:'published'}}/>);
 fireEvent.click(screen.getByRole('button',{name:'Download package 1.0.0'}));
 await waitFor(()=>expect(downloadArtifact).toHaveBeenCalledWith('/api/v1/data-products/motor%3A1.0.0/download','motor-1.0.0.zip'));
});
test('a failed package verification remains actionable and is not reported as downloaded',async()=>{
 downloadArtifact.mockRejectedValue(new Error('Package integrity verification failed'));
 render(<ProductEvidenceDetails detail={{product_id:'motor',version:'2.0.0',status:'published'}}/>);
 fireEvent.click(screen.getByRole('button',{name:'Download package 2.0.0'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('Package integrity verification failed');
 expect(screen.getByRole('button',{name:'Download package 2.0.0'})).toBeEnabled();
});

test('catalog registration does not invent missing delivery or artifact statuses',()=>{
 render(<ProductEvidenceDetails catalog detail={{product_id:'motor',versions:[{version:'1.0.0',name:'Motor evidence',lifecycle_state:'published',sources:[]}]}}/>);
 expect(screen.getByRole('heading',{name:'Motor evidence'})).toBeVisible();expect(screen.getByText('Catalog presence')).toBeVisible();expect(screen.getByText('Registered')).toBeVisible();
 expect(screen.queryByText(/Artifacts: Not recorded/)).not.toBeInTheDocument();expect(screen.getByRole('button',{name:'Download package 1.0.0'})).toBeEnabled();
});
