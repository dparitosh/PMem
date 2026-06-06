import React from 'react';
import DataImportPipeline from '../Components/DataImportPipeline';
import WorkflowWidget from '../widgets/WorkflowWidget';
import { workflowCatalog } from './workflowCatalog';

export default function ImportPage() {
  const importWorkflows = workflowCatalog.filter((item) => ['Import', 'Mapping', 'Ontology'].includes(item.category));

  return (
    <div className="depo-page">
      <div className="depo-workflow-grid">
        {importWorkflows.map((workflow) => (
          <WorkflowWidget key={workflow.id} workflow={workflow} />
        ))}
      </div>
      <section style={{ minHeight: 520 }}>
        <DataImportPipeline />
      </section>
    </div>
  );
}
