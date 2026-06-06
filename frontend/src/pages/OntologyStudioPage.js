import React from 'react';
import OntologyMapper from '../Components/OntologyMapper';
import WorkflowWidget from '../widgets/WorkflowWidget';
import { workflowCatalog } from './workflowCatalog';

export default function OntologyStudioPage() {
  const studioWorkflows = workflowCatalog.filter((item) => ['Ontology', 'Mapping', 'Governance'].includes(item.category));

  return (
    <div className="depo-page">
      <div className="depo-workflow-grid">
        {studioWorkflows.map((workflow) => (
          <WorkflowWidget key={workflow.id} workflow={workflow} />
        ))}
      </div>
      <section style={{ minHeight: 520 }}>
        <OntologyMapper />
      </section>
    </div>
  );
}
