import { expect, test } from 'vitest';
import { createChatFrameParser } from './chatStreamFrames';

test('parses chunked CRLF and multiline data while ignoring heartbeat comments', () => {
  const events = [];
  const parser = createChatFrameParser(event => events.push(event));
  parser.push(': keepalive\r\n\r\ndata: {"token":\r');
  parser.push('\ndata: "hello"}\r\n\r\ndata: {"done":true}\n\n');
  parser.finish();
  expect(events).toEqual([{ token: 'hello' }, { done: true }]);
});

test('rejects malformed and unterminated events', () => {
  expect(() => createChatFrameParser(() => {}).push('data: broken\n\n')).toThrow('invalid JSON');
  const parser = createChatFrameParser(() => {});
  parser.push('data: {"done":true}\n');
  expect(() => parser.finish()).toThrow('incomplete event');
});

test('limits individual frames rather than an aggregate network chunk', () => {
  const events = [];
  const parser = createChatFrameParser(event => events.push(event));
  const frame = `data: ${JSON.stringify({ token: 'a'.repeat(600000) })}\n\n`;
  parser.push(frame + frame);
  parser.finish();
  expect(events).toHaveLength(2);
});

test('rejects oversized frames split across chunks or data lines', () => {
  const parser = createChatFrameParser(() => {});
  parser.push('data: ' + 'a'.repeat(600000) + '\n');
  expect(() => parser.push('data: ' + 'a'.repeat(600000) + '\n\n')).toThrow('permitted size');
  expect(() => createChatFrameParser(() => {}).push('data: ' + 'a'.repeat(1100000))).toThrow('permitted size');
});
