import React from 'react';
import useRouteView from '../app/useRouteView';
const REPORT_VIEWS=['memory','engineering','reporting'];
import ReportingReplica from '../Components/ReportingReplica';
import ReportsTab from '../Components/ReportsTab';
import MemoryRecords from '../Components/MemoryRecords';

export default function ReportsPage({ searchResults, chatResults, graphData }) {
  const [view,setView]=useRouteView(REPORT_VIEWS,'memory',undefined,'#/reports');
  return (
    <div className="depo-page">
      <nav aria-label="Report types"><button onClick={()=>setView('memory')} aria-pressed={view==='memory'}>Memory records</button><button onClick={()=>setView('engineering')} aria-pressed={view==='engineering'}>Engineering reports</button><button onClick={()=>setView('reporting')} aria-pressed={view==='reporting'}>Reporting data</button></nav>
      {view==='reporting'?<ReportingReplica/>:view==='memory'?<MemoryRecords/>:<ReportsTab searchResults={searchResults} chatResults={chatResults} graphData={graphData} />}
    </div>
  );
}
