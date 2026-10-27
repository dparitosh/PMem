import React from 'react';
import {act,render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import WhereUsed from '../Components/WhereUsedView.js';
import {graphApi} from '../services/graphApi.js';
vi.mock('../SchemaContext.js',()=>({useSchema:()=>({})}));
vi.mock('../widgets/DataGridWidget.js',()=>({default:({rows,title})=><section aria-label={title}>{rows.map((row,i)=><div key={i}>{row.displayName}</div>)}</section>}));
vi.mock('../services/graphApi.js',()=>({graphApi:{getTraversal:vi.fn(),getOverview:vi.fn()}}));
const root={elementId:'root',labels:['Part'],properties:{name:'AuditBearing'}};
const parent={elementId:'parent',labels:['Assembly'],properties:{name:'AuditAssembly'}};
const search=value=>{fireEvent.change(screen.getByRole('textbox'),{target:{value}});fireEvent.click(screen.getByRole('button',{name:'Search'}));};
afterEach(()=>{cleanup();vi.clearAllMocks();});
test('WU-01 regression: a late traversal repopulates a hierarchy after a new unmatched search',async()=>{
 let finish;graphApi.getTraversal.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;})).mockResolvedValue({data:{nodes:[parent],links:[]}});
 render(<WhereUsed data={{nodes:[root],links:[]}}/>);search('AuditBearing');
 await waitFor(()=>expect(graphApi.getTraversal).toHaveBeenCalled());
 const signal=graphApi.getTraversal.mock.calls[0][2];search('NoSuchObject');
 expect(signal.aborted).toBe(true);
 await act(async()=>{finish({data:{nodes:[root,parent],links:[{elementId:'uses',source:'parent',target:'root',type:'HAS_PART'}]}});});
 expect(screen.getByRole('status',{name:'Search outcome'})).toHaveTextContent('No matching');
 expect(screen.queryByRole('region',{name:'Business object usage'})).toBeNull();
});
test('WU-02 regression: child PART_OF assembly is included in upward usage',async()=>{
 graphApi.getTraversal.mockResolvedValue({data:{nodes:[root,parent],links:[{elementId:'partof',source:'root',target:'parent',type:'PART_OF'}]}});
 render(<WhereUsed data={{nodes:[root],links:[]}}/>);search('AuditBearing');
 await waitFor(()=>expect(screen.getByRole('region',{name:'Business object usage'})).toBeVisible());
 expect(screen.getByRole('region',{name:'Business object usage'})).toHaveTextContent('AuditAssembly');
});

test('declared usage predicates are read from semantic relationships without exposing their assertion carrier',async()=>{
 graphApi.getTraversal.mockResolvedValue({data:{nodes:[root,parent],links:[{elementId:'semantic-use',source:'parent',target:'root',type:'SEMANTIC_RELATION',properties:{predicate:'https://example.test/business#hasComponent'}}]}});
 render(<WhereUsed data={{nodes:[root],links:[]}}/>);search('AuditBearing');
 await waitFor(()=>expect(screen.getByRole('region',{name:'Business object usage'})).toHaveTextContent('AuditAssembly'));
 expect(screen.getByText(/Source-provided usage links/)).toBeVisible();
});
test('WU-03 regression: session replacement leaves previous identity graph evidence visible',async()=>{
 graphApi.getTraversal.mockResolvedValue({data:{nodes:[root,parent],links:[{elementId:'uses',source:'parent',target:'root',type:'HAS_PART'}]}});
 render(<WhereUsed data={{nodes:[root],links:[]}}/>);search('AuditBearing');
 await screen.findByRole('region',{name:'Business object usage'});
 fireEvent(window,new Event('depo:session-replaced'));
 expect(screen.queryByRole('region',{name:'Business object usage'})).toBeNull();
});
test('WU-04 regression: provenance assertion metadata is counted as an upstream business record',async()=>{
 const assertion={elementId:'assertion',labels:['OntologyResource'],properties:{name:'urn:depo:assertion:audit'}};
 graphApi.getTraversal.mockResolvedValue({data:{nodes:[root,assertion],links:[{elementId:'evidence-edge',source:'assertion',target:'root',type:'SUBJECT'}]}});
 render(<WhereUsed data={{nodes:[root],links:[]}}/>);search('AuditBearing');
 await screen.findByRole('region',{name:'Business object usage'});
 expect(screen.getByRole('region',{name:'Business object usage'})).not.toHaveTextContent('urn:depo:assertion:audit');
 expect(screen.getByText(/Upstream records/)).toHaveTextContent('Upstream records 0');
});
