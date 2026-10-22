import React from 'react';
import {render,screen,within,fireEvent} from '@testing-library/react';
import EvidenceProductOptions from './EvidenceProductOptions';
test('empty catalog still explains both available evidence workflows and links to the right tools',()=>{
 render(<EvidenceProductOptions catalog draftCount={0}/>);
 expect(screen.getByRole('heading',{name:'Structural analytics'})).toBeVisible();
 expect(screen.queryByRole('heading',{name:'Pipeline evidence'})).toBeNull();
 expect(screen.getByRole('link',{name:'Review structural analytics'})).toHaveAttribute('href','#/data-products?view=structural');
 fireEvent.click(screen.getByRole('tab',{name:'Pipeline evidence'}));
 expect(screen.getByRole('link',{name:'Review pipeline evidence'})).toHaveAttribute('href','#/data-products?view=pipeline');
 expect(screen.getByRole('tabpanel')).toHaveAccessibleName('Pipeline evidence');
});
test('counts retained versions by actual evidence kind',()=>{
 render(<EvidenceProductOptions rows={[{product_kind:'schema-design-evidence'},{product_kind:'pipeline-evidence'},{product_kind:'pipeline-evidence'}]} draftCount={4}/>);
 const structural=screen.getByRole('heading',{name:'Structural analytics'}).closest('article');
 expect(within(structural).getByText('4')).toBeVisible();expect(within(structural).getByText('1')).toBeVisible();
 fireEvent.click(screen.getByRole('tab',{name:'Pipeline evidence'}));
 expect(within(screen.getByRole('tabpanel')).getByText('2')).toBeVisible();
});
test('failed retrieval is unavailable rather than a zero-product claim',()=>{
 render(<EvidenceProductOptions error="Offline" draftCount={null}/>);
 expect(within(screen.getByRole('tabpanel')).getByText('Unavailable')).toBeVisible();
 expect(screen.getByText('Not verified')).toBeVisible();
 expect(screen.queryByText('0')).not.toBeInTheDocument();
});
test('product actions reveal the existing workflows without approving or publishing',()=>{
 const structural=vi.fn(),pipeline=vi.fn();
 render(<EvidenceProductOptions onStructural={structural} onPipeline={pipeline}/>);
 fireEvent.click(screen.getByRole('button',{name:'Review structural analytics'}));
 fireEvent.click(screen.getByRole('tab',{name:'Pipeline evidence'}));
 fireEvent.click(screen.getByRole('button',{name:'Review pipeline evidence'}));
 expect(structural).toHaveBeenCalledOnce();expect(pipeline).toHaveBeenCalledOnce();
});

test('subtabs support keyboard navigation and preserve action boundaries',()=>{
 render(<EvidenceProductOptions/>);
 const structural=screen.getByRole('tab',{name:'Structural analytics'});
 const pipeline=screen.getByRole('tab',{name:'Pipeline evidence'});
 structural.focus();fireEvent.keyDown(structural,{key:'ArrowRight'});
 expect(pipeline).toHaveFocus();expect(pipeline).toHaveAttribute('aria-selected','true');
 expect(screen.queryByRole('button',{name:'Review structural analytics'})).toBeNull();
 fireEvent.keyDown(pipeline,{key:'Home'});expect(structural).toHaveFocus();
 fireEvent.keyDown(structural,{key:'End'});expect(pipeline).toHaveFocus();
 fireEvent.keyDown(pipeline,{key:'ArrowLeft'});expect(structural).toHaveFocus();
});
