import React,{useState} from 'react';
import {render,screen,fireEvent} from '@testing-library/react';
import DataWorkspace,{DataJourney} from './DataWorkspace';
function Example(){const [active,setActive]=useState('runs');return <DataWorkspace label="Operations" active={active} onChange={setActive} tabs={[{id:'runs',label:'Runs'},{id:'settings',label:'Settings'}]}>{{runs:<button>Inspect run</button>,settings:<label>Reviewer<input/></label>}}</DataWorkspace>;}
test('workspace navigation preserves entered settings and exposes only the active panel',()=>{
 render(<Example/>);
 expect(screen.getByRole('tabpanel')).toHaveAccessibleName('Runs');
 fireEvent.click(screen.getByRole('tab',{name:'Settings'}));
 fireEvent.change(screen.getByLabelText('Reviewer'),{target:{value:'steward'}});
 fireEvent.keyDown(screen.getByRole('tab',{name:'Settings'}),{key:'ArrowRight'});
 expect(screen.getByRole('tab',{name:'Runs'})).toHaveFocus();
 expect(screen.queryByRole('textbox')).toBeNull();
 fireEvent.keyDown(screen.getByRole('tab',{name:'Runs'}),{key:'End'});
 expect(screen.getByRole('textbox')).toHaveValue('steward');
 fireEvent.keyDown(screen.getByRole('tab',{name:'Settings'}),{key:'Home'});
 expect(screen.getByRole('tab',{name:'Runs'})).toHaveAttribute('aria-selected','true');
});
test('journey is navigation and does not claim completed lifecycle steps',()=>{
 render(<DataJourney current="products"/>);
 expect(screen.getByRole('link',{name:/Build products/})).toHaveAttribute('aria-current','step');
 expect(screen.getByRole('link',{name:/Process & validate/})).toHaveAttribute('href','#/data-flow');
 expect(screen.queryByText(/completed/i)).toBeNull();
});
