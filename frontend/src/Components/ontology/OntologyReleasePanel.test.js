import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { apiClient } from '../../services/apiClient';
import OntologyReleasePanel from './OntologyReleasePanel';

afterEach(() => vi.restoreAllMocks());
const empty = id => ({ data: { ontology_id: id, release: null, history: [] } });

test('declaration is separate from approval and duplicate clicks send one write', async () => {
  vi.spyOn(apiClient, 'get').mockResolvedValue(empty('model'));
  let complete;
  const post = vi.spyOn(apiClient, 'post').mockImplementation(() => new Promise(resolve => { complete = resolve; }));
  const view = render(<OntologyReleasePanel ontologyId="model" actor="reviewer" />);
  await screen.findByText(/No release version is declared/);
  fireEvent.change(screen.getByLabelText(/Ontology family/), { target: { value: 'AP242' } });
  fireEvent.change(screen.getByLabelText(/Version \(for example/), { target: { value: '1.0.0' } });
  fireEvent.change(screen.getByLabelText('Change notes'), { target: { value: 'Initial model' } });
  const button = screen.getByRole('button', { name: 'Declare immutable release' });
  fireEvent.click(button); fireEvent.click(button);
  expect(post).toHaveBeenCalledTimes(1);
  expect(post.mock.calls[0][1]).toMatchObject({ family_id: 'AP242', version: '1.0.0', predecessor_id: null, approved_by: 'reviewer' });
  expect(post.mock.calls[0][0]).toMatch(/\/model\/releases$/);
  view.unmount(); complete({ data: { ontology_id: 'model', version: '1.0.0' } });
});

test('switching ontology cancels stale history', async () => {
  let old;
  vi.spyOn(apiClient, 'get').mockImplementation(url => url.includes('/old/') ? new Promise(resolve => { old = resolve; }) : Promise.resolve(empty('new')));
  const view = render(<OntologyReleasePanel ontologyId="old" actor="reviewer" />);
  view.rerender(<OntologyReleasePanel ontologyId="new" actor="reviewer" />);
  await screen.findByText(/No release version is declared/);
  old({ data: { ontology_id: 'old', release: { family_id: 'OLD', version: '1.0.0' }, history: [] } });
  await waitFor(() => expect(screen.queryByText(/OLD/)).not.toBeInTheDocument());
});

test('changed artifact shows recovery warning and no declaration form', async () => {
  vi.spyOn(apiClient, 'get').mockResolvedValue({ data: { ontology_id: 'model', release: { family_id: 'AP242', version: '1.0.0', change_kind: 'initial' }, history: [], artifact_matches_release: false } });
  render(<OntologyReleasePanel ontologyId="model" actor="reviewer" />);
  expect(await screen.findByRole('alert')).toHaveTextContent(/does not match its release/);
  expect(screen.queryByRole('button', { name: 'Declare immutable release' })).not.toBeInTheDocument();
});

test('unrelated response is rejected', async () => {
  vi.spyOn(apiClient, 'get').mockResolvedValue(empty('other'));
  render(<OntologyReleasePanel ontologyId="model" actor="reviewer" />);
  expect(await screen.findByRole('alert')).toHaveTextContent(/does not match/);
  expect(screen.queryByRole('button', { name: 'Declare immutable release' })).not.toBeInTheDocument();
});
