import React, { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import { BarChart, PieChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { registerTheme, resolveEChartThemeName } from '@siemens/ix-echarts';

let themesRegistered = false;

echarts.use([BarChart, PieChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

function ensureThemes() {
  if (themesRegistered) return;
  registerTheme(echarts);
  themesRegistered = true;
}

export default function EChartPanel({ title, description, option, emptyMessage = 'No chart data is available.' }) {
  const hostRef = useRef(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !option || import.meta.env.MODE === 'test' || typeof ResizeObserver === 'undefined') return undefined;
    ensureThemes();
    let chart;

    const render = () => {
      if (chart) chart.dispose();
      chart = echarts.init(host, resolveEChartThemeName(), { renderer: 'canvas' });
      chart.setOption(option, { notMerge: true });
    };

    render();
    const resizeObserver = new ResizeObserver(() => chart?.resize());
    resizeObserver.observe(host);
    const themeObserver = new MutationObserver((records) => {
      if (records.some((record) => record.attributeName === 'data-ix-color-schema')) render();
    });
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-ix-color-schema'] });

    return () => {
      resizeObserver.disconnect();
      themeObserver.disconnect();
      chart?.dispose();
    };
  }, [option]);

  return (
    <section className="reports-chart-card" aria-label={title}>
      <header className="reports-chart-card__header">
        <h3>{title}</h3>
        <p>{description}</p>
      </header>
      {option ? (
        <div ref={hostRef} className="reports-chart-card__canvas" role="img" aria-label={`${title}. ${description}`} />
      ) : (
        <div className="reports-chart-card__empty" role="status">{emptyMessage}</div>
      )}
    </section>
  );
}
