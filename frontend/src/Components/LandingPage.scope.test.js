import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
const mocks = vi.hoisted(() => ({ getMetrics: vi.fn(), fetchOntologies: vi.fn() }));
vi.mock('@siemens/ix-react', () => {
  const Container = ({ children }) => <div>{children}</div>;
  return { IxBadge: Container, IxButton: Container, IxCard: Container, IxCardContent: Container, IxCardTitle: Container, IxCol: Container, IxLayoutGrid: Container };
});
vi.mock('../services/graphApi', () => ({ graphApi: { getMetrics: mocks.getMetrics } }));
vi.mock('../contexts/OntologyContext', () => ({ useOntologies: () => ({ ontologies: [{ ontology_id: 'qif-id', ontology_prefix: 'qif', name: 'QIF' }], fetchOntologies: mocks.fetchOntologies }) }));
vi.mock('./Chatbot', () => ({ default: ({nodeId,contextLabel}) => <div>Chat ready <span data-testid="chat-context">{nodeId}:{contextLabel}</span></div> }));
vi.mock('./HomeKnowledgeOverview',()=>({default:({ontologyId,revision,onSelectNode})=> <div data-testid="overview" data-revision={revision}>{ontologyId}<button onClick={()=>onSelectNode?.({elementId:'bearing:1',name:'Bearing A',properties:{ontology_id:'qif-id',ontology_prefix:'qif'}})}>Select bearing record</button></div>}));
import LandingPage from './LandingPage';
beforeEach(()=>{vi.clearAllMocks();window.history.replaceState(null,'','#/home');});

test('scope selection refreshes metrics using identity and namespace prefix', async () => {
  mocks.getMetrics.mockImplementation(async (id) => ({ data: { resources: 20, classes: id ? 7 : 12, scope: { sampled: false, type: 'published_rdf_projection', ontology_id: id } } }));
  render(<LandingPage />);
  await screen.findByText('12');
  fireEvent.change(screen.getByRole('combobox', { name: 'Ontology scope' }), { target: { value: 'qif-id' } });
  await screen.findByText('7');
  await waitFor(() => expect(mocks.getMetrics).toHaveBeenLastCalledWith('qif-id', expect.any(AbortSignal), 'qif'));
  expect(screen.getByRole('region', { name: 'Graph profile metrics' })).toHaveAttribute('tabindex', '0');
  expect(screen.getByText('Chat ready')).toBeVisible();
  const reads = mocks.getMetrics.mock.calls.length;
  fireEvent(window, new Event('focus'));
  await waitFor(() => expect(mocks.getMetrics.mock.calls.length).toBe(reads + 1));
  expect(mocks.getMetrics).toHaveBeenLastCalledWith('qif-id', expect.any(AbortSignal), 'qif');
});


test('slow scope responses do not show counts from another scope',async()=>{
 let finish;
 mocks.getMetrics.mockResolvedValueOnce({data:{resources:20,classes:12,scope:{sampled:false,type:'published_rdf_projection',ontology_id:''}}}).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
 render(<LandingPage/>);await screen.findByText('12');
 fireEvent.change(screen.getByRole('combobox',{name:'Ontology scope'}),{target:{value:'qif-id'}});
 expect(screen.queryByText('12')).toBeNull();expect(screen.getByText('Loading graph metrics…')).toBeVisible();
 finish({data:{resources:10,classes:7,scope:{sampled:false,type:'published_rdf_projection',ontology_id:'qif-id'}}});await screen.findByText('7');
 expect(window.location.hash).toContain('ontology_id=qif-id');
});

test('overview refresh is independent of metrics success and selected business context is reused',async()=>{
 mocks.getMetrics.mockResolvedValueOnce({data:{resources:20,classes:12,scope:{sampled:false,type:'published_rdf_projection',ontology_id:''}}}).mockRejectedValueOnce(new Error('metrics unavailable'));
 render(<LandingPage/>);await screen.findByText('12');
 expect(screen.getByTestId('overview')).toHaveAttribute('data-revision','0');
 fireEvent.click(screen.getByRole('button',{name:'Select bearing record'}));
 expect(screen.getByTestId('chat-context')).toHaveTextContent('bearing:1:Bearing A');
 expect(screen.getByRole('link',{name:/Review a decision/})).toHaveAttribute('href',expect.stringContaining('node_id=bearing%3A1'));
 fireEvent.click(screen.getByRole('button',{name:'Refresh data',exact:true}));
 await screen.findByText('metrics unavailable');
 expect(screen.getByTestId('overview')).toHaveAttribute('data-revision','1');
});

test('Home restores the selected scope from its URL on remount',async()=>{
 window.history.replaceState(null,'','#/home?ontology_id=qif-id');
 mocks.getMetrics.mockImplementation(async id=>({data:{resources:20,classes:7,scope:{sampled:false,type:'published_rdf_projection',ontology_id:id}}}));
 const first=render(<LandingPage/>);await screen.findByText('7');first.unmount();
 render(<LandingPage/>);await screen.findByText('7');
 expect(screen.getByRole('combobox',{name:'Ontology scope'})).toHaveValue('qif-id');
});
