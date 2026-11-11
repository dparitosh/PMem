import React from 'react';
import ReportsTab from '../Components/ReportsTab';
import MemoryRecords from '../Components/MemoryRecords';

export default function ReportsPage({ searchResults, chatResults, graphData }) {
  const [view,setView]=React.useState('memory');
  return (
    <div className="depo-page">
      <nav aria-label="Report types"><button onClick={()=>setView('memory')} aria-pressed={view==='memory'}>Memory records</button><button onClick={()=>setView('engineering')} aria-pressed={view==='engineering'}>Engineering reports</button></nav>
      {view==='memory'?<MemoryRecords/>:<ReportsTab searchResults={searchResults} chatResults={chatResults} graphData={graphData} />}
    </div>
  );
}
