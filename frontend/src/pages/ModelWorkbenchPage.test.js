import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import ModelWorkbenchPage from './ModelWorkbenchPage';
import { useOntologies } from '../contexts/OntologyContext';
import graphApi from '../services/graphApi';
import { API_METHODS } from '../services/apiClient';

vi.mock('../contexts/OntologyContext', () => ({ useOntologies: vi.fn(() => ({ ontologies: [], loading: false, error: '' })) }));
vi.mock('../services/graphApi', () => ({ default: { getArchitectureGraph: vi.fn(), getOntologyGraph: vi.fn() } }));
vi.mock('../services/apiClient', () => ({ API_METHODS: { modeling: { graph: vi.fn(), diagrams: vi.fn(), xmiContext: vi.fn().mockResolvedValue({data:{status:'unpublished',nodes:[],links:[]}}) } } }));
vi.mock('../Components/GraphMiner/GraphVisualizationWidget', () => ({ default: ({ graph, onSelect }) => <div data-testid="canvas">{graph.nodes.map(node => <button key={node.id} onClick={()=>onSelect(node)}>{node.id}</button>)}</div> }));
vi.mock('./SysMLDiagram',()=>({ default: ({graph,onSelect})=><div data-testid="canvas">{graph.nodes.map(node=><button key={node.id} onClick={()=>onSelect(node)}>{node.id}</button>)}</div> }));
vi.mock('../features/graph/GraphInvestigation',()=>({ default: ({node,ontologyId,page})=><div data-testid="model-investigation">{page}|{ontologyId}|{node.elementId}</div> }));

