import React from 'react';
import ReportsTab from '../Components/ReportsTab';

export default function ReportsPage({ searchResults, chatResults, graphData }) {
  return (
    <div className="depo-page">
      <section className="depo-panel">
        <div className="depo-panel__header">
          <div>
            <div className="depo-panel__title">Outputs</div>
            <div className="depo-panel__meta">Publish and inspect outputs generated from the current workspace context.</div>
          </div>
        </div>
        <div className="depo-panel__body">
          <ReportsTab searchResults={searchResults} chatResults={chatResults} graphData={graphData} />
        </div>
      </section>
    </div>
  );
}
