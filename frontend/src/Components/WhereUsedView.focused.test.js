import React from 'react';
import {vi,test,expect} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import WhereUsedView from './WhereUsedView';
import WhereUsedPage from '../pages/WhereUsedPage';
import {graphApi} from '../services/graphApi';
vi.mock('../SchemaContext',()=>({useSchema:()=>({})}));
vi.mock('../widgets/DataGridWidget',()=>({default:()=>null}));
vi.mock('../widgets/GraphWidget',()=>({default:({children})=><>{children}</>}));
vi.mock('../services/graphApi',()=>({graphApi:{searchBusiness:vi.fn(),getTraversal:vi.fn()}}));
const part={elementId:'outside-overview',labels:['Part'],properties:{name:'Motor Cover Machined'}};
test('standalone finds a business object absent from the overview and traverses its identity',async()=>{
 graphApi.searchBusiness.mockResolvedValue({data:{nodes:[part],relationships:[]}});
 graphApi.getTraversal.mockResolvedValue({data:{nodes:[part],links:[]}});
 render(<WhereUsedPage data={{nodes:[{elementId:'unrelated-schema',labels:['OntologyClass']}],links:[]}}/>);
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'Motor Cover Machined'}});
 fireEvent.click(screen.getByRole('button',{name:'Search'}));
 await waitFor(()=>expect(graphApi.getTraversal).toHaveBeenCalledWith('outside-overview',1,expect.any(AbortSignal)));
 expect(graphApi.searchBusiness).toHaveBeenCalledWith('Motor Cover Machined',expect.any(AbortSignal));
 await screen.findByText(/No upstream references were returned for Part - Motor Cover Machined/);
});
test('editing the query invalidates a late focused-search response',async()=>{
 let resolve;
 graphApi.searchBusiness.mockImplementation(()=>new Promise(r=>{resolve=r;}));
 graphApi.getTraversal.mockClear();
 render(<WhereUsedView/>);
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'Motor Cover Machined'}});
 fireEvent.click(screen.getByRole('button',{name:'Search'}));
 const signal=graphApi.searchBusiness.mock.calls.at(-1)[1];
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'Bearing'}});
 expect(signal.aborted).toBe(true);
 resolve({data:{nodes:[part]}});
 await waitFor(()=>expect(screen.getByRole('button',{name:'Search'})).toBeEnabled());
 expect(graphApi.getTraversal).not.toHaveBeenCalled();
 expect(screen.queryByRole('region',{name:'Business object usage'})).toBeNull();
});

