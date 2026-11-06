import React from 'react';
import {render,screen,fireEvent,act} from '@testing-library/react';
import {vi} from 'vitest';
import WorkspaceBreadcrumbs from './WorkspaceBreadcrumbs';
test('breadcrumbs follow URL views and history controls use browser navigation',()=>{
 window.history.replaceState(null,'','#/data-products?view=analytics&analytics_step=1');
 const back=vi.spyOn(window.history,'back').mockImplementation(()=>{}),forward=vi.spyOn(window.history,'forward').mockImplementation(()=>{});
 render(<WorkspaceBreadcrumbs page="data-products" label="Data Products"/>);
 expect(screen.getByText('Configure analysis')).toHaveAttribute('aria-current','page');
 expect(screen.getByRole('link',{name:'Home'})).toHaveAttribute('href','#/home');
 fireEvent.click(screen.getByRole('button',{name:'Go back'}));expect(back).toHaveBeenCalledTimes(1);
 fireEvent.click(screen.getByRole('button',{name:'Go forward'}));expect(forward).toHaveBeenCalledTimes(1);
 act(()=>{window.history.replaceState(null,'','#/data-products?run_id=r');window.dispatchEvent(new PopStateEvent('popstate'));});
 expect(screen.getByText('Run details')).toHaveAttribute('aria-current','page');
 back.mockRestore();forward.mockRestore();
});

test('analytics step never overrides a different workspace breadcrumb',()=>{
 window.history.replaceState(null,'','#/data-products?view=governance&analytics_step=1');
 render(<WorkspaceBreadcrumbs page="data-products" label="Data Products"/>);
 expect(screen.getByText('Governance')).toHaveAttribute('aria-current','page');
 expect(screen.queryByText('Configure analysis')).toBeNull();
});
