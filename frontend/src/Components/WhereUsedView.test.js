import React from 'react';
import { vi, test, expect } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import WhereUsedView from './WhereUsedView';
import { graphApi } from '../services/graphApi';
vi.mock('../SchemaContext', () => ({useSchema: () => ({})}));
vi.mock('../widgets/DataGridWidget', () => ({default: ({rows}) => <div>{rows.map(row => <span key={row.id || row.nodeId}>{row.displayName}</span>)}</div>}));
vi.mock('../services/graphApi', () => ({graphApi: {getTraversal: vi.fn(), getOverview: vi.fn(async () => ({data:{nodes:[],links:[]}}))}}));
const root = {elementId:'root',labels:['Part'],properties:{name:'Root'}};

test('an unmatched search explains the snapshot boundary without claiming full-graph absence', () => {
 render(<WhereUsedView data={{nodes:[root],links:[]}} />);
 fireEvent.change(screen.getByRole('textbox'), {target:{value:'Absent business object'}});
 fireEvent.click(screen.getByRole('button',{name:'Search'}));
 expect(screen.getByRole('status',{name:'Search outcome'})).toHaveTextContent('No matching business objects in the loaded graph snapshot');
 expect(screen.getByRole('status',{name:'Search outcome'})).toHaveTextContent('does not prove the object is absent from the full graph');
 fireEvent(window, new Event('depo:credentials-cleared'));
 expect(screen.queryByRole('status',{name:'Search outcome'})).toBeNull();
});
test('upward traversal stops at the depth budget and shows partial evidence', async () => {
 graphApi.getTraversal.mockImplementation(async id => {
   const depth = id === 'root' ? 0 : Number(id.slice(1));
   const parent = `p${depth+1}`;
   return {data:{nodes:[{elementId:id},{elementId:parent}],links:[{elementId:`e${depth}`,source:parent,target:id,type:'USES'}]}};
 });
 render(<WhereUsedView data={{nodes:[root],links:[]}} />);
 fireEvent.change(screen.getByRole('textbox'), {target:{value:'Root'}});
 fireEvent.click(screen.getByRole('button',{name:'Search'}));
 await screen.findByText(/Partial hierarchy: reached the safety limit/);
 expect(graphApi.getTraversal).toHaveBeenCalledTimes(10);
 fireEvent(window, new Event('depo:credentials-cleared'));
 await waitFor(() => expect(screen.queryByText(/Partial hierarchy: reached/)).toBeNull());
});

