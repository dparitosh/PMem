import React from 'react';
import { MessageSquare } from 'lucide-react';
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
          const Icon = item.icon;
          const active = item.id === activePage;
          return (
            <button
              key={item.id}
              type="button"
              className={`depo-rail__button ${active ? 'is-active' : ''}`}
              title={item.label}
              aria-label={item.label}
              aria-current={active ? 'page' : undefined}
              onClick={() => (item.id === 'home' ? onHome() : onPageChange(item.id))}
            >
              <Icon size={16} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      <header className="depo-topbar">
        <div className="depo-topbar__title">
          <nav className="depo-breadcrumb" aria-label="Breadcrumb">
            <button type="button" onClick={onHome}>Home</button>
            <span aria-hidden="true">/</span>
            <span>{pageLabel(activePage)}</span>
          </nav>
          <h1>{pageLabel(activePage)}</h1>
        </div>
        <div className="depo-topbar__actions">
          <span className={`depo-status depo-status--${serviceStatus}`} role="status" aria-live="polite">
            {serviceStatus === 'online' ? 'Online' : serviceStatus === 'offline' ? 'Unavailable' : 'Checking'}
          </span>
          <button
            type="button"
            className="depo-icon-button"
            title="Toggle chat"
            aria-label="Toggle chat"
            aria-expanded={Boolean(showChat)}
            aria-controls="depo-chat-drawer"
            onClick={onToggleChat}
          >
            <MessageSquare size={16} fill={showChat ? '#eef5fb' : 'none'} />
          </button>
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
