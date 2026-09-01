import React from 'react';
import { IxBadge, IxButton, IxIcon } from '@siemens/ix-react';

// IX components use Shadow DOM. Vitest's JSDOM does not implement the custom
// element lifecycle fully, so these small adapters preserve accessible native
// controls in tests while the browser always receives the real IX components.
const isTestEnvironment = import.meta.env.MODE === 'test';

export function SiemensButton({ variant: _variant, icon: _icon, iconRight: _iconRight, ...props }) {
  if (isTestEnvironment) return <button {...props} />;
  return <IxButton variant={_variant} icon={_icon} iconRight={_iconRight} {...props} />;
}

export function SiemensBadge({ label, type: _type, variant: _variant, ...props }) {
  if (isTestEnvironment) return <span {...props}>{label}</span>;
  return <IxBadge label={label} type={_type} variant={_variant} {...props} />;
}

export function SiemensNavigationIcon({ name, ...props }) {
  if (isTestEnvironment) return <span aria-hidden="true" {...props} />;
  return <IxIcon name={name} {...props} />;
}
