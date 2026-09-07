import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import AppShell from './AppShell';

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
  IxMenu: ({ children, ...props }) => <nav {...props}>{children}</nav>,
  IxMenuItem: ({ children, active, ...props }) => <button aria-current={active ? 'page' : undefined} {...props}>{children}</button>,
}));

test('exposes active navigation, backend status, and chat drawer state', () => {
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
  expect(screen.getByRole('complementary', { name: 'Chat assistant' })).toBeInTheDocument();
  const chatButton = screen.getByRole('button', { name: 'Toggle Knowledge Companion' });
  expect(chatButton).toHaveAttribute('aria-expanded', 'true');
  expect(chatButton).toHaveAttribute('aria-controls', 'depo-chat-drawer');
  fireEvent.click(chatButton);
  expect(onToggleChat).toHaveBeenCalledTimes(1);
});
