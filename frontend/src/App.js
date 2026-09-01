import 'bootstrap/dist/css/bootstrap.min.css';
import './App.css';
import './CSS/TCSColors.css';
import ErrorBoundary from './Components/ErrorBoundary';
import LandingPage from './Components/LandingPage';
import { SchemaProvider } from './SchemaContext';
import { OntologyProvider } from './contexts/OntologyContext';
import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowRight } from 'lucide-react';
import { SiemensButton } from './ui/SiemensPrimitives';
import AppShell from './app/AppShell';
import AppPageOutlet from './app/AppPageOutlet';
import { normalizePage } from './app/navigation';
import { API_METHODS } from './services/apiClient';

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
    const hashPage = hash.slice(2).split('/')[0];
    return hashPage ? normalizePage(hashPage) : 'home';
  }
  const pathname = String(window.location.pathname || '/');
  if (pathname === '/') return 'home';
  const pathPage = pathname.split('/').filter(Boolean)[0];
  return pathPage ? normalizePage(pathPage) : 'home';
}

function pushPageLocation(value) {
  if (typeof window === 'undefined' || !window.history?.pushState) return;
  const target = value === 'home' ? '#/home' : `#/${value}`;
  if (window.location.hash !== target.slice(1)) {
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
    if (page === 'home') return undefined;
    let active = true;
    let inFlight = false;
    let currentController = null;
    let retryDelayMs = 30000;
    let retryTimer = null;
    let consecutiveFailures = 0;
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
        const healthChecks = [
          () => API_METHODS.health.ready({ signal: controller.signal, timeout: 5000 }),
          () => API_METHODS.health.check({ signal: controller.signal, timeout: 5000 }),
          () => API_METHODS.ontology.listRegistered({ signal: controller.signal, timeout: 8000 }),
        ];
        let lastError = null;
        let healthy = false;
        for (const runCheck of healthChecks) {
          try {
            await runCheck();
            healthy = true;
            break;
          } catch (error) {
            if (error?.code === 'ERR_CANCELED' || error?.name === 'CanceledError') {
              throw error;
            }
            lastError = error;
          }
        }
        if (!healthy && lastError) throw lastError;
        if (active) {
          setServiceStatus('online');
          retryDelayMs = 30000;
          consecutiveFailures = 0;
        }
      } catch (error) {
        if (active && error?.code !== 'ERR_CANCELED' && error?.name !== 'CanceledError') {
          consecutiveFailures += 1;
          if (consecutiveFailures >= 3) {
            setServiceStatus('offline');
          }
          retryDelayMs = Math.min(retryDelayMs * 2, 300000);
        }
      } finally {
        inFlight = false;
        if (currentController === controller) currentController = null;
        if (active) {
          retryTimer = window.setTimeout(checkHealth, retryDelayMs);
        }
      }
    };
    checkHealth();
    return () => {
      active = false;
      if (retryTimer) window.clearTimeout(retryTimer);
      currentController?.abort();
    };
  }, [page]);

  useEffect(() => {
    if (typeof window !== 'undefined') window.dispatchEvent(new Event('resize'));
  }, [activePage, showChat]);

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
    setData({ nodes: [], links: [] });
    setSearchResults(null);
    setChatResults(null);
    setVisibleRelationships(null);
  }, []);

  const graphProps = useMemo(() => ({
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
      <OntologyProvider>
        <SchemaProvider>
          <div hidden={page !== 'home'}>
            <div className="depo-landing-shell">
              <header className="depo-landing-shell__header">
                <div>
                  <h1 className="depo-landing-shell__title">
                    DEPO Digital Thread Platform
                  </h1>
                  <p className="depo-landing-shell__subtitle">Ontology governance, traceability, and model intelligence in one workspace.</p>
                </div>
                <SiemensButton onClick={() => handleNavigate('import')} variant="primary" className="depo-landing-shell__action">
                  <span>Open platform</span>
                  <ArrowRight size={14} />
                </SiemensButton>
              </header>
              <main aria-label="Platform overview" className="depo-landing-shell__content">
                {page === 'home' && <LandingPage setChatResults={setChatResults} onNavigate={handleNavigate} />}
              </main>
            </div>
          </div>
          <div hidden={page === 'home'} style={{ minHeight: '100dvh' }}>
            <AppShell
            activePage={activePage}
            onPageChange={handleNavigate}
            onHome={() => {
              pushPageLocation('home');
              setPage('home');
            }}
            showChat={showChat}
            onToggleChat={toggleChat}
            serviceStatus={serviceStatus}
            rightDrawer={(
              <ErrorBoundary>
                <Suspense fallback={<PageFallback />}>
                  <Chatbot
                    graphData={data}
                    searchResults={searchResults}
                    chatResults={chatResults}
                    setSearchResults={setSearchResults}
                    setChatResults={setChatResults}
                  />
                </Suspense>
              </ErrorBoundary>
            )}
            >
              <AppPageOutlet
                page={activePage}
                pageContext={{
                  data,
                  searchResults,
                  chatResults,
                  graphProps,
                  onNavigate: handleNavigate,
                  onSchemaCleaned: handleSchemaCleaned,
                }}
              />
            </AppShell>
          </div>
        </SchemaProvider>
      </OntologyProvider>
    </ErrorBoundary>
  );
}

export default App;
