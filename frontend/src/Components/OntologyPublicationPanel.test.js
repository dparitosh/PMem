import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { apiClient } from '../services/apiClient';
import OntologyPublicationPanel from './OntologyPublicationPanel';
afterEach(() => vi.restoreAllMocks());

test('hidden tabs pause publication polling and automatic refresh skips metadata', async () => {
  const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
  const get = vi.spyOn(apiClient, 'get').mockImplementation(url => Promise.resolve({ data: url.endsWith('/publication')
    ? { status: 'publishing', job_id: 'poll-job' } : { lifecycle_status: 'approved' } }));
  const view = render(<OntologyPublicationPanel ontologyId="poll-demo" />);
  await screen.findByText(/Job: poll-job/);
  vi.useFakeTimers();
  try {
    act(() => { hidden.mockReturnValue(true); document.dispatchEvent(new Event('visibilitychange')); });
    await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
    expect(get).toHaveBeenCalledTimes(2);
    act(() => { hidden.mockReturnValue(false); document.dispatchEvent(new Event('visibilitychange')); });
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(get).toHaveBeenCalledTimes(3);
    expect(get.mock.calls[2][0]).toContain('/publication');
  } finally { view.unmount(); vi.useRealTimers(); }
});
test('a failed refresh of an idle publisher disables stale write controls until verification succeeds', async () => {
  let reject = false;
  vi.spyOn(apiClient, 'get').mockImplementation(url => reject
    ? Promise.reject({ response: { status: 503, data: { detail: 'Graph unavailable' } } })
    : Promise.resolve({ data: url.endsWith('/publication') ? { status: 'not_published' } : { lifecycle_status: 'approved' } }));
  const view = render(<OntologyPublicationPanel ontologyId="idle-refresh" />);
  await screen.findByText('Publish to Neo4j');
  fireEvent.change(screen.getByPlaceholderText('Your approval identity'), { target: { value: 'reviewer' } });
  await waitFor(() => expect(screen.getByText('Publish to Neo4j')).toBeEnabled());
  reject = true;
  fireEvent.click(screen.getByText('Verify publication'));
  await screen.findByRole('alert');
  expect(screen.getByText('Publish to Neo4j')).toBeDisabled();
  reject = false;
  fireEvent.click(screen.getByText('Verify publication'));
  await waitFor(() => expect(screen.getByText('Publish to Neo4j')).toBeEnabled());
  view.unmount();
});
test('failed status refresh retains the background job and disables duplicate publication', async () => {
  let reject = false;
  vi.spyOn(apiClient, 'get').mockImplementation(url => reject
    ? Promise.reject({ response: { status: 403, data: { detail: 'Invalid or revoked GRAPH_READ_TOKEN' }, headers: { 'x-request-id': 'customer-status-42' } } })
    : Promise.resolve({ data: url.endsWith('/publication') ? { status: 'publishing', phase: 'running', job_id: 'retained-customer-job' } : { lifecycle_status: 'approved' } }));
  const view = render(<OntologyPublicationPanel ontologyId="customer-status" />);
  await screen.findByText(/Job: retained-customer-job/);
  reject = true;
  fireEvent.click(screen.getByText('Verify publication'));
  await screen.findByText(/Last confirmed job details are retained/);
  expect(screen.getByText(/Job: retained-customer-job/)).toBeInTheDocument();
  expect(screen.getByText(/Request ID: customer-status-42/)).toBeInTheDocument();
  expect(screen.getByText('Publish to Neo4j')).toBeDisabled();
  view.unmount();
});
test('registration stays separate from publication and approval is required', async () => {
  vi.spyOn(apiClient, 'get').mockImplementation(url => Promise.resolve({ data: url.endsWith('/publication') ? { status: 'not_published' } : { lifecycle_status: 'draft' } }));
  const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: {} });
  render(<OntologyPublicationPanel ontologyId="demo" />);
  await screen.findByText('Submit for review');
  expect(screen.queryByText('Publish to Neo4j')).toBeNull();
  expect(post).not.toHaveBeenCalled();
});
test('an approved ontology publishes only on an explicit user action', async () => {
  vi.spyOn(apiClient, 'get').mockImplementation(url => Promise.resolve({ data: url.endsWith('/publication') ? { status: 'not_published' } : { lifecycle_status: 'approved' } }));
  const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: {} });
  render(<OntologyPublicationPanel ontologyId="demo" />);
  const button = await screen.findByText('Publish to Neo4j');
  expect(button).toBeDisabled();
  fireEvent.change(screen.getByPlaceholderText('Your approval identity'), { target: { value: 'reviewer' } });
  fireEvent.click(button);
  expect(post).toHaveBeenCalledWith(expect.stringContaining('/demo/publish'), expect.objectContaining({ approved_by: 'reviewer' }), expect.objectContaining({ signal: expect.any(AbortSignal) }));
  await waitFor(() => expect(screen.getByText('Publish to Neo4j')).toBeEnabled());
});

