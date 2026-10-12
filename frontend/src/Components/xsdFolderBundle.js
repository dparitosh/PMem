const XSD = 'http://www.w3.org/2001/XMLSchema';
const readText = file => typeof file.text === 'function' ? file.text() : new Promise((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve(reader.result);
  reader.onerror = () => reject(new Error(`Cannot read schema: ${file.name}`));
  reader.readAsText(file);
});
export async function combineXsdFiles(selected, available = selected, preflight = false) {
  if (selected.length > 63 || selected.reduce((total, file) => total + file.size, 0) > 25 * 1024 * 1024) throw new Error('Selected schema set exceeds 63 source files or 25 MiB.');
  const paths = folderPaths(available);
  const document = new DOMParser().parseFromString(`<xs:schema xmlns:xs="${XSD}"/>`, 'application/xml');
  const ordered = [...selected].sort((a, b) => a.name.localeCompare(b.name, 'en'));
  let namespace;
  for (const original of ordered) {
    const candidates = available.map((file, index) => ({ file, path: paths[index] }));
    const originalPath = original.webkitRelativePath ? folderPaths([original])[0] : null;
    const matches = originalPath ? candidates.filter(item => item.path === originalPath) : candidates.filter(item => item.file === original || item.file.name === original.name);
    if (matches.length !== 1) throw new Error(`Select a folder containing exactly one copy of ${original.name}.`);
    const { file, path } = matches[0];
    const text = await readText(file);
    if (/<!DOCTYPE|<!ENTITY/i.test(text)) throw new Error('DTD/entities are not permitted in schemas.');
    const xml = new DOMParser().parseFromString(text, 'application/xml');
    if (xml.querySelector('parsererror') || xml.documentElement.namespaceURI !== XSD || xml.documentElement.localName !== 'schema') throw new Error(`Invalid XML Schema: ${file.name}`);
    const ns = xml.documentElement.getAttribute('targetNamespace') || '';
    if (namespace === undefined) { namespace = ns; if (ns) document.documentElement.setAttribute('targetNamespace', ns); }
    const reference = document.createElementNS(XSD, ns === namespace ? 'xs:include' : 'xs:import');
    if (ns !== namespace && ns) reference.setAttribute('namespace', ns);
    reference.setAttribute('schemaLocation', path);
    document.documentElement.appendChild(reference);
  }
  let name = 'uploaded-schema-set.xsd';
  while (paths.some(path => path.toLowerCase() === name.toLowerCase())) name = '_' + name;
  const root = new File([new XMLSerializer().serializeToString(document)], name, { type: 'application/xml' });
  const bundle = preflight ? await prepareXsdFolder([...available, root], name) : { root, files: selected, paths: selected.map(file => paths[available.indexOf(file)]).join('\n') };
  return { ...bundle, sources: selected };
}
function resolvePath(base, location) {
  if (/[:\\%?#]/.test(location) || location.startsWith('/')) throw new Error('Schema references must be local relative paths.');
  const parts = base.split('/').slice(0, -1);
  for (const part of location.split('/')) {
    if (!part || part === '.') continue;
    if (part === '..') { if (!parts.length) throw new Error('Schema dependency escapes the selected folder.'); parts.pop(); }
    else parts.push(part);
  }
  return parts.join('/');
}
export function folderPaths(files) {
  return files.map(file => (file.webkitRelativePath || file.name).split('/').slice(file.webkitRelativePath ? 1 : 0).join('/'));
}
export async function prepareXsdFolder(files, rootPath) {
  const paths = folderPaths(files);
  const source = new Map(paths.map((path, index) => [path, files[index]]));
  if (source.size !== files.length || !source.has(rootPath)) throw new Error('Select a unique root XSD within the folder.');
  const pending = [rootPath], documents = new Map();
  let size = 0;
  while (pending.length) {
    const path = pending.pop();
    if (documents.has(path)) continue;
    const file = source.get(path);
    if (!file || !path.toLowerCase().endsWith('.xsd')) throw new Error(`Missing companion XSD: ${path}`);
    size += file.size;
    if (documents.size >= 64 || size > 25 * 1024 * 1024) throw new Error('Schema set exceeds 64 files or 25 MiB.');
    const text = await readText(file);
    if (/<!DOCTYPE|<!ENTITY/i.test(text)) throw new Error('DTD/entities are not permitted in schemas.');
    const xml = new DOMParser().parseFromString(text, 'application/xml');
    if (xml.querySelector('parsererror') || xml.documentElement.namespaceURI !== XSD || xml.documentElement.localName !== 'schema') throw new Error(`Invalid XML Schema: ${path}`);
    const refs = Array.from(xml.documentElement.children).filter(node => node.namespaceURI === XSD && ['include', 'import', 'redefine'].includes(node.localName) && node.hasAttribute('schemaLocation')).map(node => {
      const dependency = resolvePath(path, node.getAttribute('schemaLocation'));
      pending.push(dependency);
      return { node, dependency };
    });
    documents.set(path, { xml, refs, file });
  }
  const rootName = source.get(rootPath).name;
  const target = path => path === rootPath ? rootName : path;
  const targets = Array.from(documents.keys()).map(target);
  if (new Set(targets.map(path => path.toLowerCase())).size !== targets.length) throw new Error('Root and companion paths collide.');
  const prepared = new Map();
  for (const [path, { xml, refs, file }] of documents) {
    const base = target(path).split('/').slice(0, -1);
    for (const { node, dependency } of refs) {
      const dest = target(dependency).split('/');
      let common = 0;
      while (common < base.length && common < dest.length && base[common] === dest[common]) common++;
      node.setAttribute('schemaLocation', [...base.slice(common).map(() => '..'), ...dest.slice(common)].join('/'));
    }
    prepared.set(target(path), new File([new XMLSerializer().serializeToString(xml)], file.name, { type: 'application/xml' }));
  }
  const companionPaths = targets.filter(path => path !== rootName).sort();
  return { root: prepared.get(rootName), files: companionPaths.map(path => prepared.get(path)), paths: companionPaths.join('\n') };
}
