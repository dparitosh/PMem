import React from 'react';

export function appendXsdDependencies(form, rootFile, dependencies, pathsText) {
  if (!dependencies.length) return;
  if (!rootFile.name.toLowerCase().endsWith('.xsd')) throw new Error('Companion schemas apply only to an XSD root. Clear companion files before importing other formats.');
  const paths = pathsText.split(/\r?\n/).map(path => path.trim()).filter(Boolean);
  if (paths.length !== dependencies.length || paths.length > 63) throw new Error('Enter one relative path per companion XSD, in the selected file order (maximum 63).');
  const used = new Set([rootFile.name.toLowerCase()]);
  paths.forEach(path => {
    if (!path.toLowerCase().endsWith('.xsd') || /[:\\%?#]/.test(path) || path.startsWith('/') || path.split('/').some(part => !part || part === '.' || part === '..') || used.has(path.toLowerCase())) throw new Error('Companion paths must be distinct relative XSD paths, such as common.xsd or types/part.xsd; do not repeat the root filename.');
    used.add(path.toLowerCase());
  });
  dependencies.forEach(file => form.append('dependencies', file));
  form.append('dependency_paths', JSON.stringify(paths));
}

export default function XsdDependencies({ files, paths, onChange, disabled }) {
  return <fieldset disabled={disabled} style={{ minWidth: 0, margin: '8px 0', padding: 12 }}>
    <legend>Companion XSD files</legend>
    <p>For schemas that import other XSDs, select the companion files here. They are sent with the root XSD as one schema set. Files stay in this tab and must be selected again after reload.</p>
    <label>Companion XSD files<input type="file" accept=".xsd" multiple onChange={event => {
      const selected = Array.from(event.target.files || []);
      onChange(selected, selected.map(file => file.name).join('\n'));
    }} /></label>
    {files.length > 0 && <>
      <p>Selected order: {files.map(file => file.name).join(', ')}</p>
      <label>Companion relative paths (one per selected file)<textarea value={paths} onChange={event => onChange(files, event.target.value)} style={{ display: 'block', width: '100%', minHeight: 72 }} /></label>
      <button type="button" onClick={() => onChange([], '')}>Clear companion files</button>
    </>}
    <p>For the bundled bom.xsd, select the bundled Edition 2 common.xsd with relative path common.xsd. Choose OWL generation. External schemas are not downloaded automatically.</p>
  </fieldset>;
}
