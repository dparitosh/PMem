// SSE events end at a blank line; network chunks are not event boundaries.
export function createChatFrameParser(onEvent) {
  let pending = '';
  let data = [];
  let dataSize = 0;
  const limit = 1024 * 1024;
  const line = value => {
    if (!value) {
      if (data.length) {
        const payload = data.join('\n');
        data = [];
        dataSize = 0;
        let event;
        try { event = JSON.parse(payload); }
        catch { throw new Error('Chat stream returned an invalid JSON event.'); }
        if (!event || typeof event !== 'object' || Array.isArray(event)) throw new Error('Chat stream returned an invalid event.');
        onEvent(event);
      }
    } else if (value.startsWith('data:')) {
      const part = value.slice(5).replace(/^ /, '');
      dataSize += part.length + (data.length ? 1 : 0);
      if (dataSize > limit) throw new Error('Chat response frame exceeds the permitted size.');
      data.push(part);
    }
  };
  return {
    push(text) {
      pending += text;
      let end;
      while ((end = pending.indexOf('\n')) >= 0) {
        if (end + dataSize > limit) throw new Error('Chat response frame exceeds the permitted size.');
        line(pending.slice(0, end).replace(/\r$/, ''));
        pending = pending.slice(end + 1);
      }
      if (pending.length + dataSize > limit) throw new Error('Chat response frame exceeds the permitted size.');
    },
    finish() {
      if (pending || data.length) throw new Error('Chat stream ended with an incomplete event.');
    },
  };
}
