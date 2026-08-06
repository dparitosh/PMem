import React from 'react';
import GraphHEB from '../Components/GraphHEB';
import GraphWidget from '../widgets/GraphWidget';

export default function GraphExplorerPage(props) {
  return (
    <div className="depo-page" style={{ height: '100%', minHeight: 'calc(100dvh - 120px)' }}>
      <GraphWidget minHeight={680}>
        <GraphHEB {...props} />
      </GraphWidget>
    </div>
  );
}
