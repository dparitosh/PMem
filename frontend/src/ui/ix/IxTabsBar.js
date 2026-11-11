/*
 * IxTabsBar: horizontal tab strip built on IX <IxTabs>/<IxTabItem>.
 *
 * Props:
 *   tabs      [{ id: string, label: string }]
 *   active    id of the selected tab
 *   onChange  (id) => void, called on click and on arrow/Home/End keys
 *   ariaLabel accessible name for the tablist (required)
 *   idPrefix  optional; sets tab id and aria-controls to `${idPrefix}-tab-${id}`
 *             and `${idPrefix}-panel-${id}` for matching tab panels
 *
 * Keyboard: ArrowLeft/ArrowRight wrap, Home/End jump to the ends. Focus follows
 * selection. IX keyboardNavigation is "manual" so this component owns the keys.
 */
import React, { forwardRef, useRef } from 'react';
import { IxTabItem, IxTabs } from '@siemens/ix-react';
import './tokens.css';

const TabItem = forwardRef(function TabItem({ tab, selected, idPrefix, ...rest }, ref) {
  return (
    <IxTabItem
      ref={ref}
      tabKey={tab.id}
      role="tab"
      id={idPrefix ? `${idPrefix}-tab-${tab.id}` : undefined}
      aria-controls={idPrefix ? `${idPrefix}-panel-${tab.id}` : undefined}
      aria-selected={selected ? 'true' : 'false'}
      tabIndex={selected ? 0 : -1}
      {...rest}
    >
      {tab.label}
    </IxTabItem>
  );
});

export default function IxTabsBar({ tabs, active, onChange, ariaLabel, idPrefix }) {
  const itemRefs = useRef([]);
  const onKeyDown = (event) => {
    const count = tabs.length;
    if (!count) return;
    const index = Math.max(0, tabs.findIndex((tab) => tab.id === active));
    let next;
    if (event.key === 'ArrowRight') next = (index + 1) % count;
    else if (event.key === 'ArrowLeft') next = (index + count - 1) % count;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = count - 1;
    else return;
    event.preventDefault();
    onChange(tabs[next].id);
    itemRefs.current[next]?.focus?.();
  };
  return (
    <IxTabs
      className="ui-tabs-bar"
      role="tablist"
      aria-label={ariaLabel}
      activeTabKey={active}
      keyboardNavigation="manual"
      layout="auto"
      onTabChange={(event) => {
        if (event.detail && event.detail !== active) onChange(event.detail);
      }}
      onKeyDown={onKeyDown}
    >
      {tabs.map((tab, index) => (
        <TabItem
          key={tab.id}
          ref={(node) => { itemRefs.current[index] = node; }}
          tab={tab}
          selected={tab.id === active}
          idPrefix={idPrefix}
          onClick={() => { if (tab.id !== active) onChange(tab.id); }}
        />
      ))}
    </IxTabs>
  );
}
