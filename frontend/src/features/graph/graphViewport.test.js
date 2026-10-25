import {it,expect} from 'vitest';
import {fitGraphViewport} from './graphViewport';
it('keeps settled nodes within the viewport even after large coordinate drift',()=>{
 const nodes=[{x:-900,y:1200},{x:800,y:2500}];const view=fitGraphViewport(nodes,1000,500);
 nodes.forEach(n=>{expect(n.x*view.scale+view.x).toBeGreaterThan(0);expect(n.x*view.scale+view.x).toBeLessThan(1000);expect(n.y*view.scale+view.y).toBeGreaterThan(0);expect(n.y*view.scale+view.y).toBeLessThan(500);});
});
it('handles unpositioned data without invalid transforms',()=>{expect(fitGraphViewport([{x:NaN}],1000,500)).toEqual({x:0,y:0,scale:1});});

it('fits extreme extents and narrow containers without a minimum zoom clipping nodes',()=>{
 for(const [width,height] of [[320,280],[1000,500]]) {
  const nodes=[{x:-100000,y:-100000},{x:100000,y:100000}];
  const view=fitGraphViewport(nodes,width,height);
  nodes.forEach(n=>{expect(n.x*view.scale+view.x).toBeGreaterThan(0);expect(n.x*view.scale+view.x).toBeLessThan(width);expect(n.y*view.scale+view.y).toBeGreaterThan(0);expect(n.y*view.scale+view.y).toBeLessThan(height);});
 }
});
it('handles invalid container dimensions',()=>{expect(fitGraphViewport([{x:0,y:0}],0,0)).toEqual({x:0,y:0,scale:1});});
