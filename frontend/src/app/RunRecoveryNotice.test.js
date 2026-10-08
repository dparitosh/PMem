import React from 'react';
import { vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import RunRecoveryNotice from './RunRecoveryNotice';
import agenticAPI from '../services/agenticApi';
vi.mock('../services/agenticApi', () => ({default:{getRun:vi.fn()}}));

test('credential change clears retained notice and rejects a stale response', async () => {
  let resolve;
  agenticAPI.getRun.mockReturnValue(new Promise(done => {resolve=done;}));
  render(<RunRecoveryNotice />);
  act(() => window.dispatchEvent(new CustomEvent('depo:run-recovery', {detail:{runId:'private-run',kind:'workflow'}})));
  fireEvent.click(screen.getByText('Load retained run status'));
  act(() => window.dispatchEvent(new Event('depo:credentials-cleared')));
  await act(async () => resolve({data:{status:'completed'}}));
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});
