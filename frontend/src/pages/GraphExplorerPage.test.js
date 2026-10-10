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


test.each([{}, {status:'unknown'}])('rejects malformed or unknown health contracts %s', async data => {
  health.mockResolvedValueOnce({data});
  render(<GraphExplorerPage />);
  expect(await screen.findByText('Graph Explorer is unavailable')).toBeInTheDocument();
  expect(screen.queryByText('Graph canvas')).not.toBeInTheDocument();
});


test.each([401, 403])('explains credential failures for HTTP %s', async status => {
  health.mockRejectedValueOnce({response: {status}});
  render(<GraphExplorerPage />);
  expect(await screen.findByText('Graph access required')).toBeInTheDocument();
  expect(screen.getByText('Connect or validate graph read access in Admin, then retry.')).toBeInTheDocument();
});
