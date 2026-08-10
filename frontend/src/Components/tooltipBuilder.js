// Shared tooltip header builder to avoid duplicated HTML across components
export function buildTooltipHeader(nodeType, closeBtnHtml = '', accentColor = '#1F3D63') {
  return `
    <div class="dt-tooltip-header" style="position:relative; background: linear-gradient(135deg, ${accentColor} 0%, #486581 100%); color: white; padding: 10px 14px; margin: -10px -12px 10px -12px; font-weight: 700; border-radius: 10px 10px 0 0;">
      <div class="dt-tooltip-handle" style="display: flex; align-items: center; gap: 8px;">
        <i class="fas fa-tag" style="font-size: 16px;"></i>
        <span>${nodeType}</span>
      </div>
      ${closeBtnHtml}
    </div>
  `;
}