test('malformed lifecycle data cannot render approval controls', async () => {
  vi.spyOn(apiClient, 'get').mockImplementation(url => Promise.resolve({data:url.endsWith('/publication') ? {status:'not_published'} : {lifecycle_status:{approved:true}}}));
  render(<OntologyPublicationPanel ontologyId="bad" />);
  await screen.findByRole('alert');
  expect(screen.queryByText('Publish to Neo4j')).toBeNull();
});

test('changing credentials clears the pending approver identity', async () => {
  vi.spyOn(apiClient, 'get').mockImplementation(url => Promise.resolve({data:url.endsWith('/publication') ? {status:'not_published'} : {lifecycle_status:'approved'}}));
  render(<OntologyPublicationPanel ontologyId="demo" />);
  await screen.findByText('Publish to Neo4j');
  fireEvent.change(screen.getByPlaceholderText('Your approval identity'), {target:{value:'previous-user'}});
  fireEvent(window, new Event('depo:credentials-changed'));
  expect(screen.getByPlaceholderText('Your approval identity')).toHaveValue('');
});


test('shows publication in progress until the request settles', async () => {
  vi.spyOn(apiClient, 'get').mockImplementation(url => Promise.resolve({data: url.endsWith('/publication') ? {status:'not_published'} : {lifecycle_status:'approved'}}));
  let finish;
  vi.spyOn(apiClient, 'post').mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  render(<OntologyPublicationPanel ontologyId="progress-demo" />);
  const button = await screen.findByText('Publish to Neo4j');
  fireEvent.change(screen.getByPlaceholderText('Your approval identity'), {target:{value:'reviewer'}});
  fireEvent.click(button);
  await screen.findByText(/Submitting background publication/);
  expect(button).toBeDisabled();
  finish({data:{}});
  await waitFor(() => expect(button).toBeEnabled());
});


test('workflow links to the selected ontology and records the correct review origin', async () => {
  vi.spyOn(apiClient, 'get').mockImplementation(url => Promise.resolve({data: url.endsWith('/publication') ? {status:'not_published'} : {lifecycle_status:'draft'}}));
  const post = vi.spyOn(apiClient, 'post').mockResolvedValue({data:{}});
  render(<OntologyPublicationPanel ontologyId="schema set&v2" fromWorkflow />);
  const link = screen.getByRole('link', {name:'View in Ontology Junction'});
  expect(link).toHaveAttribute('href', '#/ontology?target=schema%20set%26v2');
  expect(link).toHaveAttribute('target', '_blank');
  const submit = await screen.findByText('Submit for review');
  fireEvent.change(screen.getByPlaceholderText('Your approval identity'), {target:{value:'reviewer'}});
  fireEvent.click(submit);
  expect(post).toHaveBeenCalledWith(expect.stringContaining('/transition'), expect.objectContaining({reason:'Reviewed from import workflow'}), expect.any(Object));
  await waitFor(() => expect(submit).toBeEnabled());
});


