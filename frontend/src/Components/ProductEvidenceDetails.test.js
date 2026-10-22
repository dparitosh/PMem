import React from 'react';
import {render,screen} from '@testing-library/react';
import ProductEvidenceDetails from './ProductEvidenceDetails';
test('shows ownership, readiness and pending delivery without requiring raw JSON',()=>{
 render(<ProductEvidenceDetails detail={{product_id:'quality',name:'Inspection results',owner:'Metrology',analytics_readiness:'evidence-only',status:'pending_catalog_registration',sources:[{run_id:'run-1'}],artifacts:[{}]}}/>);
 expect(screen.getByRole('heading',{name:'Inspection results'})).toBeVisible();
 expect(screen.getByText('Metrology')).toBeVisible();
 expect(screen.getByText('evidence-only')).toBeVisible();
 expect(screen.getByRole('status')).toHaveTextContent('Package retained; catalog delivery needs attention');
 expect(screen.getByText('Technical record').closest('details')).not.toHaveAttribute('open');
});
test('catalog versions retain individual owners and missing values are explicit',()=>{
 render(<ProductEvidenceDetails detail={{product_id:'parts',versions:[{version:'1.0.0',owner:'PLM'},{version:'2.0.0',owner:'Manufacturing'}]}}/>);
 expect(screen.getByText('1.0.0')).toBeVisible();expect(screen.getByText('2.0.0')).toBeVisible();
 expect(screen.getByText('PLM')).toBeVisible();expect(screen.getByText('Manufacturing')).toBeVisible();
 expect(screen.getAllByText('Not recorded').length).toBeGreaterThan(0);
});
