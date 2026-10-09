import React from 'react';
import { act, render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import QualityPage from './QualityPage';
import { dataPipelineAPI } from '../services/apiClient';
vi.mock('../services/apiClient', () => ({ dataPipelineAPI: { runs: vi.fn() } }));

test('malformed run entries show an error rather than crashing the page', async () => {
  dataPipelineAPI.runs.mockResolvedValue({data:{runs:[null]}});
  render(<QualityPage />);
  expect(await screen.findByRole('alert')).toHaveTextContent('invalid run list');
});

test('disconnect clears prior-session quality evidence immediately', async () => {
  dataPipelineAPI.runs.mockResolvedValue({data:{runs:[{run_id:'private-run',status:'completed'}]}});
  render(<QualityPage />);
  await screen.findByText('private-run');
  act(() => window.dispatchEvent(new Event('depo:credentials-cleared')));
  expect(screen.queryByText('private-run')).toBeNull();
});
