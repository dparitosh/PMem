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

test.each(['definitions','pipelines'])('Data Flow %s breadcrumb matches the pipeline job view',view=>{
 window.history.replaceState(null,'',`#/data-flow?view=${view}`);
 render(<WorkspaceBreadcrumbs page="data-flow" label="Data Flow"/>);
 expect(screen.getByText('Pipeline jobs')).toHaveAttribute('aria-current','page');
 expect(screen.queryByText('Definitions')).toBeNull();
});


test('retained run context does not hide the selected Event reviews breadcrumb',()=>{
 window.history.replaceState(null,'','#/data-flow?view=events&run_id=retained-run');render(<WorkspaceBreadcrumbs page="data-flow" label="Data Flow"/>);
 expect(screen.getByText('Event reviews')).toBeInTheDocument();expect(screen.queryByText('Run details')).toBeNull();
});

test.each(['data-flow','admin','graph','modeling','requirements','qif','registry','home'])('foreign analytics parameters do not label the %s workspace',page=>{
 window.history.replaceState(null,'',`#/${page}?view=analytics&analytics_step=1&run_id=foreign`);render(<WorkspaceBreadcrumbs page={page} label={page}/>);
 expect(screen.queryByText('Available analytics')).not.toBeInTheDocument();expect(screen.queryByText('Configure analysis')).not.toBeInTheDocument();
 if(page!=='data-flow')expect(screen.queryByText('Run details')).not.toBeInTheDocument();
});
