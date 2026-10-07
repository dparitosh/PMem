import { setCredentialProfile, getCredentialProfile } from '../services/serviceAuth';
import React from 'react';
import { vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { TextDecoder } from 'util';
import Chatbot from './Chatbot';

global.TextDecoder = TextDecoder;

// The production component is a Siemens IX web component with a shadow-root
// textarea.  Test the React contract through an accessible stand-in rather
// than relying on JSDOM's incomplete custom-element/shadow-DOM support.
vi.mock('@siemens/ix-react', () => ({
  IxChatInput: ({ value, disabled, textareaLabel, placeholder, onValueChange, onPromptSubmit }) => (
    <div>
      <textarea
        aria-label={textareaLabel}
        disabled={disabled}
        placeholder={placeholder}
        value={value}
        onChange={(event) => onValueChange?.({ detail: event.target.value })}
      />
      <button
        type="button"
        aria-label="Send chat question"
        disabled={disabled}
        onClick={() => onPromptSubmit?.({ detail: value })}
      >Send</button>
    </div>
  ),
}));

const bytes = (value) => new Uint8Array(Array.from(value).map((character) => character.charCodeAt(0)));

test('completed chat shows generation status and the telemetry run', async () => {
  setCredentialProfile('GRAPH_READ_TOKEN', 'read-fixture');
  let sent = false;
  global.fetch = vi.fn((_url, options = {}) => {
    if (options.method !== 'POST') return Promise.resolve({ ok: true, headers: { get: () => null }, json: async () => ({ queries: [] }) });
    return Promise.resolve({ ok: true, status: 200, headers: { get: () => null }, body: { getReader: () => ({ read: async () => {
      if (sent) return { done: true };
      sent = true;
      return { done: false, value: bytes('data: {"response":"Verified evidence","evidence":[],"sources":[],"answerable":true,"run_id":"chat-run-1","generation":{"status":"unavailable"}}\n\ndata: {"done":true}\n\n') };
    } }) } });
  });
  render(<Chatbot />);
  fireEvent.change(screen.getByLabelText('Chat question'), { target: { value: 'Find product' } });
  fireEvent.click(screen.getByLabelText('Send chat question'));
  await screen.findByText('Model generation: unavailable');
  expect(screen.getByText('Agent run: chat-run-1')).toBeInTheDocument();
});

test('Stop cancels generation and does not publish partial text as an answer', async () => {
  const results = vi.fn();
  let rejectRead, sent = false;
  global.fetch = vi.fn((_url, options = {}) => {
    if (options.method !== 'POST') return Promise.resolve({ ok: true, headers: { get: () => null }, json: async () => ({ queries: [] }) });
    options.signal.addEventListener('abort', () => rejectRead?.(new DOMException('Aborted', 'AbortError')));
    return Promise.resolve({ ok: true, status: 200, headers: { get: () => null }, body: { getReader: () => ({ read: async () => {
      if (sent) return new Promise((_resolve, reject) => { rejectRead = reject; });
      sent = true;
      return { done: false, value: bytes('data: {"token":"Partial evidence"}\n\n') };
    } }) } });
  });
  render(<Chatbot setChatResults={results} />);
  fireEvent.change(screen.getByLabelText('Chat question'), { target: { value: 'Find product' } });
  fireEvent.click(screen.getByLabelText('Send chat question'));
  await screen.findByText('Partial evidence');
  fireEvent.click(screen.getByText('Stop response'));
  await waitFor(() => expect(screen.getByLabelText('Send chat question')).not.toBeDisabled());
  expect(screen.getByText('Stopped — partial text is not a completed answer.')).toBeInTheDocument();
  expect(results).not.toHaveBeenCalled();
});

test('scope changes abort old evidence and clear the previous server session', async () => {
  window.sessionStorage.clear();
  const results = jest.fn();
  let rejectRead;
  let tokenSent = false;
  global.fetch = jest.fn((_url, options = {}) => {
    if (options.method !== 'POST') return Promise.resolve({ ok: true, headers: { get: () => null }, json: async () => ({ queries: [] }) });
    options.signal.addEventListener('abort', () => rejectRead?.(new DOMException('Aborted', 'AbortError')));
    return Promise.resolve({ ok: true, status: 200, headers: { get: name => name === 'x-session-id' ? 'old-session' : null },
      body: { getReader: () => ({ read: () => {
        if (!tokenSent) { tokenSent = true; return Promise.resolve({ done: false, value: bytes('data: {"token":"Old scope answer"}\n\n') }); }
        return new Promise((_resolve, reject) => { rejectRead = reject; });
      } }) } });
  });
  const graphData = { nodes: [{ properties: { label: 'Browser text is not evidence' } }] };
  const { rerender } = render(<Chatbot setChatResults={results} ontologyId="first" graphData={graphData} />);
  setCredentialProfile('GRAPH_READ_TOKEN', 'read-key');
  fireEvent.change(screen.getByLabelText('Chat question'), { target: { value: 'Show product' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send chat question' }));
  expect(await screen.findByText('Old scope answer')).toBeInTheDocument();
  const request = global.fetch.mock.calls.find(([, options]) => options.method === 'POST')[1];
  expect(JSON.parse(request.body).graph_context).toEqual({ ontology: 'first', ontology_prefix: '' });
  rerender(<Chatbot setChatResults={results} ontologyId="second" graphData={graphData} />);
  await waitFor(() => expect(request.signal.aborted).toBe(true));
  expect(screen.queryByText('Old scope answer')).not.toBeInTheDocument();
  expect(window.sessionStorage.getItem('depo.sessionId.v1')).toBeNull();
  expect(screen.getByLabelText('Chat question')).not.toBeDisabled();
  expect(results).toHaveBeenLastCalledWith([]);
});

test('a truncated response is not published as a successful answer', async () => {
  window.sessionStorage.clear();
  let sent = false;
  global.fetch = jest.fn((_url, options = {}) => Promise.resolve(options.method !== 'POST'
    ? { ok: true, headers: { get: () => null }, json: async () => ({ queries: [] }) }
    : { ok: true, status: 200, headers: { get: () => null }, body: { getReader: () => ({ read: async () => {
      if (sent) return { done: true };
      sent = true;
      return { done: false, value: bytes('data: {"token":"Partial answer"}\n\n') };
    } }) } }));
  const results = jest.fn();
  render(<Chatbot setChatResults={results} />);
  setCredentialProfile('GRAPH_READ_TOKEN', 'read-key');
  fireEvent.change(screen.getByLabelText('Chat question'), { target: { value: 'Find product' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send chat question' }));
  expect(await screen.findByText(/stream ended before completion/)).toBeInTheDocument();
  expect(results).not.toHaveBeenCalled();
});

test('read-key rotation discards the old credential-owned session', async () => {
  window.sessionStorage.setItem('depo.sessionId.v1', 'old-session');
  setCredentialProfile('GRAPH_READ_TOKEN', 'old-key');
  global.fetch = jest.fn(() => Promise.resolve({ ok: true, headers: { get: () => null }, json: async () => ({ queries: [] }) }));
  const results = jest.fn();
  render(<Chatbot setChatResults={results} />);
  setCredentialProfile('GRAPH_READ_TOKEN', 'new-key');
  fireEvent(window, new Event('depo:credentials-changed'));
  expect(window.sessionStorage.getItem('depo.sessionId.v1')).toBeNull();
  expect(results).toHaveBeenCalledWith([]);
});

test('expired chat session retries retrieval once without its old identifier', async () => {
  window.sessionStorage.clear();
  window.sessionStorage.setItem('depo.sessionId.v1', 'expired-session');
  let submissions = 0;
  global.fetch = jest.fn((_url, options = {}) => {
    if (options.method !== 'POST') return Promise.resolve({ ok: true, headers: { get: () => null }, json: async () => ({ queries: [] }) });
    submissions += 1;
    if (submissions === 1) return Promise.resolve({ ok: false, status: 410, headers: { get: () => null } });
    let sent = false;
    return Promise.resolve({ ok: true, status: 200, headers: { get: () => 'new-session' },
      body: { getReader: () => ({ read: async () => {
        if (sent) return { done: true };
        sent = true;
        return { done: false, value: bytes('data: {"token":"Fresh evidence"}\n\ndata: {"evidence":[],"sources":[],"answerable":false}\n\ndata: {"done":true}\n\n') };
      } }) } });
  });
  render(<Chatbot setChatResults={jest.fn()} graphData={{ nodes: [], links: [] }} searchResults={[]} />);
  setCredentialProfile('GRAPH_READ_TOKEN', 'read-key');
  fireEvent.change(screen.getByLabelText('Chat question'), { target: { value: 'Show product' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send chat question' }));
  await waitFor(() => expect(submissions).toBe(2));
  const requests = global.fetch.mock.calls.filter(([, options]) => options.method === 'POST');
  expect(JSON.parse(requests[0][1].body).session_id).toBe('expired-session');
  expect(JSON.parse(requests[1][1].body).session_id).toBeNull();
  await waitFor(() => expect(window.sessionStorage.getItem('depo.sessionId.v1')).toBe('new-session'));
});

test('keeps chat input locked until the SSE stream completes and clears the server session', async () => {
  window.sessionStorage.clear();
  let releaseDone;
  let readCount = 0;
  const reader = {
    read: jest.fn(() => {
      readCount += 1;
      if (readCount === 1) return Promise.resolve({ done: false, value: bytes('data: {"token":"Hello"}\n\n') });
      if (readCount === 2) return new Promise((resolve) => { releaseDone = resolve; });
      return Promise.resolve({ done: true, value: undefined });
    }),
  };

  global.fetch = jest.fn((url, options = {}) => {
    if (options.method === 'POST') {
      return Promise.resolve({
        ok: true,
        status: 200,
        headers: { get: (name) => name.toLowerCase() === 'x-session-id' ? 'server-session' : null },
        body: { getReader: () => reader },
      });
    }
    return Promise.resolve({
      ok: true,
      status: 200,
      headers: { get: () => 'server-session' },
      json: () => Promise.resolve({ queries: [] }),
    });
  });

  const setChatResults = jest.fn();
  const { rerender } = render(<Chatbot setChatResults={setChatResults} ontologyId="uuid-123" ontologyPrefix="qif" />);
  rerender(<Chatbot setChatResults={setChatResults} ontologyId="uuid-456" ontologyPrefix="qif" />);
  setCredentialProfile('GRAPH_READ_TOKEN', 'read-test-key');

  const input = screen.getByRole('textbox', { name: 'Chat question' });
  fireEvent.change(input, { target: { value: 'Explain this graph' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send chat question' }));

  expect(await screen.findByText('Hello')).toBeInTheDocument();
  const sent = global.fetch.mock.calls.find(([, options]) => options.method === 'POST');
  expect(JSON.parse(sent[1].body).graph_context).toEqual({ ontology: 'uuid-456', ontology_prefix: 'qif' });
  expect(sent[1].headers.Authorization).toBe('Bearer read-test-key');
  expect(JSON.stringify(window.sessionStorage)).not.toContain('read-test-key');
  expect(input).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Send chat question' })).toBeDisabled();

  releaseDone({ done: false, value: bytes('data: {"evidence":[],"sources":[],"answerable":false}\n\ndata: {"done":true}\n\n') });
  await waitFor(() => expect(input).not.toBeDisabled());
  expect(setChatResults).toHaveBeenCalledWith([expect.objectContaining({ response: 'Hello' })]);
  expect(window.sessionStorage.getItem('depo.sessionId.v1')).toBe('server-session');

  fireEvent.click(screen.getByTitle('Clear conversation'));
  expect(window.sessionStorage.getItem('depo.sessionId.v1')).toBeNull();
  expect(setChatResults).toHaveBeenLastCalledWith([]);
});


test('the final evidence response replaces provisional streamed model text', async () => {
  window.sessionStorage.clear();
  let sent = false;
  global.fetch = jest.fn((_url, options = {}) => Promise.resolve(options.method !== 'POST'
    ? { ok: true, headers: { get: () => null }, json: async () => ({ queries: [] }) }
    : { ok: true, status: 200, headers: { get: () => null }, body: { getReader: () => ({ read: async () => {
      if (sent) return { done: true };
      sent = true;
      return { done: false, value: bytes('data: {"token":"Unfinished model suggestion"}\n\ndata: {"response":"Verified graph evidence remains available","evidence":[],"sources":[],"answerable":true}\n\ndata: {"done":true}\n\n') };
    } }) } }));
  const results = jest.fn();
  render(<Chatbot setChatResults={results} graphData={{ nodes: [], links: [] }} searchResults={[]} />);
  setCredentialProfile('GRAPH_READ_TOKEN', 'read-test');
  fireEvent.change(screen.getByLabelText('Chat question'), { target: { value: 'Show product' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send chat question' }));
  await waitFor(() => expect(results).toHaveBeenCalledWith([expect.objectContaining({ response: 'Verified graph evidence remains available' })]));
  expect(screen.queryByText('Unfinished model suggestion')).not.toBeInTheDocument();
});
