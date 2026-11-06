import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
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

test('filters execution attention separately from recorded measurements', async () => {
  dataPipelineAPI.runs.mockResolvedValue({data:{runs:[
    {run_id:'measured-run',job_type:'source_validation',status:'completed',output_manifest:{counts:{records:12}}},
    {run_id:'failed-run',job_type:'quality_check',status:'failed'}
  ]}});
  render(<QualityPage />);
  await screen.findByText('measured-run');
  expect(screen.getByText(/Execution status is not a quality verdict/)).toBeVisible();
  fireEvent.change(screen.getByLabelText('Show'),{target:{value:'attention'}});
  expect(screen.queryByText('measured-run')).toBeNull();
  expect(screen.getByText('failed-run')).toBeVisible();
  fireEvent.change(screen.getByLabelText('Show'),{target:{value:'evidence'}});
  expect(screen.getByText('measured-run')).toBeVisible();
  expect(screen.queryByText('failed-run')).toBeNull();
  fireEvent.change(screen.getByLabelText('Find a run or job'),{target:{value:'no-match'}});
  expect(screen.getByText(/No runs match/)).toBeVisible();
});
