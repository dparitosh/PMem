import React from 'react';

export default function Palette({ items = [], onCreate }) {
  return <aside className="model-palette" aria-label="Element palette">{items.map((item) => <button key={item} type="button" onClick={() => onCreate?.(item)}>{item}</button>)}</aside>;
}
