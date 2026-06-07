import React from 'react';
import DataImportPipeline from '../Components/DataImportPipeline';
import DataGridWidget from '../widgets/DataGridWidget';
import PageHeader from '../widgets/PageHeader';

const importPolicyRows = [
  { flow: 'Ontology only', input: 'EXPRESS, XSD, OWL', output: 'Ontology artifact', neo4j_write: 'Optional' },
  { flow: 'Instance graph only', input: 'STEP, STP, STPX, PLMXML, XMI, CSV', output: 'Neo4j instance graph', neo4j_write: 'Yes' },
  { flow: 'Link instances to ontology', input: 'Imported graph plus ontology mapping', output: 'Semantic trace links', neo4j_write: 'Yes' },
  { flow: 'Retain artifacts', input: 'Any import run', output: 'Parse report, generated files, lineage record', neo4j_write: 'No' },
];

export default function ImportPage() {
  return (
    <div className="depo-page">
      <PageHeader
        eyebrow="Data onboarding"
        title="Import product evidence without forcing a single rigid pipeline"
        summary="This page is for controlled ingestion of engineering files. The user should choose whether they are creating ontology assets, instance graphs, semantic links, or retained artifacts."
        insights={[
          { label: 'File families', value: 'STEP/STP/STPX, PLMXML, XMI, CSV, OWL/XSD' },
          { label: 'Control point', value: 'Preview and pre-commit checks before graph writes' },
          { label: 'Evidence policy', value: 'Generated files and reports must remain attached to each workflow run' },
        ]}
      />
      <DataGridWidget
        title="Import Flow Options"
        subtitle="Use this as the logical contract for the data import task surface below."
        rows={importPolicyRows}
        height={210}
        columns={[
          { field: 'flow', flex: 1.1 },
          { field: 'input', flex: 1.8 },
          { field: 'output', flex: 1.5 },
          { field: 'neo4j_write', headerName: 'Neo4j Write', flex: 0.8 },
        ]}
      />
      <section className="depo-panel">
        <div className="depo-panel__header">
          <div>
            <div className="depo-panel__title">Import Workbench</div>
            <div className="depo-panel__meta">Upload, preview, map, commit, and retain artifacts from one controlled surface.</div>
          </div>
        </div>
        <div className="depo-panel__body">
          <DataImportPipeline />
        </div>
      </section>
    </div>
  );
}
