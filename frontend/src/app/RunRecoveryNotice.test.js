import React from 'react';
import { vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import RunRecoveryNotice from './RunRecoveryNotice';
import agenticAPI from '../services/agenticApi';
import { dataPipelineAPI } from '../services/apiClient';
vi.mock('../services/agenticApi', () => ({default:{getRun:vi.fn()}}));
vi.mock('../services/apiClient', () => ({dataPipelineAPI:{getRun:vi.fn()}}));
beforeEach(() => { vi.clearAllMocks(); sessionStorage.clear(); });

test('credential change retains the run identity and rejects a stale response', async () => {
  let resolve;
  agenticAPI.getRun.mockReturnValue(new Promise(done => {resolve=done;}));
  render(<RunRecoveryNotice />);
  act(() => window.dispatchEvent(new CustomEvent('depo:run-recovery', {detail:{runId:'private-run',kind:'workflow'}})));
  fireEvent.click(screen.getByText('Load retained run status'));
  act(() => window.dispatchEvent(new Event('depo:credentials-cleared')));
  await act(async () => resolve({data:{status:'completed'}}));
  expect(screen.getByRole('alert')).toHaveTextContent('private-run');
  expect(screen.queryByText(/Status: completed/)).toBeNull();
});

test('multiple run bookmarks survive remount and can be dismissed independently', () => {
  const view = render(<RunRecoveryNotice />);
  for (const runId of ['first', 'second', 'first']) act(() => window.dispatchEvent(new CustomEvent('depo:run-recovery', {detail:{runId,kind:'pipeline'}})));
  expect(screen.getAllByRole('alert')).toHaveLength(2);
  view.unmount();
  render(<RunRecoveryNotice />);
  expect(screen.getAllByRole('alert')).toHaveLength(2);
  fireEvent.click(screen.getAllByText('Dismiss')[0]);
  expect(screen.getByRole('alert')).toHaveTextContent('second');
});

test('pipeline recovery loads status from the pipeline service', async () => {
  dataPipelineAPI.getRun.mockResolvedValue({data:{run_id:'pipeline-run',status:'completed'}});
  render(<RunRecoveryNotice />);
  act(() => window.dispatchEvent(new CustomEvent('depo:run-recovery', {detail:{runId:'pipeline-run',kind:'pipeline'}})));
  fireEvent.click(screen.getByText('Load retained run status'));
  await screen.findByText(/Status: completed/);
  expect(dataPipelineAPI.getRun).toHaveBeenCalledWith('pipeline-run');
  expect(agenticAPI.getRun).not.toHaveBeenCalled();
});

test('a response for another pipeline run is rejected with diagnostics', async () => {
  dataPipelineAPI.getRun.mockResolvedValue({data:{run_id:'other-run',status:'completed'}});
  render(<RunRecoveryNotice />);
  act(() => window.dispatchEvent(new CustomEvent('depo:run-recovery', {detail:{runId:'pipeline-run',kind:'pipeline'}})));
  fireEvent.click(screen.getByText('Load retained run status'));
  await screen.findByText('The status response does not match this pipeline run.');
  expect(screen.queryByText(/Status: completed/)).toBeNull();
});

test('recovery errors display the server request ID', async () => {
  dataPipelineAPI.getRun.mockRejectedValue({response:{status:503,headers:{'x-request-id':'status-request'},data:{detail:'Registry unavailable'}}});
  render(<RunRecoveryNotice />);
  act(() => window.dispatchEvent(new CustomEvent('depo:run-recovery', {detail:{runId:'pipeline-run',kind:'pipeline'}})));
  fireEvent.click(screen.getByText('Load retained run status'));
  await screen.findByText('Registry unavailable Request ID: status-request');
});
