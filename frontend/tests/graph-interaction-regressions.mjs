import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const require = createRequire(import.meta.url);
const babelParse = process.env.DEPO_TEST_BABEL_BUNDLE
  ? require(process.env.DEPO_TEST_BABEL_BUNDLE).babelParse
  : (source => require('@babel/parser').parse(source, { sourceType: 'module', plugins: ['jsx'] }));
const component = readFileSync(new URL('../src/Components/GraphHEB.js', import.meta.url), 'utf8');
const tree = babelParse(component, 'GraphHEB.js');
const callbacks = new Map();
function visit(node) {
  if (!node || typeof node !== 'object') return;
  if (node.type === 'VariableDeclarator' && node.id?.name && node.init) callbacks.set(node.id.name, node.init);
  for (const value of Object.values(node)) {
    if (Array.isArray(value)) value.forEach(visit); else if (value && typeof value === 'object') visit(value);
  }
}
visit(tree);
const utilities = readFileSync(new URL('../src/utils/graphUtils.js', import.meta.url), 'utf8')
  .replace(/export \{[^}]*\};?/g, '').replace(/export /g, '');
const interactions = readFileSync(new URL('../src/utils/graphInteractionState.js', import.meta.url), 'utf8')
  .replace(/^import .*\n/, '').replace(/export /g, '');
const node = id => ({ elementId: id, labels: ['Individual'], properties: { name: id } });
const link = (a, b) => ({ elementId: `${a}-${b}`, source: a, target: b, type: 'LINK' });
const base = { nodes: [node('a'), node('b')], links: [] };
const scope = { console, AbortController, Map, Set, JSON, Number,
  useCallback: fn => fn, isDevelopment: false, performanceWarn: () => {},
  logger: { error() {} }, API: { ui: { graphMaxNodes: 750 } }, DEFAULT_GRAPH_OVERVIEW_LIMIT: 750,
  isComponentMountedRef: { current: true },
  filteredDataRef: { current: base }, searchResultDataRef: { current: base },
  graphViewModeRef: { current: 'ontology' }, graphSearchActiveRef: { current: true },
  selectedOntologyRef: { current: 'demo' }, debouncedSearchQueryRef: { current: 'search' },
  expandedNodesRef: { current: new Set() }, nodeExpansionsRef: { current: new Map() },
  expansionBaseRef: { current: null }, expansionRequestsRef: { current: new Map() },
  expansionEpochRef: { current: 0 }, loadingNodesRef: { current: new Set() },
  rootLoadRef: { current: null }, activeSearchResultIdRef: { current: null },
  contextualRootNodeIdRef: { current: null },
  lastCenteredSearchRef: { current: '' },
  setFilteredData() {}, setSearchResultData() {}, setGraphData() {}, setFullDataset() {},
  setData() {}, setActiveSearchResultId() {}, syncSharedSearchResults() {},
  setNodeExpansions() {}, setExpandedNodes() {}, setLoadingNodes() {}, setError() {},
  setSearchLoading() {}, setContextualRootNodeId() {}, setContextualSearchResults() {},
  syncContextualHighlights() {}, setSearchQuery() {}, setSearchInput() {}, setHighlightedNodeIds() {},
  sanitizeContextualGraph: data => data,
};
vm.createContext(scope);
vm.runInContext(utilities + '\n' + interactions, scope);
const utility = name => vm.runInContext(name, scope);
const rebuild = utility('rebuildExpandedGraph');
const first = { nodes: [node('a'), node('shared')], links: [link('a', 'shared')] };
const second = { nodes: [node('b'), node('shared')], links: [link('b', 'shared')] };
const child = { nodes: [node('shared'), node('leaf')], links: [link('shared', 'leaf')] };
let result = rebuild(base, new Map([['a', first], ['b', second], ['shared', child]]), 'a');
assert(result.graph.nodes.some(item => item.elementId === 'leaf'), 'shared child must survive through branch b');
assert(!result.expansions.has('a'));
result = rebuild(base, new Map([['a', first], ['shared', child]]), 'a');
assert.equal(result.graph.nodes.length, 2, 'exclusive descendants must collapse');
assert.equal(result.expansions.size, 0);
const bounded = utility('boundExpansionSlice')(base, {
  nodes: [node('a'), node('b'), node('c'), node('d')], links: [link('a', 'c'), link('c', 'd')],
}, 3);
assert.equal(bounded.nodes.length, 3);
assert.equal(bounded.links.length, 1);
assert.equal(bounded.truncated, true);
const reconcile = utility('reconcileSimulationNodes');
const old = { ...node('a'), x: 0, y: 0, vx: 1, fy: 0 };
const reused = reconcile([{ ...node('a'), properties: { name: 'updated' } }], [old]);
assert.equal(reused[0], old);
assert.equal(reused[0].x, 0);
assert.equal(reused[0].fy, 0);
assert.equal(reused[0].properties.name, 'updated');
const seed = utility('seedSimulationNodes');
const ordered = seed([node('a'), node('b')], 800, 600);
const reversed = seed([node('b'), node('a')], 800, 600);
assert.equal(ordered[0].x, reversed[1].x);
assert.equal(ordered[0].y, reversed[1].y);
seed([old], 800, 600);
assert.equal(old.x, 0);
assert.equal(old.y, 0);
const topology = utility('graphTopologyKey');
assert.notEqual(topology(base.nodes, [link('a', 'b')]), topology(base.nodes, [{ ...link('a', 'b'), target: 'a' }]));
const trace = utility('oneHopCodeTrace');
const files = ['root', 'neighbor', 'far'].map(id => ({ id }));
const edges = [{ source: 'root', target: 'neighbor' }, { source: 'neighbor', target: 'far' }];
assert.equal(trace(files, edges, 'root').nodes.length, 2);
assert.equal(trace(files, [...edges].reverse(), 'root').nodes.length, 2);

