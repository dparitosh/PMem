// Explicit local QA mode only. No telemetry transport and no DOM/event payloads.
let started;
export function startPerformanceProbe() {
  if (new URLSearchParams(window.location.search).get('measure_ui') !== '1') return Promise.resolve(false);
  if (started) return started;
  started = (async () => {
    const output = document.createElement('script');
    output.id = 'depo-performance-probe';
    output.type = 'application/json';
    const snapshot = {scope:'single-document browser sample; not field certification',
      state:'loading', metrics:{CLS:null,INP:null,LCP:null}};
    const write = () => { output.textContent = JSON.stringify(snapshot); };
    write(); document.head.appendChild(output);
    try {
      const {onCLS,onINP,onLCP} = await import('web-vitals');
      const report = metric => {
        if (!Object.hasOwn(snapshot.metrics, metric.name) || !Number.isFinite(metric.value)) return;
        snapshot.metrics[metric.name] = {value:metric.value, rating:metric.rating,
          unit:metric.name==='CLS'?'score':'ms'};
        write();
      };
      snapshot.state='collecting';write();
      const options={reportAllChanges:true};
      onCLS(report,options);onINP(report,options);onLCP(report,options);
      return true;
    } catch {
      snapshot.state='unavailable';write();return false;
    }
  })();
  return started;
}
