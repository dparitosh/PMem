import React from 'react';
import ReactFlowDiagramCanvas from '../DiagramCanvas/ReactFlowDiagramCanvas';
import D3NetworkGraph from './D3NetworkGraph';

export default function GraphVisualizationWidget({ renderer = 'react-flow', ...props }) {
  return renderer === 'd3'
    ? <D3NetworkGraph {...props} />
    : <ReactFlowDiagramCanvas {...props} />;
}
