import React from 'react';
import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import ErrorBoundary from './ErrorBoundary';

function BrokenPage() {
  throw new Error('render failed');
}

test('renders a recoverable fallback when a feature page throws', () => {
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
  render(<ErrorBoundary><BrokenPage /></ErrorBoundary>);

  expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong');
  expect(screen.getByRole('button', { name: 'Try Again' })).toHaveAttribute('type', 'button');
  expect(screen.getByRole('button', { name: 'Go Home' })).toHaveAttribute('type', 'button');
  consoleError.mockRestore();
});
