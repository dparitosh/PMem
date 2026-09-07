import React from 'react';
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
import './AppShell.css';

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
  children,
}) {
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
      <IxApplication>
        <IxApplicationHeader name="DEPO | Digital Thread">
          <div className="depo-app-mark" aria-label="DEPO">D</div>
          <IxBadge type="label" variant={statusVariant} label={statusLabel} role="status" aria-live="polite" />
          <IxButton
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
          <IxAvatar initials="DT" aria-label="Digital Thread workspace" />
        </IxApplicationHeader>

        {/* Keep the desktop menu breakpoint explicit. IX recalculates overflow
            while custom elements hydrate; an implicit breakpoint can trigger
            its scroll handler before the menu items container exists. */}
        <IxMenu aria-label="Application navigation" breakpoint="lg">
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
            <IxContentHeader
              headerTitle={pageLabel(activePage)}
              headerSubtitle={activePage === 'home' ? 'Digital thread workspace' : undefined}
              hasBackButton={false}
              variant="primary"
            />
            <div className="depo-ix-page__body">{children}</div>
          </div>
          {rightDrawer && (
            <aside id="depo-chat-drawer" className="depo-ix-drawer" aria-label="Chat assistant" hidden={!showChat}>
              {rightDrawer}
            </aside>
          )}
        </IxContent>
      </IxApplication>
    </>
  );
}
