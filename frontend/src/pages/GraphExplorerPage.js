import React from 'react';
import GraphHEB from '../Components/GraphHEB';
import GraphWidget from '../widgets/GraphWidget';

export default function GraphExplorerPage(props) {
  return (
    <div className="depo-page" style={{ height: '100%' }}>
      <GraphWidget subtitle="D3 graph visualization remains the graph canvas for this migration phase." minHeight={620}>
        <GraphHEB {...props} />
      </GraphWidget>
    </div>
  );
}
