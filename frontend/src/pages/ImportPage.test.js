import React from 'react';
import { render, screen, fireEvent, act, cleanup } from '@testing-library/react';
import { vi } from 'vitest';
import ImportPage from './ImportPage';

vi.mock('../features/import/ImportWorkspace.js', () => ({ default: () => <p>Data workspace</p> }));
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

beforeEach(()=>window.history.replaceState(null,'','#/import'));
test('import view survives remount and follows history without losing scope',async()=>{
 window.history.replaceState(null,'','#/import?view=qif&source=parts');
 const first=render(<ImportPage/>);expect(screen.getByText('QIF workspace')).toBeVisible();
 fireEvent.click(screen.getByRole('tab',{name:'SysML repository'}));
 expect(window.location.hash).toContain('view=sysml');expect(window.location.hash).toContain('source=parts');
 first.unmount();render(<ImportPage/>);expect(screen.getByText('SysML workspace')).toBeVisible();
 await act(async()=>{window.history.replaceState(null,'','#/import?view=qif&source=parts');window.dispatchEvent(new PopStateEvent('popstate'));});
 expect(screen.getByText('QIF workspace')).toBeVisible();
});
