/*
 * EmptyState: IX <IxEmptyState> for a view with no data.
 *
 * Props:
 *   title   heading text (required)
 *   body    supporting text (optional)
 *   action  optional { label: string, onClick: () => void } rendered as the
 *           IX empty-state action button
 *   icon    optional IX icon name
 */
import React from 'react';
import { IxEmptyState } from '@siemens/ix-react';

export default function EmptyState({ title, body, action, icon }) {
  return (
    <IxEmptyState
      header={title}
      subHeader={body}
      icon={icon}
      action={action?.label}
      onActionClick={() => action?.onClick?.()}
    />
  );
}
