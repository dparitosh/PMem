/*
 * Form fields: IX form controls with label, help text and error text.
 *
 * TextField
 *   props: label (required), value, onValueChange(string), type, name, placeholder,
 *          helperText, error, required, disabled, readOnly
 * SelectField
 *   props: label (required), value, onValueChange(string), options [{ value, label }],
 *          name, helperText, error, required, disabled
 * CheckboxField
 *   props: label (required), checked, onCheckedChange(boolean), name,
 *          helperText, error, disabled
 *
 * helperText is shown under the control; error replaces it visually and is
 * exposed with role="alert". Errors set aria-invalid on the control.
 * TextField and SelectField use the IX helperText/invalidText props; CheckboxField
 * renders its own text (IX checkbox has no text slot for it) and links it with
 * aria-describedby.
 */
import React, { useId } from 'react';
import { IxCheckbox, IxInput, IxSelect, IxSelectItem } from '@siemens/ix-react';
import './tokens.css';

export function TextField({
  label, value, onValueChange, type = 'text', name, placeholder,
  helperText, error, required = false, disabled = false, readOnly = false,
}) {
  return (
    <IxInput
      label={label}
      type={type}
      name={name}
      placeholder={placeholder}
      value={value ?? ''}
      onValueChange={(event) => onValueChange?.(event.detail)}
      helperText={error ? undefined : helperText}
      invalidText={error}
      required={required}
      disabled={disabled}
      readonly={readOnly}
      aria-invalid={error ? 'true' : undefined}
    />
  );
}

export function SelectField({
  label, value, onValueChange, options = [], name,
  helperText, error, required = false, disabled = false,
}) {
  return (
    <IxSelect
      label={label}
      name={name}
      value={value ?? ''}
      onValueChange={(event) => onValueChange?.(event.detail)}
      helperText={error ? undefined : helperText}
      invalidText={error}
      required={required}
      disabled={disabled}
      aria-invalid={error ? 'true' : undefined}
    >
      {options.map((option) => (
        <IxSelectItem key={option.value} value={option.value} label={option.label} />
      ))}
    </IxSelect>
  );
}

export function CheckboxField({
  label, checked = false, onCheckedChange, name,
  helperText, error, disabled = false,
}) {
  const id = useId();
  const helpId = `${id}-help`;
  return (
    <div className="ui-checkbox-field">
      <IxCheckbox
        label={label}
        name={name}
        checked={checked}
        disabled={disabled}
        onCheckedChange={(event) => onCheckedChange?.(event.detail)}
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={helperText || error ? helpId : undefined}
      />
      {error ? <div id={helpId} role="alert" className="ui-form-error">{error}</div>
        : helperText ? <div id={helpId} className="ui-form-help">{helperText}</div> : null}
    </div>
  );
}
