/**
 * Smart Tooltip Positioning Utility
 * Ensures tooltips stay within viewport and positioned consistently to the right side
 */

export const calculateTooltipPosition = (mouseX, mouseY, tooltipEl, containerEl) => {
  if (!tooltipEl || !containerEl) return { x: mouseX + 15, y: mouseY };

  const tooltip = tooltipEl.getBoundingClientRect();
  
  const tooltipWidth = tooltip.width || 280; // Default width
  const tooltipHeight = tooltip.height || 120; // Default height
  const padding = 12; // Padding from viewport edge
  const offset = 15; // Offset from cursor

  // Viewport boundaries
  const viewport = {
    left: padding,
    right: window.innerWidth - padding,
    top: padding,
    bottom: window.innerHeight - padding,
  };

  // Default position: to the right of cursor
  let finalX = mouseX + offset;
  let finalY = mouseY - (tooltipHeight / 2); // Vertically center with cursor

  // Horizontal: If tooltip would go off right edge, position to the left instead
  if (finalX + tooltipWidth > viewport.right) {
    finalX = mouseX - tooltipWidth - offset;
  }
  
  // Keep within left boundary
  if (finalX < viewport.left) {
    finalX = viewport.left;
  }

  // Vertical: Keep within top/bottom boundaries
  if (finalY < viewport.top) {
    finalY = viewport.top;
  }
  if (finalY + tooltipHeight > viewport.bottom) {
    finalY = viewport.bottom - tooltipHeight;
  }

  return { x: finalX, y: finalY };
};

/**
 * Apply smart positioning to tooltip element
 */
export const applySmartTooltipPosition = (tooltipEl, mouseX, mouseY, containerEl) => {
  if (!tooltipEl) return;

  // Set temporary position for measurement
  tooltipEl.style.position = 'fixed';
  tooltipEl.style.zIndex = '9999';
  tooltipEl.style.opacity = '1';
  tooltipEl.style.pointerEvents = 'auto';

  // Calculate optimal position
  const { x, y } = calculateTooltipPosition(mouseX, mouseY, tooltipEl, containerEl);

  // Apply position
  tooltipEl.style.left = x + 'px';
  tooltipEl.style.top = y + 'px';
};

/**
 * Ensure tooltip is above other elements (z-index management)
 */
export const bringTooltipToFront = (tooltipEl) => {
  if (tooltipEl) {
    tooltipEl.style.zIndex = '10000'; // Above D3 elements
  }
};

/**
 * Hide tooltip safely
 */
export const hideTooltip = (tooltipEl) => {
  if (tooltipEl) {
    tooltipEl.style.opacity = '0';
    tooltipEl.style.pointerEvents = 'none';
    tooltipEl.style.zIndex = 'auto';
  }
};
