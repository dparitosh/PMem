import React from 'react';
import ReportsTab from '../Components/ReportsTab';
import WorkflowWidget from '../widgets/WorkflowWidget';
import { workflowCatalog } from './workflowCatalog';

export default function ReportsPage({ searchResults, chatResults, graphData }) {
  const reportWorkflows = workflowCatalog.filter((item) => item.category === 'Reports');
  return (
    <div className="depo-page">
      <div className="depo-workflow-grid">
        {reportWorkflows.map((workflow) => (
          <WorkflowWidget key={workflow.id} workflow={workflow} />
        ))}
      </div>
      <ReportsTab searchResults={searchResults} chatResults={chatResults} graphData={graphData} />
    </div>
  );
}
