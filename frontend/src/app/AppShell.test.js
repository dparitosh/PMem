import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import AppShell from './AppShell';
import { graphApi } from '../services/graphApi';
vi.mock('../services/graphApi', () => ({ graphApi: { verifyAccess: vi.fn() } }));
import { clearServiceAuthToken, getServiceAuthToken } from '../services/serviceAuth';

// AppShell verifies our navigation contract, not Siemens IX internals. The
// real custom elements need browser APIs JSDOM does not faithfully emulate.
vi.mock('@siemens/ix-react', () => ({
  IxApplication: ({ children }) => <div>{children}</div>,
  IxApplicationHeader: ({ children }) => <header>{children}</header>,
  IxAvatar: () => <span aria-label="Digital Thread workspace" />,
  IxBadge: ({ label, ...props }) => <span {...props}>{label}</span>,
  IxButton: ({ children, ...props }) => <button {...props}>{children}</button>,
  IxContent: ({ children, ...props }) => <main {...props}>{children}</main>,
  IxContentHeader: ({ headerTitle }) => <h1>{headerTitle}</h1>,
  IxMenu: ({ children, enableToggleTheme, i18nToggleTheme: _i18nToggleTheme, ...props }) => <nav data-theme-toggle={String(enableToggleTheme)} {...props}>{children}</nav>,
  IxMenuItem: ({ children, active, ...props }) => <button aria-current={active ? 'page' : undefined} {...props}>{children}</button>,
}));

beforeEach(() => {
  graphApi.verifyAccess.mockReset();
  graphApi.verifyAccess.mockResolvedValue({ data: {} });
  clearServiceAuthToken();
  window.localStorage.clear();
  document.documentElement.dataset.ixColorSchema = 'light';
});

test('opens central Admin credentials instead of a duplicate key dialog', () => {
  const onPageChange = vi.fn();
  render(<AppShell activePage="home" onPageChange={onPageChange} onHome={vi.fn()} showChat={false} onToggleChat={vi.fn()}><div>Page content</div></AppShell>);
  fireEvent.click(screen.getByRole('button', { name: 'Configure API access' }));
  expect(onPageChange).toHaveBeenCalledWith('admin');
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});

test('exposes active navigation, backend status, chat drawer state, and persistent theme control', () => {
  const onToggleChat = jest.fn();
  render(
    <AppShell
      activePage="registry"
      onPageChange={jest.fn()}
      onHome={jest.fn()}
      showChat
      onToggleChat={onToggleChat}
      serviceStatus="offline"
      rightDrawer={<div>Assistant content</div>}
    >
      <div>Page content</div>
    </AppShell>,
  );

  expect(screen.getByRole('button', { name: 'Metadata Registry' })).toHaveAttribute('aria-current', 'page');
  expect(screen.getByRole('status')).toHaveTextContent('Unavailable');
  expect(screen.getByRole('complementary', { name: 'Knowledge Companion' })).toBeInTheDocument();
  const chatButton = screen.getByRole('button', { name: 'Toggle Knowledge Companion' });
  expect(chatButton).toHaveAttribute('aria-expanded', 'true');
  expect(chatButton).toHaveAttribute('aria-controls', 'depo-chat-drawer');
  fireEvent.click(chatButton);
  expect(onToggleChat).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole('button', { name: 'Close Knowledge Companion' }));
  expect(onToggleChat).toHaveBeenCalledTimes(2);
  fireEvent.click(screen.getByRole('button', { name: 'Use dark theme' }));
  expect(document.documentElement.dataset.ixColorSchema).toBe('dark');
  expect(window.localStorage.getItem('depo.colorSchema')).toBe('dark');
  expect(screen.getByRole('button', { name: 'Use light theme' })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('navigation')).toHaveAttribute('data-theme-toggle', 'false');
  expect(screen.getByRole('button', { name: 'Admin' })).toBeInTheDocument();
});
