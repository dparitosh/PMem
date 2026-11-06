// Fit finite positions without allocating coordinate arrays or spreading large datasets.
export function fitGraphViewport(nodes, width, height) {
  if (!(width > 0 && height > 0)) return {x:0,y:0,scale:1};
  let minX=Infinity, maxX=-Infinity, minY=Infinity, maxY=-Infinity;
  for (const node of nodes) {
    if (!Number.isFinite(node.x) || !Number.isFinite(node.y)) continue;
    minX=Math.min(minX,node.x); maxX=Math.max(maxX,node.x);
    minY=Math.min(minY,node.y); maxY=Math.max(maxY,node.y);
  }
  if (minX===Infinity) return {x:0,y:0,scale:1};
  const padX=Math.min(80,width/4), padY=Math.min(40,height/4);
  const scale=Math.min(1,(width-2*padX)/Math.max(maxX-minX+240,1),
    (height-2*padY)/Math.max(maxY-minY+80,1));
  // Labels extend to the right of nodes; include that space in the fitted bounds.
  return {x:width/2-scale*((minX+maxX)/2+90),y:height/2-scale*(minY+maxY)/2,scale};
}
