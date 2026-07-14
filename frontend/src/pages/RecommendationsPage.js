import React from 'react';
import RecommendationsTab from '../Components/RecommendationsTab';

export default function RecommendationsPage({ setActiveTab }) {
  return (
    <div className="depo-page">
      <section className="depo-panel">
        <div className="depo-panel__header">
          <div>
            <div className="depo-panel__title">Recommendations</div>
            <div className="depo-panel__meta">Impact, reuse, and manufacturing guidance from the graph.</div>
          </div>
        </div>
        <div className="depo-panel__body">
          <RecommendationsTab setActiveTab={setActiveTab} />
        </div>
      </section>
    </div>
  );
}
