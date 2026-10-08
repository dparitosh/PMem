// SSE events end at a blank line; network chunks are not event boundaries.
export function createChatFrameParser(onEvent) {
  let pending = '';
  let data = [];
  const line = value => {
    if (!value) {
      if (data.length) {
        const payload = data.join('\n');
        data = [];
        let event;
        try { event = JSON.parse(payload); }
        catch { throw new Error('Chat stream returned an invalid JSON event.'); }
        if (!event || typeof event !== 'object' || Array.isArray(event)) throw new Error('Chat stream returned an invalid event.');
        onEvent(event);
      }
    } else if (value.startsWith('data:')) {
      data.push(value.slice(5).replace(/^ /, ''));
    }
  };
  return {
    push(text) {
      pending += text;
      if (pending.length + data.join('\n').length > 1024 * 1024) throw new Error('Chat response frame exceeds the permitted size.');
      let end;
      while ((end = pending.indexOf('\n')) >= 0) {
        line(pending.slice(0, end).replace(/\r$/, ''));
        pending = pending.slice(end + 1);
      }
    },
    finish() {
      if (pending || data.length) throw new Error('Chat stream ended with an incomplete event.');
    },
  };
}
