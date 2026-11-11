import React, { useState } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import {
  ConfirmDialog, DataTable, EmptyState, IxTabsBar, StatusBadge, TextField, CheckboxField, PrimaryButton,
} from './index';
import { modalSpies } from './ixReact.mock.js';

vi.mock('@siemens/ix-react', () => import('./ixReact.mock.js'));

beforeEach(() => {
  modalSpies.showModal.mockClear();
  modalSpies.closeModal.mockClear();
});

describe('IxTabsBar', () => {
  const tabs = [{ id: 'a', label: 'First' }, { id: 'b', label: 'Second' }, { id: 'c', label: 'Third' }];

  function Harness({ onChange = () => {} }) {
    const [active, setActive] = useState('a');
    return <IxTabsBar tabs={tabs} active={active} ariaLabel="Views" idPrefix="v" onChange={(id) => { onChange(id); setActive(id); }} />;
  }

  test('exposes a named tablist with roving tabindex and aria wiring', () => {
    render(<Harness />);
    expect(screen.getByRole('tablist', { name: 'Views' })).toBeInTheDocument();
    const first = screen.getByRole('tab', { name: 'First' });
    expect(first).toHaveAttribute('aria-selected', 'true');
    expect(first).toHaveAttribute('tabindex', '0');
    expect(first).toHaveAttribute('aria-controls', 'v-panel-a');
    expect(screen.getByRole('tab', { name: 'Second' })).toHaveAttribute('tabindex', '-1');
  });

  test('arrow keys wrap, Home and End jump, and focus follows selection', () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const first = screen.getByRole('tab', { name: 'First' });
    const second = screen.getByRole('tab', { name: 'Second' });
    const third = screen.getByRole('tab', { name: 'Third' });

    fireEvent.keyDown(first, { key: 'ArrowRight' });
    expect(onChange).toHaveBeenLastCalledWith('b');
    expect(second).toHaveAttribute('aria-selected', 'true');
    expect(second).toHaveFocus();

    fireEvent.keyDown(second, { key: 'End' });
    expect(third).toHaveAttribute('aria-selected', 'true');
    expect(third).toHaveFocus();

    fireEvent.keyDown(third, { key: 'ArrowRight' });
    expect(first).toHaveAttribute('aria-selected', 'true');
    expect(first).toHaveFocus();

    fireEvent.keyDown(first, { key: 'ArrowLeft' });
    expect(third).toHaveFocus();

    fireEvent.keyDown(third, { key: 'Home' });
    expect(first).toHaveFocus();
  });

  test('clicking a tab selects it; the selected tab does not fire onChange', () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    fireEvent.click(screen.getByRole('tab', { name: 'First' }));
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('tab', { name: 'Third' }));
    expect(onChange).toHaveBeenCalledWith('c');
  });
});

