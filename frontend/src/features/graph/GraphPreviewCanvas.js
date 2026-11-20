import * as d3 from 'd3';
import React,{useMemo,useRef,forwardRef,useImperativeHandle} from 'react';

import GraphCanvas from './GraphCanvas';
import {getNodeColor,processLinksForOffset,calculateCurvedPath,boundaryForce} from './graphCanvasPolicy';
import {resolveNodeName,TCS_GRAPH_THEME} from './graphRenderingPolicy';
import {seedSimulationNodes} from '../../utils/graphInteractionState';

// Compact host for the same renderer used by Graph Explorer. No extra toolbar or tooltip.
const GraphPreviewCanvas=forwardRef(function GraphPreviewCanvas({data,onInspectNode},ref) {
 const svgRef=useRef(null),gRef=useRef(null),zoomBehaviorRef=useRef(null),simulationRef=useRef(null),simulationLayoutRef=useRef(null),activeTooltipNodeRef=useRef(null),tooltipRef=useRef(null),highlightedNodeIdsRef=useRef(new Set()),expandedNodesRef=useRef(new Set()),nodeExpansionsRef=useRef(new Map()),tickFrameRef=useRef(null),lastCenteredSearchRef=useRef(''),userInteractedWithGraphRef=useRef(false);
 useImperativeHandle(ref,()=>({zoomBy:factor=>{if(!svgRef.current||!zoomBehaviorRef.current)return;userInteractedWithGraphRef.current=true;d3.select(svgRef.current).call(zoomBehaviorRef.current.scaleBy,factor);}}),[]);
 const inspectRef=useRef(onInspectNode);inspectRef.current=onInspectNode;
 const actions=useMemo(()=>({
  onInspectNode:id=>inspectRef.current?.(id),hideAllTooltips:()=>{activeTooltipNodeRef.current=null;inspectRef.current?.(null);},
  handleZoom:event=>{if(event.sourceEvent)userInteractedWithGraphRef.current=true;gRef.current?.attr('transform',event.transform);gRef.current?.selectAll('.node-label').style('font-size',`${Math.max(12,11/event.transform.k)}px`);gRef.current?.selectAll('.link-label').style('font-size',`${Math.max(10,10/event.transform.k)}px`);},
  initializeNodePositions:seedSimulationNodes,processLinksForOffset:links=>processLinksForOffset(links.map(link=>({...link}))),boundaryForce,calculateCurvedPath,
  getNodeColor,getPrimaryNodeLabel:resolveNodeName,getNodeLabelColor:()=>TCS_GRAPH_THEME.ink,getRelationshipLabelColor:()=>TCS_GRAPH_THEME.inkSoft,
  canCollapseNode:()=>false,hasExpandableConnections:()=>false,
  dragstarted:(event,node)=>{userInteractedWithGraphRef.current=true;if(!event.active)simulationRef.current?.alphaTarget(.3).restart();node.fx=node.x;node.fy=node.y;},
  dragged:(event,node)=>{node.fx=event.x;node.fy=event.y;},
  dragended:(event,node)=>{if(!event.active)simulationRef.current?.alphaTarget(0);node.fx=null;node.fy=null;},
  getCurrentGraphSlice:()=>({nodes:[],links:[]}),buildRecActionBar:()=>'',tooltipCloseBtn:'',
 }),[]);
 const runtime={gRef,zoomBehaviorRef,simulationRef,simulationLayoutRef,activeTooltipNodeRef,tooltipRef,highlightedNodeIdsRef,expandedNodesRef,nodeExpansionsRef,tickFrameRef,lastCenteredSearchRef,userInteractedWithGraphRef};
 const model=useMemo(()=>({filteredData:data,activeDisplayData:data,graphData:data,activeGraphDataset:data,searchResultData:data,compact:true,graphSearchActive:true,graphViewMode:'ontology',activeSearchResultId:null,loadingNodes:new Set(),debouncedSearchQuery:data.nodes.map(node=>node.elementId).join('|'),selectedOntology:''}),[data]);
 return <GraphCanvas ref={svgRef} model={model} runtime={runtime} actions={actions}/>;
});
export default GraphPreviewCanvas;
