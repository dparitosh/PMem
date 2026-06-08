import React from 'react';
import { BarChart3, FileInput } from 'lucide-react';
import ActionWidget from '../widgets/ActionWidget';
import KpiStrip from '../widgets/KpiStrip';
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
      <KpiStrip
        items={[
          { label: 'Graph nodes', value: nodeCount },
          { label: 'Relationships', value: relationshipCount },
          { label: 'Active ontology', value: 'Current' },
          { label: 'Artifact policy', value: 'Retained' },
        ]}
      />

      <div className="depo-widget-grid">
        <ActionWidget title="Import Data" description="Load STEP, STPX, PLMXML, XMI, CSV, or ontology files." icon={FileInput} actionLabel="Open Import" onAction={() => onNavigate('import')} />
        <ActionWidget title="Review Reports" description="Open retained artifacts and generated reports." icon={BarChart3} actionLabel="Open Reports" onAction={() => onNavigate('reports')} />
      </div>

      <section className="depo-panel">
        <div className="depo-panel__header">
          <div>
            <div className="depo-panel__title">Current Graph Table</div>
            <div className="depo-panel__meta">Tabular inspection of visible graph entities and search results.</div>
          </div>
        </div>
        <div className="depo-panel__body" style={{ minHeight: 380 }}>
          <TableView
            data={data}
            searchResults={searchResults}
            chatResults={chatResults}
            visibleRelationships={visibleRelationships}
          />
        </div>
      </section>
    </div>
  );
}
