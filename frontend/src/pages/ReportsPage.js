import React from 'react';
import ReportsTab from '../Components/ReportsTab';

export default function ReportsPage({ searchResults, chatResults, graphData }) {
  return (
    <div className="depo-page">
      <ReportsTab searchResults={searchResults} chatResults={chatResults} graphData={graphData} />
    </div>
  );
}
