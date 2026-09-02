import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import GraphExplorerPage from './GraphExplorerPage';

const { health } = vi.hoisted(() => ({ health: vi.fn() }));

vi.mock('../services/apiClient', () => ({
  platformAPI: { health },
}));

vi.mock('../Components/GraphHEB', () => ({ default: () => <div>Graph canvas</div> }));

test('does not mount the legacy graph view when graph storage is not configured', async () => {
  health.mockResolvedValueOnce({ data: { status: 'not_configured' } });

  render(<GraphExplorerPage />);

  expect(await screen.findByText('Graph store setup required')).toBeInTheDocument();
  expect(screen.queryByText('Graph canvas')).not.toBeInTheDocument();
});
