/*
 * jsdom test double for @siemens/ix-react. Stencil custom elements do not
 * initialise in JSDOM (the real module exhausts the worker heap), so tests use:
 *
 *   vi.mock('@siemens/ix-react', () => import('<path to>/ui/ix/ixReact.mock.js'));
 *
 * Components render plain DOM. IX-only props are stripped, and the value and
 * change props used by the wrappers (onValueChange, onCheckedChange,
 * onTabChange, onDialogDismiss, onActionClick) are mapped to DOM events.
 * Modal open/close calls are recorded in `modalSpies`.
 * Test-only: not imported by application code.
 */
import React, { forwardRef, useImperativeHandle } from 'react';
import { vi } from 'vitest';

export const modalSpies = { showModal: vi.fn(() => Promise.resolve()), closeModal: vi.fn(), dismissModal: vi.fn() };

const DOM_EVENTS = new Set(['onClick', 'onKeyDown', 'onKeyUp', 'onFocus', 'onBlur', 'onMouseDown']);
const IX_ONLY = new Set([
  'tabKey', 'variant', 'label', 'helperText', 'invalidText', 'header', 'subHeader', 'action', 'icon',
  'size', 'closeOnBackdropClick', 'activeTabKey', 'keyboardNavigation', 'layout', 'readonly', 'required',
  'ariaLabelMoreTabs', 'ariaLabelEmptyStateIcon', 'placement', 'rounded', 'small', 'onCloseClick',
]);

function domProps(props) {
  const out = {};
  for (const [key, value] of Object.entries(props)) {
    if (IX_ONLY.has(key)) continue;
    if (key.startsWith('on') && !DOM_EVENTS.has(key)) continue;
    out[key] = value;
  }
  return out;
}

const passthrough = (tag) => forwardRef(function IxMock({ children, ...props }, ref) {
  return React.createElement(tag, { ...domProps(props), ref }, children);
});

export const IxTabs = passthrough('div');
export const IxTabItem = passthrough('div');
export const IxCheckbox = forwardRef(function IxCheckbox({ label, checked, onCheckedChange, ...props }, ref) {
  return (
    <label>
      <input ref={ref} type="checkbox" checked={!!checked} disabled={props.disabled}
        aria-describedby={props['aria-describedby']} aria-invalid={props['aria-invalid']} name={props.name}
        onChange={(event) => onCheckedChange?.({ detail: event.target.checked })} />
      {label}
    </label>
  );
});

export const IxButton = forwardRef(function IxButton({ children, variant, ...props }, ref) {
  return <button ref={ref} data-variant={variant} {...domProps(props)}>{children}</button>;
});

export const IxBadge = ({ label, variant, className }) => <span data-variant={variant} className={className}>{label}</span>;

export const IxInput = forwardRef(function IxInput({ label, value, onValueChange, helperText, invalidText, ...props }, ref) {
  return (
    <div>
      <label>{label}<input ref={ref} aria-invalid={props['aria-invalid']} name={props.name} value={value ?? ''}
        onChange={(event) => onValueChange?.({ detail: event.target.value })} /></label>
      {invalidText ? <span role="alert">{invalidText}</span> : helperText ? <span>{helperText}</span> : null}
    </div>
  );
});

export const IxSelect = forwardRef(function IxSelect({ label, value, onValueChange, helperText, invalidText, children, ...props }, ref) {
  return (
    <div>
      <label>{label}<select ref={ref} aria-invalid={props['aria-invalid']} name={props.name} value={value ?? ''}
        onChange={(event) => onValueChange?.({ detail: event.target.value })}>{children}</select></label>
      {invalidText ? <span role="alert">{invalidText}</span> : helperText ? <span>{helperText}</span> : null}
    </div>
  );
});

export const IxSelectItem = ({ value, label }) => <option value={value}>{label}</option>;

export const IxEmptyState = ({ header, subHeader, action, onActionClick }) => (
  <div>
    <h2>{header}</h2>
    {subHeader ? <p>{subHeader}</p> : null}
    {action ? <button type="button" onClick={() => onActionClick?.({ detail: undefined })}>{action}</button> : null}
  </div>
);

export const IxModal = forwardRef(function IxModal({ children, ...props }, ref) {
  useImperativeHandle(ref, () => modalSpies, []);
  return <div {...domProps(props)}>{children}</div>;
});

export const IxModalHeader = ({ children, onCloseClick }) => (
  <div>{children}<button type="button" aria-label="Close" onClick={onCloseClick}>x</button></div>
);
export const IxModalContent = ({ children }) => <div>{children}</div>;
export const IxModalFooter = ({ children }) => <div>{children}</div>;
export const IxIcon = ({ name }) => <span data-icon={name} />;
