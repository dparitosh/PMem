import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import MergeWorkflowControls from './MergeWorkflowControls';

const props = {sourceId:'ap242',targetId:'qif',reviewer:'steward',connected:true,selectionCount:0,onGenerate:vi.fn(),onResume:vi.fn(),onPublish:vi.fn(),onReviewerChange:vi.fn()};

test('first action generates evidence and does not offer publication before a plan',()=>{
 render(<MergeWorkflowControls {...props}/>);
 fireEvent.click(screen.getByRole('button',{name:'Generate mapping plan'}));
 expect(props.onGenerate).toHaveBeenCalled();
 expect(screen.getByRole('button',{name:'Approve merge and publish'})).toBeDisabled();
 expect(screen.getByRole('status')).toHaveTextContent('does not publish');
});

test('pending validation has a clear state and prevents duplicate plan requests and approval',()=>{
 render(<MergeWorkflowControls {...props} preview={{background_validation:true,job_status:'validating'}}/>);
 expect(screen.getByRole('status')).toHaveTextContent('Validating semantic constraints');
 expect(screen.getByRole('button',{name:'Validation running'})).toBeDisabled();
 expect(screen.getByRole('button',{name:'Approve merge and publish'})).toBeDisabled();
 expect(screen.getByRole('button',{name:'Resume saved plan'})).toBeEnabled();
});

test('changed selection requires a new validated plan even if the previous plan was ready',()=>{
 render(<MergeWorkflowControls {...props} preview={{job_status:'completed'}} ready dirty selectionCount={2}/>);
 expect(screen.getByRole('status')).toHaveTextContent('Your selections are retained');
 expect(screen.getByRole('button',{name:'Validate selected mappings'})).toBeEnabled();
 expect(screen.getByRole('button',{name:'Approve merge and publish'})).toBeDisabled();
});

test('current plan explains union behavior and enables explicit publication',()=>{
 render(<MergeWorkflowControls {...props} preview={{job_status:'completed'}} ready/>);
 expect(screen.getByRole('button',{name:'Approve merge and publish'})).toBeEnabled();
 expect(screen.getByRole('status')).toHaveTextContent('0 identity consolidations');
 expect(screen.getByText(/With no pairs selected/)).toHaveTextContent('preserving their distinct identities');
});

test('unconnected access and a retained publication each explain why actions are unavailable',()=>{
 const view=render(<MergeWorkflowControls {...props} connected={false}/>);
 expect(screen.getByRole('link',{name:'Connect agent access in Admin'})).toHaveAttribute('href','#/admin');
 expect(screen.getByRole('button',{name:'Generate mapping plan'})).toBeDisabled();
 view.rerender(<MergeWorkflowControls {...props} preview={{job_status:'completed'}} ready publication="queued"/>);
 expect(screen.getByRole('status')).toHaveTextContent('Publication in progress');
 expect(screen.getByRole('button',{name:'Approve merge and publish'})).toBeDisabled();
});
