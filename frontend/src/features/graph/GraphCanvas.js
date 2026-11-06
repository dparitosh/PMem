import React, { forwardRef, useEffect, useState } from 'react';
import * as d3 from 'd3';
import useGraphSimulation from './hooks/useGraphSimulation';

// Loading and selection remain in the workspace; this component owns D3 teardown.
const GraphCanvas = forwardRef(function GraphCanvas({ model, runtime, actions }, svgRef) {
  const [viewport, setViewport] = useState({width:0,height:0});
  useEffect(() => {
    const element=svgRef.current;
    if (!element || typeof ResizeObserver==='undefined') return undefined;
    const observer=new ResizeObserver(([entry]) => {
      const width=Math.round(entry.contentRect.width), height=Math.round(entry.contentRect.height);
      if(width>0 && height>0) setViewport(old=>old.width===width && old.height===height ? old : {width,height});
    });
    observer.observe(element);
    return ()=>observer.disconnect();
  }, [svgRef]);
  useGraphSimulation({ model:{...model, viewport}, runtime, actions, svgRef });
  const { tickFrameRef, simulationRef, gRef, zoomBehaviorRef } = runtime;
  useEffect(() => {
    const element = svgRef.current;
    return () => {
      if (tickFrameRef.current) cancelAnimationFrame(tickFrameRef.current);
      tickFrameRef.current = null;
      simulationRef.current?.stop();
      simulationRef.current = null;
      gRef.current = null;
      zoomBehaviorRef.current = null;
      d3.select(element).on('.zoom', null).on('click.graph-background', null);
    };
  }, [svgRef, tickFrameRef, simulationRef, gRef, zoomBehaviorRef]);
  return <svg ref={svgRef} role="img" aria-label="Knowledge graph canvas" className="graph-canvas" style={{ width: '100%', maxWidth:'100%', flex: '0 0 auto', height:'clamp(280px, 56dvh, 640px)', minHeight:0, margin: 0, padding: 0, position: 'relative', zIndex: 0 }} />;
});
export default GraphCanvas;
