import React, { createRef } from 'react';
import { render, screen } from '@testing-library/react';
import GraphCanvas from './GraphCanvas';
vi.mock('../../utils/logger', () => ({ logger: { render: vi.fn(), warn: vi.fn() } }));
function fixture() {
  const empty = { nodes: [], links: [] };
  const model = { filteredData: empty, graphSearchActive: false, activeDisplayData: empty,
    activeGraphDataset: empty, searchResultData: empty, graphViewMode: 'ontology', graphData: empty,
    activeSearchResultId: null, loadingNodes: new Set(), debouncedSearchQuery: '', selectedOntology: 'ALL' };
  const runtime = Object.fromEntries(['gRef','zoomBehaviorRef','simulationRef','simulationLayoutRef','activeTooltipNodeRef',
    'tooltipRef','highlightedNodeIdsRef','expandedNodesRef','nodeExpansionsRef','tickFrameRef','lastCenteredSearchRef',
    'userInteractedWithGraphRef'].map(name => [name, {current:null}]));
  return { model, runtime, actions: { hideAllTooltips: vi.fn(), handleZoom: vi.fn() } };
}
test('canvas removes D3 listeners and stops its simulation when the route unmounts', () => {
  const props = fixture(), ref = createRef();
  const view = render(<GraphCanvas ref={ref} {...props} />);
  const element = screen.getByRole('img', {name:'Knowledge graph canvas'});
  expect(element.__on.some(listener => listener.name === 'zoom')).toBe(true);
  const stop = vi.fn();
  props.runtime.simulationRef.current = { stop };
  view.unmount();
  expect(stop).toHaveBeenCalledTimes(1);
  expect(element.__on).toBeUndefined();
  expect(props.runtime.gRef.current).toBeNull();
  expect(props.runtime.zoomBehaviorRef.current).toBeNull();
});
test('rerendering an empty graph keeps zoom and background dismissal working', () => {
  const props = fixture(), ref = createRef();
  const view = render(<GraphCanvas ref={ref} {...props} />);
  view.rerender(<GraphCanvas ref={ref} {...props} model={{...props.model, filteredData:{nodes:[],links:[]}}} />);
  const element = screen.getByRole('img', {name:'Knowledge graph canvas'});
  element.dispatchEvent(new MouseEvent('click', { bubbles:true }));
  expect(props.actions.hideAllTooltips).toHaveBeenCalledTimes(1);
  expect(element.__on.some(listener => listener.name === 'zoom')).toBe(true);
});

test('simulation animates layout copies and preserves positions across metadata updates', () => {
  const props = fixture(), ref = createRef();
  const node = Object.freeze({elementId:'part',labels:['Class'],properties:Object.freeze({name:'Part'})});
  const graph = {nodes:[node],links:[]};
  Object.assign(props.model,{filteredData:graph,activeDisplayData:graph,activeGraphDataset:graph,graphData:graph});
  Object.assign(props.runtime.highlightedNodeIdsRef,{current:new Set()});
  Object.assign(props.runtime.expandedNodesRef,{current:new Set()});
  Object.assign(props.runtime.nodeExpansionsRef,{current:new Map()});
  Object.assign(props.actions,{
    initializeNodePositions:nodes=>nodes.forEach(n=>{n.x=80;n.y=90;}),
    processLinksForOffset:links=>links.map(link=>({...link})),boundaryForce:()=>()=>{},calculateCurvedPath:()=>'',
    getNodeColor:()=> '#123456',getPrimaryNodeLabel:n=>n.properties.name,getNodeLabelColor:()=> '#123456',
    canCollapseNode:()=>false,hasExpandableConnections:()=>false,dragstarted:()=>{},dragged:()=>{},dragended:()=>{},
  });
  const view=render(<GraphCanvas ref={ref} {...props}/>);
  const positioned=props.runtime.simulationRef.current.nodes()[0];
  expect(positioned).not.toBe(node);
  expect(node.x).toBeUndefined();
  expect(node.index).toBeUndefined();
  expect(screen.getByText('Part')).toBeInTheDocument();
  const revised={nodes:[{...node,properties:{name:'Revised part'}}],links:[]};
  view.rerender(<GraphCanvas ref={ref} {...props} model={{...props.model,filteredData:revised,activeDisplayData:revised,activeGraphDataset:revised}}/>);
  expect(props.runtime.simulationRef.current.nodes()[0]).toBe(positioned);
  expect(screen.getByText('Revised part')).toBeInTheDocument();
  expect(screen.getByText('Nodes: 1')).toBeInTheDocument();
  const empty={nodes:[],links:[]};
  view.rerender(<GraphCanvas ref={ref} {...props} model={{...props.model,filteredData:empty,activeDisplayData:empty,activeGraphDataset:empty,graphData:empty,selectedOntology:'unpublished'}}/>);
  expect(screen.queryByText('Nodes: 1')).toBeNull();
  expect(screen.queryByText('Revised part')).toBeNull();
});


test('observes container resizing and disconnects the observer on unmount', () => {
 const observe=vi.fn(),disconnect=vi.fn();
 const Original=globalThis.ResizeObserver;
 globalThis.ResizeObserver=class {observe=observe;disconnect=disconnect;};
 try {
  const props=fixture(),ref=createRef();
  const view=render(<GraphCanvas ref={ref} {...props}/>);
  expect(observe.mock.calls[0][0] === ref.current).toBe(true);
  expect(ref.current.classList.contains('graph-canvas')).toBe(true);
  view.unmount();expect(disconnect).toHaveBeenCalledTimes(1);
 } finally {globalThis.ResizeObserver=Original;}
});
