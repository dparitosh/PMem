// Shared tooltip header builder to avoid duplicated HTML across components
export function buildTooltipHeader(nodeType, closeBtnHtml = '') {
  return `
    <div style="position:relative; background: linear-gradient(135deg, #0066B3 0%, #28A745 100%); color: white; padding: 8px 12px; margin: -8px -8px 8px -8px; font-weight: bold; border-radius: 4px 4px 0 0;">
      <div style="display: flex; align-items: center; gap: 8px;">
        <i class="fas fa-tag" style="font-size: 16px;"></i>
        <span>${nodeType}</span>
      </div>
      ${closeBtnHtml}
    </div>
  `;
}
