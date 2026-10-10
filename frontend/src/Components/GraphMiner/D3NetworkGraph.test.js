import React from 'react';
import { render, screen } from '@testing-library/react';
import { test, expect } from 'vitest';
import D3NetworkGraph from './D3NetworkGraph';
const graph = {nodes:[{id:'a',label:'A'},{id:'b',label:'B'}],links:[{id:'edge',source:'a',target:'b'}]};
test('selection changes preserve SVG and positioned node objects', () => {
 const view = render(<D3NetworkGraph graph={graph} selectedId="a" />);
 const svg = view.container.querySelector('svg');
 const circle = view.container.querySelector('circle');
 const node = circle.__data__;
 node.x = 75; node.y = 80;
 view.rerender(<D3NetworkGraph graph={graph} selectedId="b" onSelect={() => {}} />);
 expect(view.container.querySelector('svg')).toBe(svg);
 expect(view.container.querySelector('circle').__data__).toBe(node);
 expect(node.x).toBe(75);
 expect(circle.getAttribute('r')).toBe('7');
 expect(view.container.querySelector('line').getAttribute('marker-end')).toMatch(/^url/);
});
test('bounded visualization states its full input size', () => {
 render(<D3NetworkGraph graph={graph} maxNodes={1} />);
 expect(screen.getByText(/Partial graph: showing 1 of 2 nodes/)).toBeVisible();
});
