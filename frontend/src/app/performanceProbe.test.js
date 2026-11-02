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
