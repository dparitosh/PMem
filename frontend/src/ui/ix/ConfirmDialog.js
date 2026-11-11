/*
 * ConfirmDialog: IX <IxModal> confirmation with role="dialog".
 *
 * Props:
 *   open           boolean. true calls showModal(); false closes it.
 *   title          dialog title (required; names the dialog)
 *   message        body text or node
 *   confirmLabel   default 'Confirm'
 *   cancelLabel    default 'Cancel'
 *   danger         true uses DangerButton for the confirm action
 *   onConfirm      () => void
 *   onCancel       () => void; called on Cancel, header close, Escape or backdrop
 *                  dismissal. Called at most once per open.
 *
 * Focus: when opened, focus moves to the first action (Cancel), so Enter does not
 * confirm a destructive action by accident. Escape closes via onCancel.
 */
import React, { useEffect, useId, useRef } from 'react';
import { IxModal, IxModalContent, IxModalFooter, IxModalHeader } from '@siemens/ix-react';
import { DangerButton, PrimaryButton, SecondaryButton } from './Buttons';
import './tokens.css';

export default function ConfirmDialog({
  open, title, message, confirmLabel = 'Confirm', cancelLabel = 'Cancel',
  danger = false, onConfirm, onCancel,
}) {
  const modalRef = useRef(null);
  const cancelRef = useRef(null);
  const cancelledRef = useRef(false);
  const shownRef = useRef(false);
  const titleId = useId();
  const messageId = `${titleId}-message`;

  const cancel = () => {
    if (cancelledRef.current) return;
    cancelledRef.current = true;
    onCancel?.();
  };

  useEffect(() => {
    const modal = modalRef.current;
    if (!modal) return undefined;
    if (!open) {
      if (shownRef.current) modal.closeModal?.('closed');
      shownRef.current = false;
      return undefined;
    }
    cancelledRef.current = false;
    shownRef.current = true;
    let active = true;
    Promise.resolve(modal.showModal?.()).then(() => {
      if (active) cancelRef.current?.focus?.();
    });
    return () => { active = false; };
  }, [open]);

  const Confirm = danger ? DangerButton : PrimaryButton;
  return (
    <IxModal
      ref={modalRef}
      role="dialog"
      aria-labelledby={titleId}
      aria-describedby={messageId}
      size="480"
      closeOnBackdropClick={false}
      onDialogDismiss={cancel}
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          event.preventDefault();
          cancel();
        }
      }}
    >
      <IxModalHeader onCloseClick={cancel}>
        <span id={titleId}>{title}</span>
      </IxModalHeader>
      <IxModalContent>
        <div id={messageId}>{message}</div>
      </IxModalContent>
      <IxModalFooter>
        <SecondaryButton ref={cancelRef} onClick={cancel}>{cancelLabel}</SecondaryButton>
        <Confirm onClick={() => onConfirm?.()}>{confirmLabel}</Confirm>
      </IxModalFooter>
    </IxModal>
  );
}
