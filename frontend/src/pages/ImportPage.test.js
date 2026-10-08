import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { vi } from 'vitest';
import ImportPage from './ImportPage';

vi.mock('../Components/DataImportPipeline', () => ({ default: () => <p>Data workspace</p> }));
vi.mock('./QifPage', () => ({ default: () => <p>QIF workspace</p> }));
vi.mock('./SysmlRepositoryImport', () => ({ default: () => <p>SysML workspace</p> }));

test('import workspace tabs support keyboard selection and roving focus', () => {
  render(<ImportPage />);
  fireEvent.keyDown(screen.getByRole('tab', { name: 'Data import' }), { key: 'End' });
  const sysml = screen.getByRole('tab', { name: 'SysML repository' });
  expect(sysml).toHaveFocus();
  expect(sysml).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByText('SysML workspace')).toBeInTheDocument();
  expect(screen.queryByText('Data workspace')).toBeNull();
});
