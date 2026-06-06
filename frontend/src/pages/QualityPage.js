import React from 'react';
import RecommendationsTab from '../Components/RecommendationsTab';
import DataGridWidget from '../widgets/DataGridWidget';
import WorkflowWidget from '../widgets/WorkflowWidget';
import { workflowCatalog } from './workflowCatalog';

const issueRows = [
  { area: 'Ontology validation', status: 'Ready', owner: 'Quality', next_action: 'Run validator from workflow studio' },
  { area: 'Data dictionary', status: 'Ready', owner: 'Governance', next_action: 'Generate from selected namespace' },
  { area: 'Taxonomy', status: 'Ready', owner: 'Ontology', next_action: 'Review class hierarchy and prefixes' },
];

export default function QualityPage({ setActiveTab }) {
  const qualityWorkflows = workflowCatalog.filter((item) => ['Quality', 'Governance'].includes(item.category));
  return (
    <div className="depo-page">
      <div className="depo-workflow-grid">
        {qualityWorkflows.map((workflow) => (
          <WorkflowWidget key={workflow.id} workflow={workflow} />
        ))}
      </div>
      <DataGridWidget
        title="Quality Work Queue"
        rows={issueRows}
        height={220}
        columns={[
          { field: 'area', flex: 1.3 },
          { field: 'status' },
          { field: 'owner' },
          { field: 'next_action', flex: 2 },
        ]}
      />
      <RecommendationsTab setActiveTab={setActiveTab} />
    </div>
  );
}
