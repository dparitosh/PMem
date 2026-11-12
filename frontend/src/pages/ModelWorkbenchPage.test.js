import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { vi } from 'vitest';
import ModelWorkbenchPage from './ModelWorkbenchPage';
import { useOntologies } from '../contexts/OntologyContext';
import graphApi from '../services/graphApi';
import { API_METHODS } from '../services/apiClient';

vi.mock('@siemens/ix-react', () => import('../ui/ix/ixReact.mock.js'));
vi.mock('../contexts/OntologyContext', () => ({ useOntologies: vi.fn(() => ({ ontologies: [], loading: false, error: '' })) }));
vi.mock('../services/graphApi', () => ({ default: { getArchitectureGraph: vi.fn(), getOntologyGraph: vi.fn() } }));
vi.mock('../services/apiClient', () => ({ API_METHODS: { modeling: { graph: vi.fn(), diagrams:vi.fn(), xmiContext:vi.fn(async (_ontology,id)=>({data:{status:'resolved',node_id:id,relationships:[],references:[]}})) } } }));
vi.mock('../Components/GraphMiner/GraphVisualizationWidget', () => ({ default: ({ graph, onSelect }) => <div data-testid="canvas">{graph.nodes.map(node => <button key={node.id} onClick={()=>onSelect(node)}>{node.id}</button>)}</div> }));
vi.mock('../features/graph/GraphInvestigation',()=>({ default: ({node,ontologyId,page})=><div data-testid="model-investigation">{page}|{ontologyId}|{node.elementId}</div> }));

test('switching model modes clears the previous canvas before the next response', async () => {
  graphApi.getArchitectureGraph.mockResolvedValue({ data: { nodes: [{ id: 'old-architecture', label: 'Old architecture', type: 'BusinessActor' }], links: [] } });
  API_METHODS.modeling.graph.mockReturnValue(new Promise(() => {}));
  const view = render(<ModelWorkbenchPage />);
  await waitFor(() => expect(screen.getByTestId('canvas')).toHaveTextContent('old-architecture'));
  const next = screen.getByRole('tab', { name: 'Systems engineering' });
  fireEvent.keyDown(screen.getByRole('tab', { name: 'Architecture' }), { key: 'ArrowRight' });
  expect(next).toHaveAttribute('aria-selected', 'true');
  expect(next).toHaveFocus();
  expect(screen.queryByTestId('canvas')).toBeNull();
  await waitFor(() => expect(API_METHODS.modeling.graph).toHaveBeenCalledTimes(1));
  const signal = API_METHODS.modeling.graph.mock.calls[0][1];
  view.unmount();
  expect(signal.aborted).toBe(true);
});


test('published XMI source uses its immutable ontology identity and keeps relationships', async () => {
  useOntologies.mockReturnValue({ ontologies: [{ ontology_id: 'sysml-version-1', label: 'SugarPlant', prefix: 'sysml', type: 'xmi' }], loading: false, error: '' });
  graphApi.getArchitectureGraph.mockResolvedValue({ data: { nodes: [], links: [] } });
  API_METHODS.modeling.diagrams.mockResolvedValue({ data: { nodes: [
    { elementId: 'part', properties: { label: 'Pump', kind: 'Class' } },
    { elementId: 'req', properties: { label: 'Pressure requirement', kind: 'Class' } }
  ], relationships: [{ elementId: 'trace', start: 'part', end: 'req', type: 'satisfies' }] } });
  render(<ModelWorkbenchPage />);
  fireEvent.click(screen.getByRole('tab', { name: 'Systems engineering' }));
  await waitFor(() => expect(API_METHODS.modeling.diagrams).toHaveBeenCalledWith('sysml-version-1', expect.any(AbortSignal)));
  await waitFor(() => expect(screen.getByTestId('canvas')).toHaveTextContent('part'));
  expect(screen.getByLabelText('Model source')).toHaveValue('sysml-version-1');
  expect(screen.getByTestId('canvas')).toHaveTextContent('req');
  fireEvent.change(screen.getByLabelText('Find model element'), { target: { value: 'No such pump' } });
  expect(screen.queryByTestId('canvas')).toBeNull();
  fireEvent.change(screen.getByLabelText('Find model element'), { target: { value: 'Pressure requirement' } });
  expect(screen.getByTestId('canvas')).toHaveTextContent('req');
  expect(screen.getByTestId('canvas')).not.toHaveTextContent('part');
});


