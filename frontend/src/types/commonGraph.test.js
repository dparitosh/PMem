import { normalizeCommonGraph } from './commonGraph';
import { expect, test } from 'vitest';
test('malformed graph payloads cannot crash the diagram', () => {
  for (const graph of [null, undefined, {nodes:{}}, {nodes:[null, 3, 'bad'], links:[null]}, {nodes:[], links:{}}]) {
    expect(normalizeCommonGraph(graph)).toEqual({nodes:[],links:[]});
  }
});
test('valid relationships survive invalid entries while orphan edges are removed', () => {
  const result = normalizeCommonGraph({nodes:[null,{id:'a'},{id:'b'}],links:[null,{source:'a',target:'b'},{source:'a',target:'missing'}]});
  expect(result.nodes).toHaveLength(2);
  expect(result.links).toHaveLength(1);
});
