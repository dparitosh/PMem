import React from 'react';
import { BarChart3, FileInput } from 'lucide-react';
import ActionWidget from '../widgets/ActionWidget';
import DataGridWidget from '../widgets/DataGridWidget';
import KpiStrip from '../widgets/KpiStrip';
import PageHeader from '../widgets/PageHeader';
import TableView from '../Components/TableView';

const threadRows = [
  { stage: 'Define ontology', product_value: 'Create reusable semantics from standards and enterprise vocabulary', system_of_record: 'Ontology registry', current_state: 'Ready' },
  { stage: 'Import instances', product_value: 'Load CAD/MBSE/BOM files as traceable product structures', system_of_record: 'Neo4j graph', current_state: 'Ready' },
  { stage: 'Link and validate', product_value: 'Connect instance data to ontology classes and detect quality gaps', system_of_record: 'Mapping and quality reports', current_state: 'Ready' },
  { stage: 'Publish artifacts', product_value: 'Export dictionaries, reports, and ontology artifacts for reuse', system_of_record: 'Retained artifact store', current_state: 'Ready' },
];

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
      <PageHeader
        eyebrow="Digital thread command view"
        title="Trace engineering data from ontology intent to instance evidence"
        summary="Use this page to understand whether the current workspace has ontology structure, imported product instances, validation coverage, and exportable artifacts."
        insights={[
          { label: 'Decision focus', value: 'What product knowledge exists and what is missing?' },
          { label: 'Primary record', value: 'Neo4j graph plus retained import artifacts' },
          { label: 'Next best action', value: nodeCount ? 'Review graph quality and mappings' : 'Start with import or ontology creation' },
        ]}
      />

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

      <DataGridWidget
        title="Digital Thread Operating Model"
        subtitle="Logical flow from standards-driven ontology creation to instance graph evidence."
        rows={threadRows}
        height={210}
        columns={[
          { field: 'stage', flex: 1 },
          { field: 'product_value', flex: 2 },
          { field: 'system_of_record', flex: 1.3 },
          { field: 'current_state', flex: 0.8 },
        ]}
      />

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
