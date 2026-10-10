import React, { useMemo } from 'react';
import EChartPanel from './EChartPanel';

const axis = {
  axisLabel: { overflow: 'truncate', width: 110 },
  axisTick: { alignWithLabel: true },
};

const top = (rows, limit = 10) => (rows || []).filter((row) => Number(row.count) > 0).slice(0, limit);

const barOption = (rows, color) => {
  const values = top(rows);
  if (!values.length) return null;
  return {
    animationDuration: 300,
    grid: { left: 12, right: 18, top: 18, bottom: 8, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', minInterval: 1 },
    yAxis: { type: 'category', data: values.map((row) => row.name), ...axis },
    series: [{ type: 'bar', name: 'Count', data: values.map((row) => row.count), itemStyle: { color }, barMaxWidth: 22 }],
  };
};

const donutOption = (rows) => {
  const values = top(rows, 8);
  if (!values.length) return null;
  return {
    animationDuration: 300,
    tooltip: { trigger: 'item' },
    legend: { type: 'scroll', bottom: 0, left: 'center' },
    series: [{
      type: 'pie', name: 'Relationships', radius: ['42%', '68%'], center: ['50%', '43%'],
      avoidLabelOverlap: true,
      label: { formatter: '{b}: {c}' },
      data: values.map((row) => ({ name: row.name, value: row.count })),
    }],
  };
};

const statusOption = (telemetry) => {
  const rows = [
    ['Completed', Number(telemetry?.completed_runs || 0)],
    ['Running', Number(telemetry?.running_runs || 0)],
    ['Queued', Number(telemetry?.queued_runs || 0)],
    ['Failed', Number(telemetry?.failed_runs || 0)],
  ];
  if (!rows.some(([, value]) => value > 0)) return null;
  return {
    animationDuration: 300,
    grid: { left: 12, right: 18, top: 18, bottom: 8, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'category', data: rows.map(([name]) => name), axisLabel: { interval: 0 } },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{
      type: 'bar', name: 'Runs', data: rows.map(([, value], index) => ({
        value,
        itemStyle: { color: ['#00a78e', '#00bedc', '#f0b323', '#e63237'][index] },
      })), barMaxWidth: 34,
    }],
  };
};

const qualityOption = (telemetry) => {
  const accepted = Number(telemetry?.records_accepted || 0);
  const rejected = Number(telemetry?.records_rejected || 0);
  if (accepted + rejected === 0) return null;
  return {
    animationDuration: 300,
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    series: [{
      type: 'pie', name: 'Quality outcome', radius: ['48%', '72%'], center: ['50%', '50%'],
      label: { formatter: '{b}\n{c}' },
      data: [
        { name: 'Accepted', value: accepted, itemStyle: { color: '#00a78e' } },
        { name: 'Rejected', value: rejected, itemStyle: { color: '#e63237' } },
      ],
    }],
  };
};

export default function ReportsAnalytics({ entityTypes, relationships, ontologies, telemetry, telemetryError }) {
  const entityOption = useMemo(() => barOption(
    (entityTypes || []).map((row) => ({ name: row.type, count: row.count })), '#007993'
  ), [entityTypes]);
  const relationshipOption = useMemo(() => donutOption(
    (relationships || []).map((row) => ({ name: row.type, count: row.count }))
  ), [relationships]);
  const ontologyOption = useMemo(() => barOption(
    (ontologies || []).filter(row => row.nodes != null && row.nodes !== '' && Number.isFinite(Number(row.nodes)))
      .map((row) => ({ name: row.ontology || row.prefix || 'Unidentified', count: Number(row.nodes) }))
      .sort((a, b) => b.count - a.count), '#005a9c'
  ), [ontologies]);
  const executionOption = useMemo(() => statusOption(telemetry), [telemetry]);
  const dataQualityOption = useMemo(() => qualityOption(telemetry), [telemetry]);

  return (
    <section className="reports-analytics" aria-labelledby="reports-analytics-title">
      <div className="reports-analytics__heading">
        <div>
          <h2 id="reports-analytics-title">Analytics overview</h2>
          <p>Live graph, ontology, data-job, and data-quality summaries. Detailed tables remain available below.</p>
        </div>
        {telemetryError && <span role="status">Pipeline telemetry unavailable; graph analytics remain visible.</span>}
      </div>
      <div className="reports-chart-grid">
        <EChartPanel title="Entity distribution" description="Top entity types in the current report scope." option={entityOption} />
        <EChartPanel title="Relationship distribution" description="Top relationship types in the current graph scope." option={relationshipOption} />
        <EChartPanel title="Ontology coverage" description="Published RDF resource totals from the full graph aggregation; unavailable counts are excluded." option={ontologyOption} />
        <EChartPanel title="Data-job status" description="Durable pipeline runs by current status." option={executionOption} emptyMessage={telemetryError || 'No pipeline runs are available.'} />
        <EChartPanel title="Data-quality outcome" description="Accepted and rejected records from recent durable runs." option={dataQualityOption} emptyMessage={telemetryError || 'No quality counts are available.'} />
      </div>
    </section>
  );
}
