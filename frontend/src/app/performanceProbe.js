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
    if (new URLSearchParams(window.location.search).get('measure_heap') === '1') {
      snapshot.heap = {supported:false, samples:[], scope:'Chromium heap samples; GC fluctuations are not a leak diagnosis'};
      const sample = () => {
        const memory = performance.memory;
        if (!memory || ![memory.usedJSHeapSize,memory.totalJSHeapSize].every(value => Number.isFinite(value) && value >= 0)) return;
        snapshot.heap.supported=true;
        snapshot.heap.samples.push({at:Math.round(performance.now()),used:memory.usedJSHeapSize,total:memory.totalJSHeapSize});
        snapshot.heap.samples=snapshot.heap.samples.slice(-40);
        write();
      };
      sample();
      if (snapshot.heap.supported) {
        const timer=setInterval(sample,15000);
        window.addEventListener('pagehide',()=>clearInterval(timer),{once:true});
      }
    }
    try {
      const {onCLS,onINP,onLCP} = await import('web-vitals');
      const report = metric => {
        if (!Object.hasOwn(snapshot.metrics, metric.name) || !Number.isFinite(metric.value)) return;
        snapshot.metrics[metric.name] = {value:metric.value, rating:metric.rating,
          unit:metric.name==='CLS'?'score':'ms'};
        if (metric.name === 'CLS') {
          snapshot.layoutSources = (metric.entries || []).slice(-2).flatMap(entry =>
            (entry.sources || []).slice(0,3).map(source => ({
              tag:source.node?.tagName || '',
              className:typeof source.node?.className==='string'?source.node.className.slice(0,80):'',
              before:source.previousRect?[source.previousRect.x,source.previousRect.y,source.previousRect.width,source.previousRect.height]:[],
              after:source.currentRect?[source.currentRect.x,source.currentRect.y,source.currentRect.width,source.currentRect.height]:[],
            })));
        }
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
