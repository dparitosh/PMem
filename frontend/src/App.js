import { configurationWarnings } from './config';
import 'bootstrap/dist/css/bootstrap.min.css';
import './App.css';
import './CSS/TCSColors.css';
import ErrorBoundary from './Components/ErrorBoundary';
import BrowserAccessBoundary from './Components/BrowserAccessBoundary';
import LandingPage from './Components/LandingPage';
import { SchemaProvider } from './SchemaContext';
import { OntologyProvider } from './contexts/OntologyContext';
import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from 'react';
import AppShell from './app/AppShell';
import AppPageOutlet from './app/AppPageOutlet';
import { normalizePage } from './app/navigation';
import { platformAPI } from './services/apiClient';

const PageTaskWorkspace = lazy(() => import('./Components/PageTaskWorkspace'));
const Chatbot = lazy(() => import('./Components/Chatbot'));


const NAV_STORAGE_KEY = 'depo.activePage';

function getInitialActivePage() {
  if (typeof window === 'undefined') return 'graph';
  try {
    const locationPage = getLocationPage();
    if (locationPage) return locationPage;
    const stored = window.localStorage.getItem(NAV_STORAGE_KEY);
    return normalizePage(stored || 'graph');
  } catch (_error) {
    return 'graph';
  }
}

function getLocationPage() {
  if (typeof window === 'undefined') return null;
  const hash = String(window.location.hash || '');
  if (hash === '#/' || hash === '#') return 'home';
  if (hash.startsWith('#/')) {
    const hashPage = hash.slice(2).split(/[/?]/)[0];
    return hashPage ? normalizePage(hashPage) : 'home';
  }
  if (hash && !hash.startsWith('#/')) return null;
  const pathname = String(window.location.pathname || '/');
  if (pathname === '/') return 'home';
  const pathPage = pathname.split('/').filter(Boolean)[0];
  return pathPage ? normalizePage(pathPage) : 'home';
}

function pushPageLocation(value) {
  if (typeof window === 'undefined' || !window.history?.pushState) return;
  const target = value === 'home' ? '#/home' : `#/${value}`;
  if (window.location.hash !== target) {
    window.history.pushState({}, '', target);
  }
}

function persistActivePage(value) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(NAV_STORAGE_KEY, value);
  } catch (_error) {
    // Storage can be unavailable in private/restricted browser contexts.
  }
}

function PageFallback() {
  return (
    <div style={{
      height: '100%',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      color: '#52606d',
      fontSize: 13,
      fontWeight: 600,
    }}>
      Loading page...
    </div>
  );
}

