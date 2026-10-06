import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import App from './App';
import { useState } from 'react';

vi.mock('./SchemaContext', () => ({
  SchemaProvider: ({ children }) => {
    const [identity] = useState(() => Math.random().toString());
    return <div data-testid="schema-instance" data-instance={identity}>{children}</div>;
  },
}));

vi.mock('./contexts/OntologyContext', () => ({
  OntologyProvider: ({ children }) => children,
}));

vi.mock('./app/AppShell', () => ({
  default: ({ activePage, children, onPageChange, onServiceAuthChange }) => (
    <div>
      <nav aria-label="Application navigation">
        {[
          'Home', 'Import', 'Ontology Junction', 'Metadata Registry', 'Graph Explorer',
          'Code Network', 'Modeling', 'ReqIF', 'QIF', 'Where Used', 'Recommendations',
          'Reports', 'Admin',
        ].map((label) => (
          <button
            key={label}
            type="button"
            aria-current={activePage === ({ Home: 'home', 'Ontology Junction': 'ontology', 'Metadata Registry': 'registry', 'Graph Explorer': 'graph', 'Code Network': 'code-audit', Modeling: 'modeling', ReqIF: 'requirements', QIF: 'qif', 'Where Used': 'whereused', Recommendations: 'quality', Reports: 'reports', Admin: 'admin', Import: 'import' }[label]) ? 'page' : undefined}
            onClick={() => onPageChange({ Home: 'home', 'Ontology Junction': 'ontology', 'Metadata Registry': 'registry', 'Graph Explorer': 'graph', 'Code Network': 'code-audit', Modeling: 'modeling', ReqIF: 'requirements', QIF: 'qif', 'Where Used': 'whereused', Recommendations: 'quality', Reports: 'reports', Admin: 'admin', Import: 'import' }[label])}
          >{label}</button>
        ))}
      </nav>
      <button onClick={onServiceAuthChange}>Simulate access change</button>
      {children}
    </div>
  ),
}));

vi.mock('./Components/LandingPage', () => ({ default: () => <div>Landing Mock</div> }));
vi.mock('./pages/ImportPage', () => ({ default: () => <div data-testid="page-import">Import page</div> }));
vi.mock('./pages/OntologyJunctionPage', () => ({ default: () => <div data-testid="page-ontology">Ontology Junction page</div> }));
vi.mock('./pages/MetadataRegistryPage', () => ({ default: () => <div data-testid="page-registry">Metadata Registry page</div> }));
vi.mock('./pages/GraphExplorerPage', () => ({ default: ({ setData, graphData }) => <div data-testid="page-graph">Graph Explorer page<button onClick={() => setData({ nodes: [{ id: 'old-session-node' }] })}>Load graph fixture</button><span data-testid="graph-data">{JSON.stringify(graphData)}</span></div> }));
vi.mock('./pages/CodeAuditPage', () => ({ default: () => <div data-testid="page-code-audit">Code Network page</div> }));
vi.mock('./pages/ModelWorkbenchPage', () => ({ default: () => <div data-testid="page-modeling">Modeling page</div> }));
vi.mock('./pages/RecommendationsPage', () => ({ default: () => <div data-testid="page-quality">Recommendations page</div> }));
vi.mock('./pages/ReportsPage', () => ({ default: () => <div data-testid="page-reports">Reports page</div> }));
vi.mock('./pages/AdminPage', () => ({ default: () => <div data-testid="page-admin">Admin page</div> }));
vi.mock('./pages/WhereUsedPage', () => ({ default: () => <div data-testid="page-whereused">Where Used page</div> }));
vi.mock('./pages/RequirementsPage', () => ({ default: () => <div data-testid="page-requirements">ReqIF page</div> }));
vi.mock('./services/apiClient', () => ({
  API_METHODS: {
    health: {
      ready: vi.fn(() => Promise.resolve({ data: { status: 'ok' } })),
      check: vi.fn(() => Promise.resolve({ data: { status: 'ok' } })),
    },
  },
  ontology: { listRegistered: vi.fn(() => Promise.resolve({ data: { ontologies: [] } })) },
}));

beforeEach(() => {
  window.localStorage.clear();
  window.history.replaceState({}, '', '/');
});

test('renders the landing-page boundary when home is persisted', () => {
  window.localStorage.setItem('depo.activePage', 'home');
  render(<App />);
  expect(screen.getByText('Landing Mock')).toBeInTheDocument();
});

test('renders the landing page for the root hash route', () => {
  window.history.replaceState({}, '', '/#/');
  render(<App />);
  expect(screen.getByText('Landing Mock')).toBeInTheDocument();
});

test('falls back to Graph Explorer for invalid persisted navigation', async () => {
  window.history.replaceState({}, '', '/#/graph');
  window.localStorage.setItem('depo.activePage', 'removed-page');
  render(<App />);
  expect(await screen.findByTestId('page-graph')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Graph Explorer' })).toHaveAttribute('aria-current', 'page');
});

test('routes every application navigation item to its page boundary', async () => {
  window.history.replaceState({}, '', '/#/graph');
  render(<App />);
  const routes = [
    ['Import', 'page-import'],
    ['Ontology Junction', 'page-ontology'],
    ['Metadata Registry', 'page-registry'],
    ['Code Network', 'page-code-audit'],
    ['Modeling', 'page-modeling'],
    ['ReqIF', 'page-requirements'],
    ['Where Used', 'page-whereused'],
    ['Recommendations', 'page-quality'],
    ['Reports', 'page-reports'],
    ['Admin', 'page-admin'],
    ['Graph Explorer', 'page-graph'],
  ];
  for (const [label, testId] of routes) {
    fireEvent.click(screen.getByRole('button', { name: label }));
    expect(await screen.findByTestId(testId)).toBeInTheDocument();
  }
});

test('navigation preserves same-session data, while an access change clears data and refreshes the schema provider', async () => {
  window.history.replaceState({}, '', '/#/graph');
  render(<App />);
  await screen.findByTestId('page-graph');
  fireEvent.click(screen.getByText('Load graph fixture'));
  expect(screen.getByTestId('graph-data')).toHaveTextContent('old-session-node');
  const schemaInstance = screen.getByTestId('schema-instance').dataset.instance;
  fireEvent.click(screen.getByRole('button', { name: 'Admin', exact: true }));
  await screen.findByTestId('page-admin');
  fireEvent.click(screen.getByRole('button', { name: 'Graph Explorer', exact: true }));
  await screen.findByTestId('page-graph');
  expect(screen.getByTestId('graph-data')).toHaveTextContent('old-session-node');
  expect(screen.getByTestId('schema-instance').dataset.instance).toBe(schemaInstance);
  fireEvent.click(screen.getByText('Simulate access change'));
  await screen.findByTestId('page-graph');
  expect(screen.getByTestId('graph-data')).not.toHaveTextContent('old-session-node');
  expect(screen.getByTestId('schema-instance').dataset.instance).not.toBe(schemaInstance);
});