test('a late XMI response cannot overwrite a different selected source', async () => {
  useOntologies.mockReturnValue({ ontologies: ['one', 'two'].map(id => ({ ontology_id: id, label: id, prefix: 'sysml', type: 'xmi' })) });
  let finishFirst;
  API_METHODS.modeling.diagrams.mockImplementation(id => id === 'one' ? new Promise(resolve => { finishFirst = resolve; }) : Promise.resolve({ data: { nodes: [{ id: 'second', label: 'Current source' }], links: [] } }));
  render(<ModelWorkbenchPage />);
  fireEvent.click(screen.getByRole('tab', { name: 'Systems engineering' }));
  await waitFor(() => expect(finishFirst).toBeDefined());
  fireEvent.change(screen.getByLabelText('Model source'), { target: { value: 'two' } });
  await waitFor(() => expect(screen.getByTestId('canvas')).toHaveTextContent('second'));
  finishFirst({ data: { nodes: [{ id: 'stale', label: 'Old source' }], links: [] } });
  await waitFor(() => expect(screen.getByTestId('canvas')).not.toHaveTextContent('stale'));
});


test('selected model identity reaches Companion and investigation and clears on departure',async()=>{
 useOntologies.mockReturnValue({ontologies:[{ontology_id:'sysml-v2',prefix:'sysml',label:'Plant',type:'xmi'}]});
 API_METHODS.modeling.diagrams.mockResolvedValue({data:{nodes:[{id:'requirement-42',label:'Drive requirement',type:'Class'}],links:[]}});
 const selection=vi.fn(),openChat=vi.fn();
 const view=render(<ModelWorkbenchPage onBusinessSelection={selection} toggleChat={openChat}/>);
 fireEvent.click(screen.getByRole('tab',{name:'Systems engineering'}));
 await waitFor(()=>expect(screen.getByRole('button',{name:'requirement-42',exact:true})).toBeInTheDocument());
 fireEvent.click(screen.getByRole('button',{name:'requirement-42',exact:true}));
 await waitFor(()=>expect(selection).toHaveBeenLastCalledWith(expect.objectContaining({node_id:'requirement-42',ontology_id:'sysml-v2',ontology_prefix:'sysml'})));
 expect(screen.getByTestId('model-investigation')).toHaveTextContent('modeling|sysml-v2|requirement-42');
 fireEvent.click(screen.getByRole('button',{name:'Ask Companion about this element'}));
 expect(openChat).toHaveBeenCalledTimes(1);
 view.unmount();expect(selection).toHaveBeenLastCalledWith(null);
});

beforeEach(()=>{window.history.replaceState(null,'','#/modeling');useOntologies.mockReturnValue({ontologies:[],loading:false,error:''});});
test('model viewer deep link and history select the correct mode',async()=>{
 window.history.replaceState(null,'','#/modeling?view=mbse');API_METHODS.modeling.graph.mockResolvedValue({data:{nodes:[],links:[]}});
 graphApi.getArchitectureGraph.mockResolvedValue({data:{nodes:[],links:[]}});
 render(<ModelWorkbenchPage/>);expect(screen.getByRole('tab',{name:'Systems engineering'})).toHaveAttribute('aria-selected','true');
 fireEvent.click(screen.getByRole('tab',{name:'Architecture'}));expect(window.location.hash).toContain('view=architecture');
 await act(async()=>{window.history.replaceState(null,'','#/modeling?view=mbse');window.dispatchEvent(new PopStateEvent('popstate'));});
 expect(screen.getByRole('tab',{name:'Systems engineering'})).toHaveAttribute('aria-selected','true');
});
