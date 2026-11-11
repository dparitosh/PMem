/*
 * StatusBadge: IX <IxBadge> that maps a status key to an IX colour variant.
 *
 * Props:
 *   status  'success' | 'warning' | 'danger' | 'info' | 'neutral' (default 'neutral';
 *           unknown keys fall back to neutral)
 *   label   visible text (defaults to the status key). Always provide a text label:
 *           colour alone must not carry meaning.
 *
 * Status colours come from tokens.css (--ui-status-*) and the IX badge variant.
 */
import React from 'react';
import { IxBadge } from '@siemens/ix-react';
import './tokens.css';

export const STATUS_VARIANTS = {
  success: 'success',
  warning: 'warning',
  danger: 'alarm',
  info: 'info',
  neutral: 'neutral',
};

export default function StatusBadge({ status = 'neutral', label }) {
  const key = Object.prototype.hasOwnProperty.call(STATUS_VARIANTS, status) ? status : 'neutral';
  return <IxBadge variant={STATUS_VARIANTS[key]} label={label ?? key} className={`ui-status-badge ui-status-badge--${key}`} />;
}
