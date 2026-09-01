import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import App from './App';

vi.mock('./SchemaContext', () => ({
  SchemaProvider: ({ children }) => children,
}));

vi.mock('./contexts/OntologyContext', () => ({
  OntologyProvider: ({ children }) => children,
}));

vi.mock('./Components/LandingPage', () => ({ default: () => <div>Landing Mock</div> }));
vi.mock('./pages/ImportPage', () => ({ default: () => <div data-testid="page-import">Import page</div> }));
vi.mock('./pages/OntologyJunctionPage', () => ({ default: () => <div data-testid="page-ontology">Ontology Junction page</div> }));
vi.mock('./pages/MetadataRegistryPage', () => ({ default: () => <div data-testid="page-registry">Metadata Registry page</div> }));
vi.mock('./pages/GraphExplorerPage', () => ({ default: () => <div data-testid="page-graph">Graph Explorer page</div> }));
vi.mock('./pages/CodeAuditPage', () => ({ default: () => <div data-testid="page-code-audit">Code Network page</div> }));
vi.mock('./pages/ModelWorkbenchPage', () => ({ default: () => <div data-testid="page-modeling">Modeling page</div> }));
vi.mock('./pages/RecommendationsPage', () => ({ default: () => <div data-testid="page-quality">Recommendations page</div> }));
vi.mock('./pages/ReportsPage', () => ({ default: () => <div data-testid="page-reports">Reports page</div> }));
vi.mock('./pages/AdminPage', () => ({ default: () => <div data-testid="page-admin">Admin page</div> }));
vi.mock('./pages/WhereUsedPage', () => ({ default: () => <div data-testid="page-whereused">Where Used page</div> }));
vi.mock('./pages/RequirementsPage', () => ({ default: () => <div data-testid="page-requirements">ReqIF page</div> }));
vi.mock('./Components/Chatbot', () => ({ default: () => <div data-testid="chatbot">Chatbot</div> }));
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

test('renders DEPO platform landing page when home is persisted', () => {
  window.localStorage.setItem('depo.activePage', 'home');
  render(<App />);
  expect(screen.getByText(/DEPO Digital Thread Platform/i)).toBeInTheDocument();
});

test('renders the landing page for the root hash route', () => {
  window.history.replaceState({}, '', '/#/');
  render(<App />);
  expect(screen.getByText(/DEPO Digital Thread Platform/i)).toBeInTheDocument();
});

test('falls back to Graph Explorer for invalid persisted navigation', async () => {
  window.history.replaceState({}, '', '/#/graph');
  window.localStorage.setItem('depo.activePage', 'removed-page');
  render(<App />);
  expect(await screen.findByRole('heading', { name: 'Graph Explorer' })).toBeInTheDocument();
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
