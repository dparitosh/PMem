import DOMPurify from 'dompurify';

export function formatChatMarkdown(text) {
  if (!text) return '';

  const escapeHtml = (value) => String(value || '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  const inline = (value) => escapeHtml(value)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>');
  const lines = String(text).replace(/\r\n/g, '\n').split('\n');
  let html = '';
  let paragraph = [];
  let listType = null;
  let listItems = [];
  let tableRows = [];

  const flushParagraph = () => {
    if (paragraph.length) {
      html += `<p class="chat-paragraph">${inline(paragraph.join(' '))}</p>`;
      paragraph = [];
    }
  };
  const flushList = () => {
    if (!listItems.length) return;
    html += `<${listType} class="chat-list">${listItems.map(item => `<li>${inline(item)}</li>`).join('')}</${listType}>`;
    listItems = [];
    listType = null;
  };
  const flushTable = () => {
    if (!tableRows.length) return;
    const rows = tableRows.filter(row => !/^\s*\|?\s*:?-{3,}/.test(row));
    if (rows.length) {
      const cells = rows.map(row => row.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(cell => cell.trim()));
      const header = cells[0];
      html += `<div class="chat-table-wrap"><table class="chat-table"><thead><tr>${header.map(cell => `<th>${inline(cell)}</th>`).join('')}</tr></thead><tbody>${cells.slice(1).map(row => `<tr>${row.map(cell => `<td>${inline(cell)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
    }
    tableRows = [];
  };

  lines.forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) { flushParagraph(); flushList(); flushTable(); return; }
    if (/^\|.*\|$/.test(line)) { flushParagraph(); flushList(); tableRows.push(line); return; }
    flushTable();
    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      flushParagraph(); flushList();
      const level = heading[1].length;
      html += `<h${level} class="chat-heading chat-heading-${level}">${inline(heading[2])}</h${level}>`;
      return;
    }
    if (/^---+$/.test(line)) { flushParagraph(); flushList(); html += '<hr class="chat-rule" />'; return; }
    // Models frequently emit Unicode bullets instead of Markdown's ASCII markers.
    // Treat them as the same list so each item remains a separate bullet in the UI.
    const bullet = line.match(/^[-*•◦▪]\s+(.+)$/);
    const numbered = line.match(/^\d+[.)]\s+(.+)$/);
    if (bullet || numbered) {
      flushParagraph();
      const nextType = numbered ? 'ol' : 'ul';
      if (listType && listType !== nextType) flushList();
      listType = nextType;
      listItems.push((bullet || numbered)[1]);
      return;
    }
    const fact = line.match(/^([A-Za-z][A-Za-z0-9 _/-]{1,36}):\s+(.+)$/);
    if (fact && !line.includes('://')) {
      flushParagraph(); flushList();
      html += `<div class="chat-fact"><span>${inline(fact[1])}</span><strong>${inline(fact[2])}</strong></div>`;
      return;
    }
    paragraph.push(line);
  });
  flushParagraph(); flushList(); flushTable();

  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['p', 'strong', 'em', 'code', 'h1', 'h2', 'h3', 'ul', 'li', 'ol', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'hr', 'div', 'span'],
    ALLOWED_ATTR: ['class'],
    KEEP_CONTENT: true,
  });
}
