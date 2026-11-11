import React from 'react';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {vi} from 'vitest';
import ActionReviewDialog from './ActionReviewDialog';
const action={label:'Cancel workflow',name:'Review source',items:[['Run ID','original-run']],description:'Cancel this execution at a safe boundary.',retryable:false};
test('review initially focuses close and Escape restores the opener',()=>{
 const opener=document.createElement('button');document.body.append(opener);opener.focus();
 const close=vi.fn(),view=render(<ActionReviewDialog action={action} onClose={close} onConfirm={vi.fn()}/>);
 expect(screen.getByRole('button',{name:'Close action review'})).toHaveFocus();
 fireEvent.keyDown(screen.getByRole('dialog'),{key:'Escape'});expect(close).toHaveBeenCalledOnce();
 view.unmount();expect(opener).toHaveFocus();opener.remove();
});
test('unconfirmed non-idempotent action keeps its target and removes blind retry',async()=>{
 const submit=vi.fn().mockRejectedValue(new Error('Response unavailable'));
 render(<ActionReviewDialog action={action} onClose={vi.fn()} onConfirm={submit}/>);
 fireEvent.click(screen.getByRole('button',{name:'Confirm cancel workflow'}));
 await screen.findByRole('alert');expect(screen.getByText('original-run')).toBeVisible();
 expect(screen.queryByRole('button',{name:'Confirm cancel workflow'})).toBeNull();
 expect(submit).toHaveBeenCalledOnce();
});
test('pending submission blocks duplicates and accepted result retains original identity',async()=>{
 let finish;const submit=vi.fn(()=>new Promise(resolve=>{finish=resolve;}));
 render(<ActionReviewDialog action={action} onClose={vi.fn()} onConfirm={submit}/>);
 const button=screen.getByRole('button',{name:'Confirm cancel workflow'});fireEvent.click(button);fireEvent.click(button);
 expect(submit).toHaveBeenCalledOnce();expect(screen.getByRole('button',{name:'Submitting…'})).toBeDisabled();
 finish({label:'Request accepted',message:'Inspect retained state',runId:'result-run'});
 await waitFor(()=>expect(screen.getByText('Request accepted')).toBeVisible());
 expect(screen.getByText('original-run')).toBeVisible();expect(screen.getByText('result-run')).toBeVisible();
});
