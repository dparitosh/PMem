import React from 'react';

export default function PageHeader({ eyebrow, title, summary, insights = [] }) {
  return (
    <section className="depo-page-header">
      <div>
        {eyebrow && <div className="depo-page-header__eyebrow">{eyebrow}</div>}
        <div className="depo-page-header__title">{title}</div>
        {summary && <div className="depo-page-header__summary">{summary}</div>}
      </div>
      <div className="depo-page-header__insights">
        {insights.map((item) => (
          <div className="depo-insight" key={item.label}>
            <div className="depo-insight__label">{item.label}</div>
            <div className="depo-insight__value">{item.value}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
