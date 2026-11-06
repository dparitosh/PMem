import React, { useMemo } from 'react';
import EChartPanel from './EChartPanel';

const axis = {
  axisLabel: { overflow: 'truncate', width: 110 },
  axisTick: { alignWithLabel: true },
};

const top = (rows, limit = 10) => (rows || []).filter((row) => Number.isFinite(Number(row.count)) && Number(row.count) > 0)
  .sort((a, b) => Number(b.count) - Number(a.count)).slice(0, limit);

export const telemetryCategories = (telemetry, kind) => Object.entries(telemetry || {})
  .filter(([key, value]) => (kind === 'runs' ? key.endsWith('_runs') && key !== 'total_runs' : key.startsWith('records_'))
    && typeof value === 'number' && Number.isFinite(value) && value >= 0)
  .map(([key, value]) => ({ name: key.replace(kind === 'runs' ? /_runs$/ : /^records_/, '').replace(/_/g, ' '), count: value }));

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
  const rows = telemetryCategories(telemetry, 'runs').map(row => [row.name, row.count]);
  if (!rows.some(([, value]) => value > 0)) return null;
  return {
    animationDuration: 300,
    grid: { left: 12, right: 18, top: 18, bottom: 8, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'category', data: rows.map(([name]) => name), axisLabel: { interval: 0 } },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{
      type: 'bar', name: 'Runs', data: rows.map(([, value]) => value), barMaxWidth: 34,
    }],
  };
};

const qualityOption = (telemetry) => {
  // Record counters may overlap (processed, accepted, published). A bar chart
  // shows each returned metric without inventing parts of a percentage total.
  return barOption(telemetryCategories(telemetry, 'quality'), '#007993');
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
          <p>Service-backed summaries. Entity and relationship charts describe the loaded graph sample; ontology coverage uses full published totals. Pipeline charts describe global runs.</p>
        </div>
        {telemetryError && <span role="status">Pipeline telemetry unavailable; graph analytics remain visible.</span>}
      </div>
      <div className="reports-chart-grid">
        <EChartPanel title="Entity distribution" description="Top entity types in the current report scope." option={entityOption} />
        <EChartPanel title="Relationship distribution" description="Top relationship types in the current graph scope." option={relationshipOption} />
        <EChartPanel title="Ontology coverage" description="Published RDF resource totals from the full graph aggregation; unavailable counts are excluded." option={ontologyOption} />
        <EChartPanel title="Data-job status" description="Global durable pipeline runs; categories come from returned status counters." option={executionOption} emptyMessage={telemetryError || 'No pipeline runs are available.'} />
        <EChartPanel title="Record quality metrics" description="Global record counters returned by durable pipeline telemetry; counters may overlap." option={dataQualityOption} emptyMessage={telemetryError || 'No quality counts are available.'} />
      </div>
    </section>
  );
}
