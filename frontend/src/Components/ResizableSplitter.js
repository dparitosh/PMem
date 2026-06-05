import { useState, useRef, useEffect } from 'react';

/**
 * ResizableSplitter
 * 3-state toggle: Up (tabs full) | Middle (split) | Down (graph full)
 * Also supports manual drag to any position.
 * splitState: 'up' | 'middle' | 'down'
 */
const ResizableSplitter = ({ onResize, graphHeight, splitState, onClickUp, onClickDown }) => {
  const [isDragging, setIsDragging] = useState(false);
  const [isHovering, setIsHovering] = useState(false);
  const splitterRef = useRef(null);
  const dragStartRef = useRef(null);

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e) => {
      e.preventDefault();
      const container = document.querySelector('.cloud-main');
      if (!container) return;
      const rect = container.getBoundingClientRect();
      const newHeight = e.clientY - rect.top - 5;
      const minHeight = 50;
      const maxHeight = rect.height - 60;
      if (newHeight >= minHeight && newHeight <= maxHeight) {
        onResize(newHeight);
      }
    };

    const handleMouseUp = () => {
      setIsDragging(false);
    };

    document.addEventListener('mousemove', handleMouseMove, true);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove, true);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging, onResize]);

  const handleMouseDown = (e) => {
    e.preventDefault();
    dragStartRef.current = { y: e.clientY, time: Date.now() };
    setIsDragging(true);
  };

  const handleMouseUp = (e) => {
    if (dragStartRef.current) {
      const dy = Math.abs(e.clientY - dragStartRef.current.y);
      const dt = Date.now() - dragStartRef.current.time;
      // If it was a click (not a drag), ignore — use buttons instead
      if (dy < 5 && dt < 300) {
        setIsDragging(false);
      }
    }
    dragStartRef.current = null;
  };

  return (
    <div
      ref={splitterRef}
      className="resizable-splitter"
      onMouseDown={handleMouseDown}
      onMouseUp={handleMouseUp}
      onMouseEnter={() => setIsHovering(true)}
      onMouseLeave={() => setIsHovering(false)}
      title="Drag to resize manually"
      style={{
        height: '18px',
        backgroundColor: isHovering || isDragging ? '#004B87' : '#e9ecef',
        cursor: isDragging ? 'row-resize' : 'row-resize',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '4px',
        userSelect: 'none',
        transition: isDragging ? 'none' : 'background-color 0.15s ease',
        flexShrink: 0,
        zIndex: 100,
        borderTop: '1px solid #d0d5db',
        borderBottom: '1px solid #d0d5db',
      }}
    >
      {/* Up button - collapse graph, expand tabs */}
      <button
        onClick={(e) => { e.stopPropagation(); onClickUp(); }}
        onMouseDown={(e) => e.stopPropagation()}
        title="Collapse graph (tabs full screen)"
        style={{
          background: splitState === 'up' ? '#004B87' : 'transparent',
          color: splitState === 'up' ? '#fff' : (isHovering || isDragging ? '#fff' : '#555'),
          border: 'none',
          fontSize: '11px',
          lineHeight: 1,
          cursor: 'pointer',
          padding: '1px 6px',
          borderRadius: '3px',
          fontWeight: 700,
        }}
      >▲</button>

      {/* Middle grip / drag handle */}
      <span
        style={{
          width: '36px',
          height: '3px',
          backgroundColor: isHovering || isDragging ? '#fff' : '#aaa',
          borderRadius: '2px',
          pointerEvents: 'none',
        }}
      />

      {/* Down button - expand graph, collapse tabs */}
      <button
        onClick={(e) => { e.stopPropagation(); onClickDown(); }}
        onMouseDown={(e) => e.stopPropagation()}
        title="Expand graph (collapse tabs)"
        style={{
          background: splitState === 'down' ? '#004B87' : 'transparent',
          color: splitState === 'down' ? '#fff' : (isHovering || isDragging ? '#fff' : '#555'),
          border: 'none',
          fontSize: '11px',
          lineHeight: 1,
          cursor: 'pointer',
          padding: '1px 6px',
          borderRadius: '3px',
          fontWeight: 700,
        }}
      >▼</button>
    </div>
  );
};

export default ResizableSplitter;
