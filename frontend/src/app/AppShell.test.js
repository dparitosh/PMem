import { fireEvent, render, screen } from '@testing-library/react';
import AppShell from './AppShell';

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
  const chatButton = screen.getByRole('button', { name: 'Toggle chat' });
  expect(chatButton).toHaveAttribute('aria-expanded', 'true');
  expect(chatButton).toHaveAttribute('aria-controls', 'depo-chat-drawer');
  fireEvent.click(chatButton);
  expect(onToggleChat).toHaveBeenCalledTimes(1);
});
