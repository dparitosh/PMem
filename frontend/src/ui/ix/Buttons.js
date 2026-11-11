/*
 * Buttons: thin wrappers over IX <IxButton> with fixed variants.
 *
 * Props (all three):
 *   children, onClick, type ('button' default | 'submit'), disabled, icon (IX icon name)
 *   Any other prop is forwarded to IxButton. Ref forwards to the IxButton host.
 *
 * Exports:
 *   PrimaryButton    variant="primary"        main action on a view or dialog
 *   SecondaryButton  variant="secondary"      alternative or cancel action
 *   DangerButton     variant="danger-primary" destructive confirm action
 */
import React, { forwardRef } from 'react';
import { IxButton } from '@siemens/ix-react';

function makeButton(variant) {
  return forwardRef(function IxVariantButton({ children, type = 'button', ...rest }, ref) {
    return <IxButton ref={ref} variant={variant} type={type} {...rest}>{children}</IxButton>;
  });
}

export const PrimaryButton = makeButton('primary');
export const SecondaryButton = makeButton('secondary');
export const DangerButton = makeButton('danger-primary');
