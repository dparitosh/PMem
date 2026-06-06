import React from 'react';
import GraphHEB from '../Components/GraphHEB';
import GraphWidget from '../widgets/GraphWidget';
import PageHeader from '../widgets/PageHeader';

export default function GraphExplorerPage(props) {
  return (
    <div className="depo-page" style={{ height: '100%' }}>
      <PageHeader
        eyebrow="Graph explorer"
        title="Inspect ontology classes, instance nodes, and trace relationships in context"
        summary="The graph canvas is for investigation: find product structures, compare ontology and instance views, and move from visual evidence to table, quality, or reports."
        insights={[
          { label: 'View modes', value: 'Ontology hierarchy and instance graph' },
          { label: 'Primary task', value: 'Explore relationships and identify gaps' },
          { label: 'Boundary', value: 'Destructive operations stay in Admin Operations' },
        ]}
      />
      <GraphWidget title="Graph Canvas" subtitle="D3 remains the graph visualization engine for this phase." minHeight={560}>
        <GraphHEB {...props} />
      </GraphWidget>
    </div>
  );
}
