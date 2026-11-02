import {vi} from 'vitest';
const callbacks=vi.hoisted(()=>({}));
vi.mock('web-vitals',()=>({
 onCLS:vi.fn(fn=>{callbacks.CLS=fn;}),onINP:vi.fn(fn=>{callbacks.INP=fn;}),onLCP:vi.fn(fn=>{callbacks.LCP=fn;})
}));
beforeEach(()=>{vi.resetModules();document.getElementById('depo-performance-probe')?.remove();window.history.replaceState(null,'','/');});
test('ordinary users do not create a probe or load its metrics module',async()=>{
 const {startPerformanceProbe}=await import('./performanceProbe');
 expect(await startPerformanceProbe()).toBe(false);
 expect(document.getElementById('depo-performance-probe')).toBeNull();
});
test('opt-in mode registers once and retains only three bounded numeric metrics',async()=>{
 window.history.replaceState(null,'','/?measure_ui=1#/data-flow');
 const {startPerformanceProbe}=await import('./performanceProbe');
 const a=startPerformanceProbe();expect(startPerformanceProbe()).toBe(a);await a;
 callbacks.CLS({name:'CLS',value:.02,rating:'good',entries:[{password:'secret'}]});
 callbacks.INP({name:'INP',value:80,rating:'good'});
 callbacks.LCP({name:'LCP',value:900,rating:'good'});
 callbacks.CLS({name:'unknown',value:1});
 const text=document.getElementById('depo-performance-probe').textContent;
 const probe=JSON.parse(text);expect(Object.keys(probe.metrics)).toHaveLength(3);
 expect(probe.metrics.CLS).toEqual({value:.02,rating:'good',unit:'score'});
 expect(text).not.toContain('secret');expect(text.length).toBeLessThan(1000);
});

test('explicit heap sampling stays bounded and stops on page departure',async()=>{
 vi.useFakeTimers();
 Object.defineProperty(performance,'memory',{configurable:true,value:{usedJSHeapSize:100,totalJSHeapSize:200}});
 try {
  window.history.replaceState(null,'','/?measure_ui=1&measure_heap=1#/data-flow');
  const {startPerformanceProbe}=await import('./performanceProbe');await startPerformanceProbe();
  vi.advanceTimersByTime(15000*50);
  const probe=JSON.parse(document.getElementById('depo-performance-probe').textContent);
  expect(probe.heap.supported).toBe(true);expect(probe.heap.samples).toHaveLength(40);
  expect(probe.heap.samples[0].used).toBe(100);
  window.dispatchEvent(new Event('pagehide'));expect(vi.getTimerCount()).toBe(0);
 } finally {delete performance.memory;vi.useRealTimers();}
});