test('long publication displays elapsed time and diagnostic guidance', async () => {
  vi.spyOn(apiClient, 'get').mockImplementation(url => Promise.resolve({data:url.endsWith('/publication') ? {status:'not_published'} : {lifecycle_status:'approved'}}));
  vi.spyOn(apiClient, 'post').mockImplementation(() => new Promise(() => {}));
  const view = render(<OntologyPublicationPanel ontologyId="elapsed-demo" />);
  const button = await screen.findByText('Publish to Neo4j');
  vi.useFakeTimers();
  try {
    fireEvent.change(screen.getByPlaceholderText('Your approval identity'), {target:{value:'reviewer'}});
    fireEvent.click(button);
    act(() => vi.advanceTimersByTime(61000));
    expect(screen.getByText(/Elapsed: 61s/)).toBeInTheDocument();
    expect(screen.getByText(/inspect ontology.err.log and graph.err.log/)).toBeInTheDocument();
  } finally { view.unmount(); vi.useRealTimers(); }
});


test('uncertain publication disables writes until verification proves the publisher is idle', async () => {
  let status = 'unverified';
  vi.spyOn(apiClient, 'get').mockImplementation(url => Promise.resolve({data:url.endsWith('/publication') ? {status} : {lifecycle_status:'approved'}}));
  const post = vi.spyOn(apiClient, 'post');
  render(<OntologyPublicationPanel ontologyId="recovery-demo" />);
  const button = await screen.findByText('Publish to Neo4j');
  fireEvent.change(screen.getByPlaceholderText('Your approval identity'), {target:{value:'reviewer'}});
  expect(button).toBeDisabled();
  expect(screen.getByText(/Publication outcome is uncertain/)).toBeInTheDocument();
  status = 'not_published';
  fireEvent.click(screen.getByText('Verify publication'));
  await waitFor(() => expect(screen.getByText('Publish to Neo4j')).toBeEnabled());
  expect(post).not.toHaveBeenCalled();
});


test('reopened panel header shows server publishing state', async () => {
  vi.spyOn(apiClient, 'get').mockImplementation(url => Promise.resolve({data:url.endsWith('/publication') ? {status:'publishing'} : {lifecycle_status:'approved'}}));
  const view = render(<OntologyPublicationPanel ontologyId="active-demo" />);
  await screen.findByText('Publishing...');
  expect(screen.getByText(/in the background. You can leave this page/)).toBeInTheDocument();
  expect(screen.getByText('Publish to Neo4j')).toBeDisabled();
  view.unmount();
});

test('background job remains visible and disables duplicate publication after submission', async () => {
  let queued = false;
  vi.spyOn(apiClient, 'get').mockImplementation(url => Promise.resolve({ data: url.endsWith('/publication')
    ? queued ? { status: 'publishing', phase: 'queued', job_id: 'retained-job' } : { status: 'not_published' }
    : { lifecycle_status: 'approved' } }));
  const post = vi.spyOn(apiClient, 'post').mockImplementation(async () => {
    queued = true; return { status: 202, data: { job_id: 'retained-job', status: 'queued' } };
  });
  const view = render(<OntologyPublicationPanel ontologyId="background-demo" />);
  await screen.findByText('Publish to Neo4j');
  fireEvent.change(screen.getByPlaceholderText('Your approval identity'), { target: { value: 'reviewer' } });
  fireEvent.click(screen.getByText('Publish to Neo4j'));
  await screen.findByText(/Job: retained-job/);
  expect(post).toHaveBeenCalledWith(expect.stringContaining('/publish?background=true'), expect.any(Object), expect.objectContaining({ timeout: 30000 }));
  expect(screen.getByText('Publish to Neo4j')).toBeDisabled();
  expect(screen.getByText('Cancel queued publication')).toBeInTheDocument();
  view.unmount();
});

test('committed staging progress is visible without claiming publication succeeded', async () => {
  vi.spyOn(apiClient, 'get').mockImplementation(url => Promise.resolve({ data: url.endsWith('/publication')
    ? { status: 'publishing', progress: { resource_offset: 1000, resources_expected: 2402 } }
    : { lifecycle_status: 'approved' } }));
  const view = render(<OntologyPublicationPanel ontologyId="staged-demo" />);
  await screen.findByText(/Staged resources: 1000 \/ 2402/);
  expect(screen.getByText('Publish to Neo4j')).toBeDisabled();
  expect(screen.queryByText('Published')).toBeNull();
  view.unmount();
});
