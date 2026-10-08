import React, { useRef } from 'react';

export default function WorkspaceTabs({ label, tabs, value, onChange }) {
  const buttons = useRef([]);
  const navigate = (event, index) => {
    let next;
    if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
    else if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = tabs.length - 1;
    else return;
    event.preventDefault();
    onChange(tabs[next].id);
    buttons.current[next]?.focus();
  };
  return <div role="tablist" aria-label={label} style={{display:'flex',gap:6,flexWrap:'wrap',marginBottom:8}}>
    {tabs.map((tab,index) => <button key={tab.id} ref={node => {buttons.current[index]=node;}} type="button" role="tab"
      aria-selected={value===tab.id} tabIndex={value===tab.id?0:-1} onKeyDown={event=>navigate(event,index)}
      onClick={()=>onChange(tab.id)} className="depo-button depo-button--secondary"
      style={value===tab.id?{background:'var(--ui-primary, #007a99)',color:'#fff'}:undefined}>{tab.label}</button>)}
  </div>;
}
