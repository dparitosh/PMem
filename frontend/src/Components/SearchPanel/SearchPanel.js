import React, { useState } from 'react';

export default function SearchPanel({ onSearch }) {
  const [query, setQuery] = useState('');
  return <form className="search-panel" onSubmit={(event) => { event.preventDefault(); onSearch?.(query); }}><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search label, property, relationship" /><button type="submit">Search</button></form>;
}
