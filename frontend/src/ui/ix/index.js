/*
 * Public entry point for the shared Siemens IX UI layer (src/ui/ix).
 * Import from '../ui/ix' (or the relevant path) rather than the individual files.
 *
 * Components:
 *   IxTabsBar({ tabs, active, onChange, ariaLabel, idPrefix? })
 *   PrimaryButton | SecondaryButton | DangerButton (forwardRef, IxButton props)
 *   TextField({ label, value, onValueChange, ... }) | SelectField({ label, value, onValueChange, options, ... })
 *   CheckboxField({ label, checked, onCheckedChange, ... })
 *   DataTable({ caption, columns, rows, rowKey?, renderCell?, empty? })
 *   StatusBadge({ status: 'success'|'warning'|'danger'|'info'|'neutral', label? })
 *   EmptyState({ title, body?, action?: { label, onClick }, icon? })
 *   ConfirmDialog({ open, title, message, confirmLabel?, cancelLabel?, danger?, onConfirm, onCancel })
 * Styles: tokens.css (imported by each component; also importable directly).
 */
import './tokens.css';

export { default as IxTabsBar } from './IxTabsBar';
export { PrimaryButton, SecondaryButton, DangerButton } from './Buttons';
export { TextField, SelectField, CheckboxField } from './FormFields';
export { default as DataTable } from './DataTable';
export { default as StatusBadge } from './StatusBadge';
export { default as EmptyState } from './EmptyState';
export { default as ConfirmDialog } from './ConfirmDialog';
