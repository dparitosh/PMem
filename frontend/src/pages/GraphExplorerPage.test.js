import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import GraphExplorerPage from './GraphExplorerPage';

const { health } = vi.hoisted(() => ({ health: vi.fn() }));

vi.mock('../services/apiClient', () => ({
  platformAPI: { health },
}));

vi.mock('../features/graph/GraphWorkspace.js', () => ({ default: () => <div>Graph canvas</div> }));

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

test('successful access revalidation rechecks an unavailable graph without remounting the page',async()=>{
 health.mockReset();health.mockRejectedValueOnce({response:{status:403}}).mockResolvedValueOnce({data:{status:'ready'}});
 render(<GraphExplorerPage/>);await screen.findByText('Graph access required');
 fireEvent(window,new Event('depo:access-verified'));
 expect(await screen.findByText('Graph canvas')).toBeVisible();expect(health).toHaveBeenCalledTimes(2);
});
test('a revalidation aborts the previous probe and discards its late failure',async()=>{
 health.mockReset();let finish;health.mockReturnValueOnce(new Promise(resolve=>{finish=resolve;})).mockResolvedValueOnce({data:{status:'ready'}});
 render(<GraphExplorerPage/>);const signal=health.mock.calls[0][1].signal;
 fireEvent(window,new Event('depo:access-verified'));expect(signal.aborted).toBe(true);
 expect(await screen.findByText('Graph canvas')).toBeVisible();
 await act(async()=>finish({data:{status:'not_configured'}}));expect(screen.queryByText('Graph store setup required')).toBeNull();
});