function App() {
  const [initialActivePage] = useState(() => getInitialActivePage());
  const [page, setPage] = useState(initialActivePage === 'home' ? 'home' : 'app');
  const [activePage, setActivePage] = useState(initialActivePage === 'home' ? 'graph' : initialActivePage);
  const [data, setData] = useState();
  const [companionSelection, setCompanionSelection] = useState(null);
  const [ontologyCompanionSelection, setOntologyCompanionSelection] = useState(null);
  const [recordCompanionSelection, setRecordCompanionSelection] = useState(null);
  const [searchResults, setSearchResults] = useState(null);
  const [chatResults, setChatResults] = useState(null);
  const [showChat, setShowChat] = useState(false);
  const [visibleRelationships, setVisibleRelationships] = useState(null);
  const [serviceStatus, setServiceStatus] = useState('checking');

  useEffect(() => {
    persistActivePage(page === 'home' ? 'home' : activePage);
  }, [page, activePage]);

  useEffect(() => {
    const syncFromLocation = () => {
      const nextPage = getLocationPage();
      if (!nextPage) return;
      if (nextPage === 'home') {
        setPage('home');
      } else {
        setPage('app');
        setActivePage(nextPage);
      }
    };
    window.addEventListener('popstate', syncFromLocation);
    window.addEventListener('hashchange', syncFromLocation);
    return () => {
      window.removeEventListener('popstate', syncFromLocation);
      window.removeEventListener('hashchange', syncFromLocation);
    };
  }, []);

  useEffect(() => {
    let active = true;
    let inFlight = false;
    let currentController = null;
    let retryDelayMs = 30000;
    let retryTimer = null;
    const checkHealth = async () => {
      if (!active || inFlight) return;
      inFlight = true;
      if (retryTimer) {
        window.clearTimeout(retryTimer);
        retryTimer = null;
      }
      const controller = new AbortController();
      currentController = controller;
      try {
        const health = await platformAPI.coreHealth({ signal: controller.signal, timeout: 15000 });
        const onlineCount = Object.values(health).filter(Boolean).length;
        if (!onlineCount) throw new Error('All required DEPO services are unavailable.');
        if (active && !controller.signal.aborted) {
          setServiceStatus(onlineCount === Object.keys(health).length ? 'online' : 'degraded');
          retryDelayMs = 30000;
        }
      } catch (error) {
        if (active && !controller.signal.aborted && error?.code !== 'ERR_CANCELED' && error?.name !== 'CanceledError') {
          setServiceStatus('offline');
          retryDelayMs = Math.min(retryDelayMs * 2, 300000);
        }
      } finally {
        inFlight = false;
        if (currentController === controller) currentController = null;
        if (active) {
          retryTimer = window.setTimeout(checkHealth, controller.signal.aborted ? 0 : retryDelayMs);
        }
      }
    };
    const verifyHealth = () => { if (!inFlight) void checkHealth(); else currentController?.abort(); };
    window.addEventListener('depo:access-verified', verifyHealth);
    checkHealth();
    return () => {
      window.removeEventListener('depo:access-verified', verifyHealth);
      active = false;
      if (retryTimer) window.clearTimeout(retryTimer);
      currentController?.abort();
    };
  }, [page]);

  useEffect(() => {
    if (!showChat || typeof window === 'undefined') return undefined;
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') setShowChat(false);
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [showChat]);

  const toggleChat = useCallback(() => {
    setShowChat((prev) => !prev);
  }, []);

  const handleNavigate = useCallback((target) => {
    const nextPage = normalizePage(target);
    if (nextPage === 'home') {
      pushPageLocation('home');
      setPage('home');
      return;
    }
    pushPageLocation(nextPage);
    setPage('app');
    setActivePage(nextPage);
  }, []);

  const handleSchemaCleaned = useCallback(() => {
    setCompanionSelection(null);
    setData({ nodes: [], links: [] });
    setSearchResults(null);
    setChatResults(null);
    setVisibleRelationships(null);
  }, []);

  const [serviceAuthRevision, setServiceAuthRevision] = useState(0);
  const handleServiceAuthChange = useCallback(() => {
    setCompanionSelection(null);
    setData(undefined);
    setSearchResults(null);
    setChatResults(null);
    setVisibleRelationships(null);
    setServiceAuthRevision(revision => revision + 1);
  }, []);
  const graphProps = useMemo(() => ({
    onBusinessSelection: setCompanionSelection,
    graphData: data,
    setData,
    searchResults,
    setSearchResults,
    chatResults,
    setChatResults,
    visibleRelationships,
    setVisibleRelationships,
    showChat,
    toggleChat,
    setActiveTab: handleNavigate,
  }), [data, searchResults, chatResults, visibleRelationships, showChat, toggleChat, handleNavigate]);

  return (
    <ErrorBoundary>
      <BrowserAccessBoundary>
      <OntologyProvider>
        <SchemaProvider key={`schema-${serviceAuthRevision}`}>
          <div style={{ minHeight: '100dvh' }}>
            {configurationWarnings.length > 0 && <div role="alert">{configurationWarnings.map(message => <p key={message}>{message}</p>)}</div>}
            <AppShell
            activePage={page === 'home' ? 'home' : activePage}
            onPageChange={handleNavigate}
            onHome={() => {
              pushPageLocation('home');
              setPage('home');
            }}
            showChat={showChat}
            onToggleChat={toggleChat}
            serviceStatus={serviceStatus}
            onServiceAuthChange={handleServiceAuthChange}
            rightDrawer={(
              <ErrorBoundary>
                <Suspense fallback={<PageFallback />}>
                    {page !== 'home' && activePage === 'change-control' ? <p>Change Control shows retained cross-workspace evidence. Open the owning workflow to investigate a selected proposal with its Governor or Steward. This view does not grant approval or execute changes.</p> : <Chatbot
                      key={`chat-${serviceAuthRevision}`}
                    graphData={page !== 'home' && ['graph','whereused'].includes(activePage) ? data : undefined}
                    pageId={page === 'home' ? 'home' : activePage}
                    runId={page !== 'home' && recordCompanionSelection?.page === activePage ? recordCompanionSelection.run_id || '' : ''}
                    productId={page !== 'home' && recordCompanionSelection?.page === activePage ? recordCompanionSelection.product_id || '' : ''}
                    productVersion={page !== 'home' && recordCompanionSelection?.page === activePage ? recordCompanionSelection.product_version || '' : ''}
                    nodeId={page !== 'home' && activePage === 'graph' ? companionSelection?.node_id || '' : ''}
                    ontologyId={page !== 'home' && activePage === 'ontology' ? ontologyCompanionSelection?.ontology_id || '' : page !== 'home' && activePage === 'graph' ? companionSelection?.ontology_id || '' : ''}
                    ontologyPrefix={page !== 'home' && activePage === 'ontology' ? ontologyCompanionSelection?.ontology_prefix || '' : page !== 'home' && activePage === 'graph' ? companionSelection?.ontology_prefix || '' : ''}
                    contextLabel={page !== 'home' && activePage === 'ontology' ? ontologyCompanionSelection?.label || '' : page !== 'home' && activePage === 'graph' ? companionSelection?.label || '' : ''}
                    setChatResults={setChatResults}
                  />}
                </Suspense>
              </ErrorBoundary>
            )}
            >
              <Suspense fallback={null}><PageTaskWorkspace key={`tasks-${page === 'home' ? 'home' : activePage}-${serviceAuthRevision}`} page={page === 'home' ? 'home' : activePage} /></Suspense>
              {page === 'home' ? (
                <LandingPage key={`home-${serviceAuthRevision}`} setChatResults={setChatResults} onNavigate={handleNavigate} />
              ) : (
                <AppPageOutlet
                  key={`${activePage}-${serviceAuthRevision}`}
                  page={activePage}
                  pageContext={{
                    data,
                    searchResults,
                    chatResults,
                    graphProps,
                    onNavigate: handleNavigate,
                    onSchemaCleaned: handleSchemaCleaned,
                    onOntologyContextChange: setOntologyCompanionSelection,
                    onCompanionRecordChange: setRecordCompanionSelection,
                  }}
                />
              )}
            </AppShell>
          </div>
        </SchemaProvider>
      </OntologyProvider>
      </BrowserAccessBoundary>
    </ErrorBoundary>
  );
}

export default App;
