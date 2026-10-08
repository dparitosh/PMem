import React,{useState} from 'react';
import {fireEvent,render,screen} from '@testing-library/react';
import WorkspaceTabs from './WorkspaceTabs';
test('keyboard navigation updates selection and focus without remounting tabs',()=>{
 function Harness(){const [value,setValue]=useState('a');return <WorkspaceTabs label="Views" tabs={[{id:'a',label:'First'},{id:'b',label:'Second'}]} value={value} onChange={setValue}/>;}
 render(<Harness/>);
 const first=screen.getByRole('tab',{name:'First'}),second=screen.getByRole('tab',{name:'Second'});
 fireEvent.keyDown(first,{key:'ArrowRight'});
 expect(second).toHaveAttribute('aria-selected','true'); expect(second).toHaveFocus();
 fireEvent.keyDown(second,{key:'Home'});
 expect(first).toHaveAttribute('aria-selected','true'); expect(first).toHaveFocus();
});
