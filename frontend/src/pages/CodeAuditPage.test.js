import React from 'react';
import { vi } from 'vitest';
import { fireEvent, render, waitFor } from '@testing-library/react';
import CodeAuditPage from './CodeAuditPage';
import { apiClient } from '../services/apiClient';
vi.mock('@siemens/ix-react', () => ({ IxBadge: ({children}) => <span>{children}</span>, IxButton: ({children, onClick, disabled}) => <button onClick={onClick} disabled={disabled}>{children}</button>, IxCheckbox: () => <span />, IxInput: () => <input />, IxSelect: ({children}) => <div>{children}</div>, IxSelectItem: () => <span /> }));
vi.mock('../services/apiClient', () => ({ apiClient: { get: vi.fn() } }));
import { reviewHeadline } from './CodeAuditPage';

test('malformed recommendation collections do not crash the summary', () => {
  for (const recommendations of [null, {}, 'invalid', [null]]) {
    expect(reviewHeadline({ graph: { analysis: { recommendations } } })).toContain('No high-priority');
  }
});

test('missing or malformed reasons show an explicit fallback', () => {
  for (const reasons of [undefined, null, 'invalid', {}, [null, 3]]) {
    expect(reviewHeadline({ graph: { analysis: { recommendations: [{ file: 'backend/app.py', reasons }] } } }))
      .toBe('app.py — Review details unavailable');
  }
});

test('valid recommendation reasons remain visible', () => {
  expect(reviewHeadline({ graph: { analysis: { recommendations: [{ file: 'backend/app.py', reasons: ['cycle', 'coupling'] }] } } }))
    .toBe('app.py — cycle, coupling');
});


test('changing credentials replaces an in-flight audit request', async () => {
  let finishOld;
  apiClient.get.mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve; }))
    .mockResolvedValue({ data: { graph: { nodes: [], links: [] } } });
  render(<CodeAuditPage />);
  await waitFor(() => expect(apiClient.get).toHaveBeenCalledTimes(1));
  const oldSignal = apiClient.get.mock.calls[0][1].signal;
  fireEvent(window, new Event('depo:credentials-changed'));
  await waitFor(() => expect(apiClient.get).toHaveBeenCalledTimes(2));
  expect(oldSignal.aborted).toBe(true);
  finishOld({ data: { graph: { nodes: [], links: [] } } });
  fireEvent(window, new Event('depo:credentials-cleared'));
  await waitFor(() => expect(apiClient.get).toHaveBeenCalledTimes(3));
});