for (const name of ['getCurrentGraphSlice', 'commitGraphSlice', 'clearExpansionState', 'loadContextualRootGraph', 'expandNode', 'collapseNode']) {
  const declaration = callbacks.get(name);
  assert(declaration, `missing component callback ${name}`);
  vm.runInContext(`globalThis.${name} = ${component.slice(declaration.start, declaration.end)}`, scope);
}
const pending = new Map();
scope.graphApi = { getTraversal(id, _depth, signal) {
  return new Promise(resolve => pending.set(id, { resolve, signal }));
} };
const expandA = scope.expandNode('a');
const expandB = scope.expandNode('b');
pending.get('b').resolve({ data: { nodes: second.nodes, relationships: second.links.map(item => ({ ...item, start: item.source, end: item.target })) } });
await expandB;
pending.get('a').resolve({ data: { nodes: first.nodes, relationships: first.links.map(item => ({ ...item, start: item.source, end: item.target })) } });
await expandA;
assert.equal(scope.nodeExpansionsRef.current.size, 2, 'concurrent completions must retain both branches');
assert.equal(scope.filteredDataRef.current.links.length, 2);
scope.collapseNode('a');
assert(scope.filteredDataRef.current.nodes.some(item => item.elementId === 'shared'));
assert.equal(scope.filteredDataRef.current.links.length, 1);

const late = scope.expandNode('a');
scope.clearExpansionState();
assert(pending.get('a').signal.aborted);
pending.get('a').resolve({ data: { nodes: [node('a'), node('stale')], relationships: [] } });
await late;
assert(!scope.filteredDataRef.current.nodes.some(item => item.elementId === 'stale'));
assert.equal(scope.nodeExpansionsRef.current.size, 0);
assert.equal(scope.loadingNodesRef.current.size, 0);
const rootA = scope.loadContextualRootGraph('a');
const rootB = scope.loadContextualRootGraph('b');
assert(pending.get('a').signal.aborted);
pending.get('b').resolve({ data: { nodes: [node('b')], relationships: [] } });
await rootB;
pending.get('a').resolve({ data: { nodes: [node('a')], relationships: [] } });
await rootA;
assert.equal(scope.filteredDataRef.current.nodes[0].elementId, 'b', 'late root selection must not replace current root');
console.log('PASS: shared/exclusive branch collapse, concurrent expansion, stale cancellation/root selection, stable simulation objects/seeds, zero coordinates and order-independent code trace');