describe('ConfirmDialog', () => {
  test('is a named dialog, focuses the first action on open, and Escape cancels once', async () => {
    const onCancel = vi.fn();
    const onConfirm = vi.fn();
    render(<ConfirmDialog open title="Delete product" message="This cannot be undone." confirmLabel="Delete" danger onConfirm={onConfirm} onCancel={onCancel} />);

    const dialog = screen.getByRole('dialog', { name: 'Delete product' });
    expect(modalSpies.showModal).toHaveBeenCalledTimes(1);
    const cancel = screen.getByRole('button', { name: 'Cancel' });
    await waitFor(() => expect(cancel).toHaveFocus());

    fireEvent.keyDown(dialog, { key: 'Escape' });
    fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  test('danger variant styles the confirm action and confirm calls onConfirm', () => {
    const onConfirm = vi.fn();
    render(<ConfirmDialog open title="Remove" message="Remove it?" confirmLabel="Remove" danger onConfirm={onConfirm} onCancel={vi.fn()} />);
    const confirm = screen.getByRole('button', { name: 'Remove' });
    expect(confirm).toHaveAttribute('data-variant', 'danger-primary');
    fireEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  test('non-danger confirm uses the primary variant and the header close button cancels', () => {
    const onCancel = vi.fn();
    render(<ConfirmDialog open title="Publish" message="Publish now?" confirmLabel="Publish" onConfirm={vi.fn()} onCancel={onCancel} />);
    expect(screen.getByRole('button', { name: 'Publish' })).toHaveAttribute('data-variant', 'primary');
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  test('closing after open calls closeModal', () => {
    const { rerender } = render(<ConfirmDialog open title="T" message="M" onConfirm={vi.fn()} onCancel={vi.fn()} />);
    rerender(<ConfirmDialog open={false} title="T" message="M" onConfirm={vi.fn()} onCancel={vi.fn()} />);
    expect(modalSpies.closeModal).toHaveBeenCalledTimes(1);
  });
});

describe('EmptyState', () => {
  test('renders title and body and runs the optional action', () => {
    const onClick = vi.fn();
    render(<EmptyState title="No products yet" body="Import a dataset to start." action={{ label: 'Import data', onClick }} />);
    expect(screen.getByRole('heading', { name: 'No products yet' })).toBeInTheDocument();
    expect(screen.getByText('Import a dataset to start.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Import data' }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  test('omits the action button when no action is given', () => {
    render(<EmptyState title="Nothing here" />);
    expect(screen.getByRole('heading', { name: 'Nothing here' })).toBeInTheDocument();
    expect(screen.queryByRole('button')).toBeNull();
  });
});

describe('DataTable', () => {
  const columns = [{ key: 'name', label: 'Name' }, { key: 'count', label: 'Count', align: 'right' }];

  test('renders a captioned table with scoped header cells', () => {
    render(<DataTable caption="Datasets" columns={columns} rows={[{ name: 'Parts', count: 4 }]} />);
    expect(screen.getByRole('table', { name: 'Datasets' })).toBeInTheDocument();
    screen.getAllByRole('columnheader').forEach((th) => expect(th).toHaveAttribute('scope', 'col'));
    expect(screen.getByRole('cell', { name: 'Parts' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '4' })).toBeInTheDocument();
  });

  test('shows the empty slot spanning all columns when there are no rows', () => {
    render(<DataTable caption="Datasets" columns={columns} rows={[]} empty={<EmptyState title="No datasets" />} />);
    expect(screen.getByRole('heading', { name: 'No datasets' })).toBeInTheDocument();
    expect(screen.getByRole('cell')).toHaveAttribute('colspan', '2');
  });
});

describe('StatusBadge and form fields', () => {
  test('maps status keys to IX variants and falls back to neutral', () => {
    const { rerender } = render(<StatusBadge status="danger" label="Failed" />);
    expect(screen.getByText('Failed')).toHaveAttribute('data-variant', 'alarm');
    rerender(<StatusBadge status="unknown-key" />);
    expect(screen.getByText('neutral')).toHaveAttribute('data-variant', 'neutral');
  });

  test('TextField is labelled, reports changes, and shows error text as an alert', () => {
    const onValueChange = vi.fn();
    const { rerender } = render(<TextField label="Dataset name" value="" onValueChange={onValueChange} helperText="Shown in catalog" />);
    expect(screen.getByLabelText('Dataset name')).toBeInTheDocument();
    expect(screen.getByText('Shown in catalog')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Dataset name'), { target: { value: 'Parts' } });
    expect(onValueChange).toHaveBeenCalledWith('Parts');
    rerender(<TextField label="Dataset name" value="" onValueChange={onValueChange} error="Name is required" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Name is required');
  });

  test('CheckboxField is labelled and links help text', () => {
    const onCheckedChange = vi.fn();
    render(<CheckboxField label="Include archived" checked={false} onCheckedChange={onCheckedChange} helperText="Adds archived rows" />);
    const box = screen.getByRole('checkbox', { name: 'Include archived' });
    fireEvent.click(box);
    expect(onCheckedChange).toHaveBeenCalledWith(true);
    expect(box).toHaveAttribute('aria-describedby');
    expect(screen.getByText('Adds archived rows')).toHaveAttribute('id', box.getAttribute('aria-describedby'));
  });

  test('PrimaryButton forwards onClick and type', () => {
    const onClick = vi.fn();
    render(<PrimaryButton onClick={onClick}>Save</PrimaryButton>);
    const button = screen.getByRole('button', { name: 'Save' });
    expect(button).toHaveAttribute('type', 'button');
    fireEvent.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
