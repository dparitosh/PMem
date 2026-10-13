import React, { useEffect, useRef, useState } from 'react';
import { folderPaths, prepareXsdFolder, combineXsdFiles } from './xsdFolderBundle';

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

export default function XsdDependencies({ files, paths, onChange, onRoot, selectedRoot, selectedSources, disabled }) {
  const [folder, setFolder] = useState([]);
  const [rootPath, setRootPath] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  useEffect(() => {
    generation.current += 1;
    setBusy(false);
    return () => { generation.current += 1; };
  }, [folder, selectedRoot, selectedSources, disabled]);
  const rootMatches = folderPaths(folder).filter(path => path.split('/').at(-1) === selectedRoot?.name);
  useEffect(() => {
    if (!folder.length) { setRootPath(''); return; }
    if (selectedSources?.length) { setRootPath('combined'); setError(''); return; }
    if (!selectedRoot) { setRootPath(''); return; }
    const matches = folderPaths(folder).filter(path => path.split('/').at(-1) === selectedRoot.name);
    setRootPath(matches.length === 1 ? matches[0] : '');
    setError(matches.length === 0
      ? `The selected folder does not contain ${selectedRoot.name}. Select its parent folder containing the root XSD and all companion folders.`
      : matches.length > 1 ? `Multiple copies of ${selectedRoot.name} were found. Select the matching root path below.` : '');
  }, [folder, selectedRoot, selectedSources]);
  return <details open={selectedRoot ? true : undefined}>
    <summary>Additional schema files are needed</summary>
    <fieldset disabled={disabled} style={{ minWidth: 0, margin: '8px 0', padding: 12 }}>
    <legend>Continue this upload</legend>
    {selectedRoot && <p><strong>Selected sources:</strong> {selectedSources?.length ? selectedSources.map(file => file.name).join(', ') : selectedRoot.name}</p>}
    <ol>
      <li>Select the folder containing your original XSD files and their referenced XSD files.</li>
      <li>Choose Resolve companions and retry. The app finds the required files and retries this upload with your saved ontology name and prefix.</li>
    </ol>
    {onRoot && <div>
      <label>Select complete XSD folder<input type="file" webkitdirectory="" multiple disabled={busy} onChange={event => {
        const selected = Array.from(event.target.files || []).filter(file => file.name.toLowerCase().endsWith('.xsd'));
        event.target.value = '';
        setFolder(selected); setError('');
      }} /></label>
      {folder.length > 0 && <>
        {(!selectedRoot || (!selectedSources?.length && rootMatches.length > 1)) && <label>Root schema<select value={rootPath} disabled={busy} onChange={event => setRootPath(event.target.value)}>
          <option value="">Select root XSD</option>
          {(selectedRoot ? rootMatches : folderPaths(folder)).map(path => <option key={path} value={path}>{path}</option>)}
        </select></label>}
        <button type="button" disabled={!rootPath || busy} onClick={async () => {
          const requestGeneration = ++generation.current;
          setBusy(true); setError('');
          try { const bundle = selectedSources?.length ? await combineXsdFiles(selectedSources, folder, true) : await prepareXsdFolder(folder, rootPath); if (requestGeneration !== generation.current) return; onChange(bundle.files, bundle.paths); onRoot(bundle.root, bundle); }
          catch (failure) { if (requestGeneration === generation.current) setError(failure.message); }
          finally { if (requestGeneration === generation.current) setBusy(false); }
        }}>{busy ? 'Checking schema dependencies...' : selectedRoot ? 'Resolve companions and retry' : 'Check folder and add root'}</button>
      </>}
      {error && <p role="alert">{error}</p>}
      <p>Your files stay unchanged. For example, if the source is in QIFApplications and its references are in QIFLibrary, select the parent folder containing both. External references use matching files in your selected folder; they are not downloaded.</p>
    </div>}
    <details><summary>Advanced: select companion files and edit relative paths</summary>
    <p>For schemas that import other XSDs, select the companion files here. They are sent with the root XSD as one schema set. Files stay in this tab and must be selected again after reload.</p>
    <label>Companion XSD files<input type="file" accept=".xsd" multiple disabled={busy} onChange={event => {
      const selected = Array.from(event.target.files || []);
      event.target.value = '';
      onChange(selected, selected.map(file => file.name).join('\n'));
    }} /></label>
    {files.length > 0 && <>
      <p>Selected order: {files.map(file => file.name).join(', ')}</p>
      <label>Companion relative paths (one per selected file)<textarea disabled={busy} value={paths} onChange={event => onChange(files, event.target.value)} style={{ display: 'block', width: '100%', minHeight: 72 }} /></label>
      <button type="button" disabled={busy} onClick={() => onChange([], '')}>Clear companion files</button>
    </>}
    <p>Use manual paths only when folder selection is unavailable. Paths must match the XSD references.</p>
    </details>
  </fieldset></details>;
}
