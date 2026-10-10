import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi, test, expect } from 'vitest';
import RequirementsPage from './RequirementsPage';

const { list } = vi.hoisted(() => ({ list: vi.fn() }));
vi.mock('../services/apiClient', () => ({ API_METHODS: { requirements: { list } } }));

test('requirements browse server pages and refresh after credentials change', async () => {
  list.mockResolvedValueOnce({ data: { requirements: [{ requirement_id: 'r1', title: 'First requirement' }], has_more: true } })
    .mockResolvedValue({ data: { requirements: [{ requirement_id: 'r2', title: 'Second requirement' }], has_more: false } });
  render(<RequirementsPage />);
  await screen.findByText('First requirement');
  fireEvent.click(screen.getByText('Next'));
  await screen.findByText('Second requirement');
  expect(list).toHaveBeenLastCalledWith({ source: 'all', limit: 1000, offset: 1000 });
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'ReqIF' } });
  await waitFor(() => expect(list).toHaveBeenLastCalledWith({ source: 'ReqIF', limit: 1000, offset: 0 }));
  const before = list.mock.calls.length;
  fireEvent(window, new Event('depo:credentials-changed'));
  await waitFor(() => expect(list.mock.calls.length).toBeGreaterThan(before));
});
