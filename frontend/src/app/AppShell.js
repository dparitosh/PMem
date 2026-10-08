import React, { useEffect, useRef, useState } from 'react';
import {
  IxApplication,
  IxApplicationHeader,
  IxAvatar,
  IxBadge,
  IxButton,
  IxContent,
  IxContentHeader,
  IxMenu,
  IxMenuItem,
} from '@siemens/ix-react';
import { navigationItems, pageLabel } from './navigation';
import { getServiceAuthToken, wasBrowserSessionExpired } from '../services/serviceAuth';
import RunRecoveryNotice from './RunRecoveryNotice';
import { verifyStoredReadAccess } from '../services/readAccessVerification';
import './AppShell.css';

const THEME_STORAGE_KEY = 'depo.colorSchema';
const EXPIRED_ACCESS_MESSAGE = 'API session expired. Use Reconnect access to restore registered scopes.';

function initialColorSchema() {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === 'dark' || stored === 'light') return stored;
  } catch (_error) { /* restricted browser storage */ }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

// Matches the official Siemens IX React starter frame while keeping DEPO
// feature pages and their API integrations independent from the shell.
export default function AppShell({
  activePage,
  onPageChange,
  onHome,
  showChat,
  onToggleChat,
  serviceStatus = 'checking',
  rightDrawer,
  onServiceAuthChange,
  children,
}) {
  const [colorSchema, setColorSchema] = useState(initialColorSchema);
  const [apiAccessConfigured, setApiAccessConfigured] = useState(() => Boolean(getServiceAuthToken()));
  const [verifyingAccess, setVerifyingAccess] = useState(false);
  const [accessMessage, setAccessMessage] = useState(() => wasBrowserSessionExpired() ? EXPIRED_ACCESS_MESSAGE : '');
  const accessRequest = useRef(null);
  useEffect(() => () => { accessRequest.current?.abort(); accessRequest.current = null; }, []);
  const openAccess = () => {
    try { sessionStorage.setItem('depo:admin-tab', 'access'); } catch {}
    window.dispatchEvent(new CustomEvent('depo:admin-section', { detail: 'access' }));
    onPageChange('admin');
  };
  const revalidateAccess = async () => {
    if (accessRequest.current) return;
    const controller = new AbortController(); accessRequest.current = controller;
    const timeout = setTimeout(() => controller.abort(), 15000);
    setVerifyingAccess(true); setAccessMessage('Checking stored API access…');
    try {
      const result = await verifyStoredReadAccess({ signal: controller.signal });
      if (!controller.signal.aborted) {
        setAccessMessage(result.message);
      }
      if (result.status === 'reconnect_required' && (!controller.signal.aborted || wasBrowserSessionExpired())) openAccess();
    } catch { if (!controller.signal.aborted) setAccessMessage('Access could not be verified. Try again.'); }
    finally {
      clearTimeout(timeout);
      if (accessRequest.current === controller) {
        accessRequest.current = null; setVerifyingAccess(false);
        if (controller.signal.aborted) setAccessMessage('Verification timed out. Retry when services are reachable.');
      }
    }
  };
  useEffect(() => {
    const changed = event => { setApiAccessConfigured(Boolean(getServiceAuthToken())); setAccessMessage(event.type === 'depo:session-expired' || wasBrowserSessionExpired() ? EXPIRED_ACCESS_MESSAGE : ''); onServiceAuthChange?.(); };
    window.addEventListener('depo:credentials-changed', changed);
    window.addEventListener('depo:credentials-cleared', changed);
    window.addEventListener('depo:session-expired', changed);
    return () => { window.removeEventListener('depo:credentials-changed', changed); window.removeEventListener('depo:credentials-cleared', changed); window.removeEventListener('depo:session-expired', changed); };
  }, [onServiceAuthChange]);
  useEffect(() => {
    document.documentElement.dataset.ixTheme = 'classic';
    document.documentElement.dataset.ixColorSchema = colorSchema;
    document.documentElement.style.colorScheme = colorSchema;
    try { window.localStorage.setItem(THEME_STORAGE_KEY, colorSchema); } catch (_error) { /* optional preference */ }
  }, [colorSchema]);
  useEffect(() => {
    const observer = new MutationObserver(() => {
      const next = document.documentElement.dataset.ixColorSchema;
      if (next === 'dark' || next === 'light') setColorSchema(next);
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-ix-color-schema'] });
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    const target = document.getElementById(showChat ? 'depo-chat-drawer' : 'depo-chat-toggle');
    target?.focus?.();
  }, [showChat]);

  const statusVariant = serviceStatus === 'online'
    ? 'success'
    : serviceStatus === 'degraded'
      ? 'warning'
      : serviceStatus === 'offline'
        ? 'alarm'
        : 'neutral';
  const statusLabel = serviceStatus === 'online'
    ? 'Online'
    : serviceStatus === 'degraded'
      ? 'Degraded'
      : serviceStatus === 'offline'
        ? 'Unavailable'
        : 'Checking';

  return (
    <>
      <a href="#main-content" className="skip-link">Skip to main content</a>
      <IxApplication theme="classic" colorSchema={colorSchema}>
        <IxApplicationHeader name="DEPO | Digital Thread">
          <div className="depo-app-mark" aria-label="DEPO">D</div>
          <IxBadge type="label" variant={statusVariant} label={statusLabel} role="status" aria-live="polite" />
          <IxButton
            type="button"
            variant="tertiary"
            onClick={openAccess}
            aria-label="Configure API access"
          >
            API access{apiAccessConfigured ? ' configured' : ''}
          </IxButton>
          <IxButton type="button" variant="tertiary" disabled={verifyingAccess} onClick={revalidateAccess} aria-label="Revalidate or reconnect API access">
            {verifyingAccess ? 'Checking access…' : apiAccessConfigured ? 'Revalidate access' : 'Reconnect access'}
          </IxButton>
          <IxButton
            id="depo-chat-toggle"
            type="button"
            variant="tertiary"
            icon="info"
            onClick={onToggleChat}
            aria-label="Toggle Knowledge Companion"
            aria-expanded={showChat}
            aria-controls="depo-chat-drawer"
          >
            Chat
          </IxButton>
          <IxButton
            type="button"
            variant="tertiary"
            onClick={() => setColorSchema((current) => current === 'dark' ? 'light' : 'dark')}
            aria-label={`Use ${colorSchema === 'dark' ? 'light' : 'dark'} theme`}
            aria-pressed={colorSchema === 'dark'}
          >
            {colorSchema === 'dark' ? 'Light' : 'Dark'}
          </IxButton>
          <IxAvatar initials="DT" aria-label="Digital Thread workspace" />
        </IxApplicationHeader>

        {/* Keep the desktop menu breakpoint explicit. IX recalculates overflow
            while custom elements hydrate; an implicit breakpoint can trigger
            its scroll handler before the menu items container exists. */}
        <IxMenu aria-label="Application navigation" breakpoint="lg" enableToggleTheme={false}>
          {navigationItems.map((item) => (
            <IxMenuItem
              key={item.id}
              icon={item.icon}
              active={item.id === activePage}
              onClick={(event) => {
                event.preventDefault();
                if (item.id === 'home') onHome();
                else onPageChange(item.id);
              }}
            >
              {item.label}
            </IxMenuItem>
          ))}
        </IxMenu>

        <IxContent id="main-content" className="depo-ix-content">

          <div className="depo-ix-page">
            {accessMessage && <div aria-live="polite" className="depo-alert">{accessMessage}</div>}
            <IxContentHeader
              headerTitle={pageLabel(activePage)}
              headerSubtitle={activePage === 'home' ? 'Digital thread workspace' : undefined}
              hasBackButton={false}
              variant="primary"
            />
            <div className="depo-ix-page__body"><RunRecoveryNotice />{children}</div>
          </div>
          {rightDrawer && (
            <aside id="depo-chat-drawer" className="depo-ix-drawer" aria-label="Knowledge Companion" hidden={!showChat} tabIndex={-1}>
              <div className="depo-ix-drawer__header">
                <strong>Knowledge Companion</strong>
                <button type="button" className="depo-ix-drawer__close" onClick={onToggleChat} aria-label="Close Knowledge Companion">×</button>
              </div>
              <div className="depo-ix-drawer__body">{rightDrawer}</div>
            </aside>
          )}
        </IxContent>
      </IxApplication>
    </>
  );
}
