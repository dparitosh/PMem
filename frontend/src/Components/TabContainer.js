import React from 'react';

/**
 * TabContainer - Keeps all tab content in DOM to preserve state
 * Shows/hides with CSS instead of mounting/unmounting
 */
const TabContainer = ({ isActive, children, tabId }) => {
  return (
    <div
      style={{
        display: isActive ? 'block' : 'none',
        position: 'absolute',
        inset: 0,
        overflow: 'hidden',
        ...(isActive && {
          animation: 'fadeIn 0.3s ease-in',
        }),
      }}
      data-tab-id={tabId}
    >
      {children}
    </div>
  );
};

export default TabContainer;
