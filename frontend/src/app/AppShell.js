import React, { useEffect, useState } from 'react';
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
import { clearServiceAuthToken, getServiceAuthToken, setServiceAuthToken } from '../services/serviceAuth';
import './AppShell.css';

const THEME_STORAGE_KEY = 'depo.colorSchema';

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
  const [showApiAccess, setShowApiAccess] = useState(false);
  const [apiKey, setApiKey] = useState(() => getServiceAuthToken());
  const [apiAccessConfigured, setApiAccessConfigured] = useState(() => Boolean(getServiceAuthToken()));
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
            onClick={() => {
              setApiKey(getServiceAuthToken());
              setShowApiAccess(true);
            }}
            aria-label="Configure API access"
          >
            API access{apiAccessConfigured ? ' configured' : ''}
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
        <IxMenu aria-label="Application navigation" breakpoint="lg" enableToggleTheme i18nToggleTheme="Toggle light and dark theme">
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
          {showApiAccess && (
            <div className="depo-api-access" role="dialog" aria-modal="true" aria-labelledby="depo-api-access-title">
              <form
                className="depo-api-access__panel"
                onSubmit={(event) => {
                  event.preventDefault();
                  setServiceAuthToken(apiKey);
                  setApiAccessConfigured(Boolean(apiKey.trim()));
                  setShowApiAccess(false);
                  onServiceAuthChange?.();
                }}
              >
                <h2 id="depo-api-access-title">Standalone API access</h2>
                <p>Enter the server GRAPH_READ_TOKEN. It remains only in this browser tab's memory and is cleared by a full reload.</p>
                <label htmlFor="depo-api-read-key">Graph read API key</label>
                <input
                  id="depo-api-read-key"
                  className="depo-api-access__input"
                  type="password"
                  autoComplete="off"
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                />
                <div className="depo-api-access__actions">
                  <button type="button" onClick={() => setShowApiAccess(false)}>Cancel</button>
                  <button
                    type="button"
                    onClick={() => {
                      clearServiceAuthToken();
                      setApiKey('');
                      setApiAccessConfigured(false);
                      setShowApiAccess(false);
                      onServiceAuthChange?.();
                    }}
                  >Clear</button>
                  <button type="submit" disabled={!apiKey.trim()}>Apply and retry</button>
                </div>
              </form>
            </div>
          )}
          <div className="depo-ix-page">
            <IxContentHeader
              headerTitle={pageLabel(activePage)}
              headerSubtitle={activePage === 'home' ? 'Digital thread workspace' : undefined}
              hasBackButton={false}
              variant="primary"
            />
            <div className="depo-ix-page__body">{children}</div>
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
