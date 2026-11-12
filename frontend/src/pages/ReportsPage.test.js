import React from 'react';
import {vi} from 'vitest';
import {render,screen,fireEvent,act} from '@testing-library/react';
import ReportsPage from './ReportsPage';
vi.mock('../Components/MemoryRecords',()=>({default:()=> <p>Saved memory records</p>}));
vi.mock('../Components/ReportsTab',()=>({default:()=> <p>Engineering evidence reports</p>}));
beforeEach(()=>window.history.replaceState(null,'','#/reports'));
test('report view survives remount and browser history',async()=>{
 const page=render(<ReportsPage/>);fireEvent.click(screen.getByRole('button',{name:'Engineering reports'}));
 expect(window.location.hash).toContain('view=engineering');page.unmount();render(<ReportsPage/>);
 expect(screen.getByText('Engineering evidence reports')).toBeVisible();
 await act(async()=>{window.history.replaceState(null,'','#/reports?view=memory');window.dispatchEvent(new PopStateEvent('popstate'));});
 expect(screen.getByText('Saved memory records')).toBeVisible();
});
