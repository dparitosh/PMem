import React from 'react';

const stages = [
  { title: 'Product definition', source: 'QIF Product', detail: 'Part, feature, PMI, geometry, and characteristic definitions that establish what must be inspected.' },
  { title: 'Inspection planning', source: 'QIF Plan', detail: 'Rules, resources, measurement strategies, and measurement programs that specify how to inspect.' },
  { title: 'Measurement execution', source: 'Measurement Resources + Results', detail: 'Equipment capability, measured values, actual observations, and execution evidence.' },
  { title: 'Quality traceability', source: 'QIF Document + Traceability', detail: 'Links between definition, plan, measurement result, and quality decision across the digital thread.' },
];

export default function QifDigitalThreadOverview({ task }) {
  const summary = task?.summary;
  const graph = task?.graph_sync?.detail;

  return (
    <section className="qif-digital-thread" aria-labelledby="qif-digital-thread-title">
      <div className="qif-digital-thread__heading">
        <div>
          <div className="depo-panel__meta">QIF 3.0 digital thread</div>
          <h3 id="qif-digital-thread-title">From product definition to verified measurement evidence</h3>
          <p>QIF 3.0 connects the engineering definition, inspection plan, measurement execution, and quality result in one traceable information model.</p>
        </div>
        <a className="depo-button depo-button--secondary" href="#/graph">Explore connected graph</a>
      </div>
      <div className="qif-digital-thread__stages">
        {stages.map((stage, index) => (
          <article key={stage.title} className="qif-digital-thread__stage">
            <span className="qif-digital-thread__index">{index + 1}</span>
            <div><strong>{stage.title}</strong><span>{stage.source}</span><p>{stage.detail}</p></div>
          </article>
        ))}
      </div>
      <div className="qif-digital-thread__evidence" aria-label="Selected QIF ontology evidence">
        <span><strong>{summary?.files_processed ?? '—'}</strong> QIF schemas</span>
        <span><strong>{summary?.classes_created ?? '—'}</strong> ontology classes</span>
        <span><strong>{summary?.properties_created ?? '—'}</strong> semantic properties</span>
        <span><strong>{graph?.relationships_merged ?? '—'}</strong> graph relationships</span>
      </div>
    </section>
  );
}
