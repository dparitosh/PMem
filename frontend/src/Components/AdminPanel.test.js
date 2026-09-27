import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import { ConfirmationDialog } from './AdminPanel';

test('destructive confirmation remains disabled until the exact phrase is entered', () => {
  const resolve = vi.fn();
  render(<ConfirmationDialog confirmation={{ title: 'Reset graph?', description: 'Deletes graph data.', phrase: 'RESET GRAPH', confirmLabel: 'Reset graph' }} onResolve={resolve} />);

  const confirm = screen.getByRole('button', { name: 'Reset graph' });
  expect(confirm).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Confirmation phrase'), { target: { value: 'RESET GRAPH' } });
  expect(confirm).toBeEnabled();
  fireEvent.click(confirm);
  expect(resolve).toHaveBeenCalledWith(true);
});

test('destructive confirmation supports keyboard cancellation', () => {
  const resolve = vi.fn();
  render(<ConfirmationDialog confirmation={{ title: 'Delete schemas?', description: 'Deletes retained schemas.' }} onResolve={resolve} />);
  fireEvent.keyDown(window, { key: 'Escape' });
  expect(resolve).toHaveBeenCalledWith(false);
});
