import React from 'react';
import { MessageSquare } from 'lucide-react';
import { SiemensBadge, SiemensButton, SiemensNavigationIcon } from '../ui/SiemensPrimitives';
import { navigationItems, pageLabel } from './navigation';
import './AppShell.css';

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
  return (
    <div className="depo-shell">
      <nav className="depo-rail" aria-label="Application navigation">
        <div className="depo-rail__brand">
          <div className="depo-rail__brand-mark" aria-hidden="true">D</div>
          <div className="depo-rail__brand-text">
            <div className="depo-rail__brand-name">DEPO</div>
            <div className="depo-rail__brand-meta">Digital Thread</div>
          </div>
        </div>
        {navigationItems.map((item) => {
          const active = item.id === activePage;
          return (
            <SiemensButton
              key={item.id}
              type="button"
              variant={active ? 'primary' : 'tertiary'}
              alignment="start"
              className={`depo-rail__button ${active ? 'is-active' : ''}`}
              title={item.label}
              aria-label={item.label}
              aria-current={active ? 'page' : undefined}
              onClick={() => (item.id === 'home' ? onHome() : onPageChange(item.id))}
            >
              <SiemensNavigationIcon className="depo-rail__icon" name={item.icon} size="16" aria-hidden="true" />
              <span>{item.label}</span>
            </SiemensButton>
          );
        })}
      </nav>

      <header className="depo-topbar">
        <div className="depo-topbar__title">
          <nav className="depo-breadcrumb" aria-label="Breadcrumb">
            <SiemensButton type="button" variant="tertiary" onClick={onHome}>Home</SiemensButton>
            <span aria-hidden="true">/</span>
            <span>{pageLabel(activePage)}</span>
          </nav>
          <h1>{pageLabel(activePage)}</h1>
        </div>
        <div className="depo-topbar__actions">
          <SiemensBadge
            className={`depo-status depo-status--${serviceStatus}`}
            type="label"
            variant={serviceStatus === 'online' ? 'success' : serviceStatus === 'offline' ? 'alarm' : 'neutral'}
            label={serviceStatus === 'online' ? 'Online' : serviceStatus === 'offline' ? 'Unavailable' : 'Checking'}
            role="status"
            aria-live="polite"
          />
          <SiemensButton
            type="button"
            variant="tertiary"
            className="depo-icon-button"
            title="Toggle chat"
            aria-label="Toggle chat"
            aria-expanded={Boolean(showChat)}
            aria-controls="depo-chat-drawer"
            onClick={onToggleChat}
          >
            <MessageSquare size={16} fill={showChat ? '#eef5fb' : 'none'} />
          </SiemensButton>
        </div>
      </header>

      <main className="depo-main">
        <div className="depo-content">{children}</div>
        {rightDrawer && (
          <aside
            id="depo-chat-drawer"
            className="depo-drawer"
            aria-label="Chat assistant"
            hidden={!showChat}
          >
            {rightDrawer}
          </aside>
        )}
      </main>
    </div>
  );
}
