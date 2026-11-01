import React from 'react';
import {render,screen} from '@testing-library/react';
import {vi} from 'vitest';
import AppPageOutlet from './AppPageOutlet';
vi.mock('./pageRegistry',()=>({resolvePage:page=>({component:page==='broken'?function Broken(){throw new Error('route failure');}:()=> <h2>Healthy workspace</h2>})}));
test('a failed page does not trap navigation to another workspace',()=>{
 const error=vi.spyOn(console,'error').mockImplementation(()=>{});
 try {
  const {rerender}=render(<AppPageOutlet page="broken" pageContext={{}}/>);
  expect(screen.getByText(/Something went wrong/)).toBeInTheDocument();
  rerender(<AppPageOutlet page="healthy" pageContext={{}}/>);
  expect(screen.getByRole('heading',{name:'Healthy workspace'})).toBeInTheDocument();
 }finally{error.mockRestore();}
});