test('switching model modes clears the previous canvas before the next response', async () => {
  graphApi.getArchitectureGraph.mockResolvedValue({ data: { nodes: [{ id: 'old-architecture', label: 'Old architecture', type: 'BusinessActor' }], links: [] } });
  API_METHODS.modeling.graph.mockReturnValue(new Promise(() => {}));
  const view = render(<ModelWorkbenchPage />);
  await waitFor(() => expect(screen.getByTestId('canvas')).toHaveTextContent('old-architecture'));
  const next = screen.getByRole('tab', { name: 'MBSE / SysML / UML' });
  fireEvent.keyDown(screen.getByRole('tab', { name: 'ArchiMate' }), { key: 'ArrowRight' });
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
  API_METHODS.modeling.diagrams.mockResolvedValue({ data: { message: 'Generated layout', representations:[{id:'req-view',name:'Requirements',type:'Requirement Diagram',nodeIds:['part','req']}], nodes: [
    { elementId: 'part', properties: { label: 'Pump', kind: 'Class' } },
    { elementId: 'req', properties: { label: 'Pressure requirement', kind: 'Class' } }
  ], relationships: [{ elementId: 'trace', start: 'part', end: 'req', type: 'satisfies' }] } });
  render(<ModelWorkbenchPage />);
  fireEvent.click(screen.getByRole('tab', { name: 'MBSE / SysML / UML' }));
  await waitFor(() => expect(API_METHODS.modeling.diagrams).toHaveBeenCalledWith('sysml-version-1', expect.any(AbortSignal)));
  await waitFor(() => expect(screen.getByTestId('canvas')).toHaveTextContent('part'));
  expect(screen.getByLabelText('Model source')).toHaveValue('sysml-version-1');
  expect(screen.getByText(/Generated layout/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Find model element'), { target: { value: 'No such pump' } });
  expect(screen.getByTestId('canvas')).not.toHaveTextContent('part');
  fireEvent.change(screen.getByLabelText('Find model element'), { target: { value: 'Pressure requirement' } });
  expect(screen.getByTestId('canvas')).toHaveTextContent('req');
  expect(screen.getByTestId('canvas')).not.toHaveTextContent('part');
});


test('a late XMI response cannot overwrite a different selected source', async () => {
  useOntologies.mockReturnValue({ ontologies: ['one', 'two'].map(id => ({ ontology_id: id, label: id, prefix: 'sysml', type: 'xmi' })) });
  let finishFirst;
  API_METHODS.modeling.diagrams.mockImplementation(id => id === 'one' ? new Promise(resolve => { finishFirst = resolve; }) : Promise.resolve({ data: { nodes: [{ id: 'second', label: 'Current source' }], links: [] } }));
  render(<ModelWorkbenchPage />);
  fireEvent.click(screen.getByRole('tab', { name: 'MBSE / SysML / UML' }));
  await waitFor(() => expect(finishFirst).toBeDefined());
  fireEvent.change(screen.getByLabelText('Model source'), { target: { value: 'two' } });
  await waitFor(() => expect(screen.getByTestId('canvas')).toHaveTextContent('second'));
  finishFirst({ data: { nodes: [{ id: 'stale', label: 'Old source' }], links: [] } });
  await waitFor(() => expect(screen.getByTestId('canvas')).not.toHaveTextContent('stale'));
});


test('selected model identity reaches Companion and investigation and clears on departure',async()=>{
 useOntologies.mockReturnValue({ontologies:[{ontology_id:'sysml-v2',prefix:'sysml',label:'Plant',type:'xmi'}]});
 API_METHODS.modeling.diagrams.mockResolvedValue({data:{nodes:[{id:'requirement-42',label:'Drive requirement',type:'Requirement'}],links:[],representations:[{id:'view',name:'Drive',type:'Requirement Diagram',nodeIds:['requirement-42']}]}});
 API_METHODS.modeling.xmiContext.mockResolvedValue({data:{node_id:'requirement-42',status:'resolved',nodes:[],links:[]}});
 const selection=vi.fn(),openChat=vi.fn();
 const view=render(<ModelWorkbenchPage onBusinessSelection={selection} toggleChat={openChat}/>);
 fireEvent.click(screen.getByRole('tab',{name:'MBSE / SysML / UML'}));
 await waitFor(()=>expect(screen.getByRole('button',{name:'requirement-42',exact:true})).toBeInTheDocument());
 fireEvent.click(screen.getByRole('button',{name:'requirement-42',exact:true}));
 await waitFor(()=>expect(selection).toHaveBeenLastCalledWith(expect.objectContaining({node_id:'requirement-42',ontology_id:'sysml-v2',ontology_prefix:'sysml'})));
 expect(screen.getByTestId('model-investigation')).toHaveTextContent('modeling|sysml-v2|requirement-42');
 fireEvent.click(screen.getByRole('button',{name:'Ask Companion about this element'}));
 expect(openChat).toHaveBeenCalledTimes(1);
 view.unmount();expect(selection).toHaveBeenLastCalledWith(null);
});


test('diagram is usable before graph context resolves and search clears selection',async()=>{
 useOntologies.mockReturnValue({ontologies:[{ontology_id:'sysml-v3',prefix:'sysml',label:'Plant',type:'xmi'}]});
 API_METHODS.modeling.xmiContext.mockReturnValue(new Promise(()=>{}));
 API_METHODS.modeling.diagrams.mockResolvedValue({data:{nodes:[{id:'r1',label:'Drive requirement',type:'Requirement'},{id:'outside',label:'Elsewhere',type:'Requirement'}],links:[],representations:[{id:'view',name:'Drive',type:'Requirement Diagram',nodeIds:['r1'],unresolvedIds:['missing']}]}});
 const selection=vi.fn();render(<ModelWorkbenchPage onBusinessSelection={selection}/>);
 fireEvent.click(screen.getByRole('tab',{name:'MBSE / SysML / UML'}));
 await waitFor(()=>expect(screen.getByRole('button',{name:'r1',exact:true})).toBeInTheDocument());
 expect(screen.getByText('Unresolved source reference: missing')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'r1',exact:true}));
 expect(screen.getByText('Checking recorded product and dataset associations…')).toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('Find model element'),{target:{value:'Elsewhere'}});
 expect(screen.queryByRole('button',{name:'Ask Companion about this element'})).toBeNull();
 expect(selection).toHaveBeenLastCalledWith(null);
 expect(screen.getByText('Model matches (0 in this view)')).toBeInTheDocument();
});

test('inspector pages all source relationships including off-view endpoints',async()=>{
 useOntologies.mockReturnValue({ontologies:[{ontology_id:'sysml-v4',prefix:'sysml',label:'Plant',type:'xmi'}]});
 API_METHODS.modeling.xmiContext.mockResolvedValue({data:{status:'unpublished'}});
 const others=Array.from({length:20},(_,i)=>({id:'other'+i,label:'Target '+i,type:'Class'}));
 API_METHODS.modeling.diagrams.mockResolvedValue({data:{nodes:[{id:'hub',label:'Hub',type:'Class'},...others],links:others.map(node=>({id:node.id,source:'hub',target:node.id,type:'TRACE'})),representations:[{id:'view',name:'Hub view',type:'Requirement Diagram',nodeIds:['hub']}]}});
 render(<ModelWorkbenchPage/>);fireEvent.click(screen.getByRole('tab',{name:'MBSE / SysML / UML'}));
 await waitFor(()=>expect(screen.getByRole('button',{name:'hub',exact:true})).toBeInTheDocument());
 fireEvent.click(screen.getByRole('button',{name:'hub',exact:true}));
 expect(screen.getByText('20 source-model relationships (0 visible in this view)')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Next relationships'}));
 expect(screen.getByText('Page 2 of 2')).toBeInTheDocument();
 expect(screen.getByText('-> TRACE Target 19')).toBeInTheDocument();
});
