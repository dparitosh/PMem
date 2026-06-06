import React from 'react';
import { BarChart3, Database, FileInput, Network } from 'lucide-react';
import StatWidget from '../widgets/StatWidget';
import ActionWidget from '../widgets/ActionWidget';
import TableView from '../Components/TableView';

export default function WorkspacePage({
  data,
  searchResults,
  chatResults,
  visibleRelationships,
  onNavigate,
}) {
  const nodeCount = data?.nodes?.length || 0;
  const relationshipCount = data?.links?.length || 0;

  return (
    <div className="depo-page">
      <div className="depo-widget-grid">
        <StatWidget label="Graph Nodes" value={nodeCount} icon={Database} status={nodeCount ? 'ok' : 'neutral'} />
        <StatWidget label="Relationships" value={relationshipCount} icon={Network} status={relationshipCount ? 'ok' : 'neutral'} />
        <ActionWidget title="Import Data" description="Load STEP, STPX, PLMXML, XMI, CSV, or ontology files." icon={FileInput} actionLabel="Open Import" onAction={() => onNavigate('import')} />
        <ActionWidget title="Review Reports" description="Open retained artifacts and generated reports." icon={BarChart3} actionLabel="Open Reports" onAction={() => onNavigate('reports')} />
      </div>
      <section style={{ minHeight: 420 }}>
        <TableView
          data={data}
          searchResults={searchResults}
          chatResults={chatResults}
          visibleRelationships={visibleRelationships}
        />
      </section>
    </div>
  );
}
