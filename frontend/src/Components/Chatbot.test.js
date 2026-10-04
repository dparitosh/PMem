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
        return { done: false, value: bytes('data: {"token":"Fresh evidence"}\n\ndata: {"done":true}\n\n') };
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
  render(<Chatbot setChatResults={setChatResults} graphData={{ nodes: [], links: [] }} searchResults={[]} />);
  setCredentialProfile('GRAPH_READ_TOKEN', 'read-test-key');

  const input = screen.getByRole('textbox', { name: 'Chat question' });
  fireEvent.change(input, { target: { value: 'Explain this graph' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send chat question' }));

  expect(await screen.findByText('Hello')).toBeInTheDocument();
  const sent = global.fetch.mock.calls.find(([, options]) => options.method === 'POST');
  expect(sent[1].headers.Authorization).toBe('Bearer read-test-key');
  expect(JSON.stringify(window.sessionStorage)).not.toContain('read-test-key');
  expect(input).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Send chat question' })).toBeDisabled();

  releaseDone({ done: false, value: bytes('data: {"done":true}\n\n') });
  await waitFor(() => expect(input).not.toBeDisabled());
  expect(setChatResults).toHaveBeenCalledWith([expect.objectContaining({ response: 'Hello' })]);
  expect(window.sessionStorage.getItem('depo.sessionId.v1')).toBe('server-session');

  fireEvent.click(screen.getByTitle('Clear conversation'));
  expect(window.sessionStorage.getItem('depo.sessionId.v1')).toBeNull();
  expect(setChatResults).toHaveBeenLastCalledWith([]);
});
