import { prepareXsdFolder, combineXsdFiles } from './xsdFolderBundle';
function file(path, body) {
  const text = `<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">${body}</xs:schema>`;
  const value = new File([text], path.split('/').at(-1));
  Object.defineProperty(value, 'webkitRelativePath', { value: `schemas/${path}` });
  value.text = async () => text;
  return value;
}
test('folder closure preserves sibling dependencies and excludes unrelated schemas', async () => {
  const result = await prepareXsdFolder([
    file('Apps/root.xsd', '<xs:include schemaLocation="../Library/part.xsd"/>'),
    file('Library/part.xsd', '<xs:include schemaLocation="../Apps/root.xsd"/>'),
    file('unused.xsd', ''),
  ], 'Apps/root.xsd');
  expect(result.root.name).toBe('root.xsd');
  expect(result.paths).toBe('Library/part.xsd');
  expect(result.files).toHaveLength(1);
  const rootXml = await new Promise(resolve => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.readAsText(result.root); });
  expect(rootXml).toContain('schemaLocation="Library/part.xsd"');
});
test('missing dependency fails preflight', async () => {
  await expect(prepareXsdFolder([file('Apps/root.xsd', '<xs:include schemaLocation="../Library/missing.xsd"/>')], 'Apps/root.xsd')).rejects.toThrow('Missing companion');
});
test('combined schema identity is independent of selection order', async () => {
  const a = file('a.xsd', ''), b = file('b.xsd', '');
  const first = await combineXsdFiles([a, b]);
  const second = await combineXsdFiles([b, a]);
  const read = blob => new Promise(resolve => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.readAsText(blob); });
  expect(await read(first.root)).toBe(await read(second.root));
});
test('multiple direct selections resolve sibling companions from an optional folder', async () => {
  const roots = [file('Apps/one.xsd', '<xs:include schemaLocation="../Library/part.xsd"/>'), file('Apps/two.xsd', '')];
  const bundle = await combineXsdFiles(roots, [...roots, file('Library/part.xsd', '')], true);
  expect(bundle.root.name).toBe('uploaded-schema-set.xsd');
  expect(bundle.paths.split('\n')).toEqual(['Apps/one.xsd', 'Apps/two.xsd', 'Library/part.xsd']);
  expect(bundle.sources).toEqual(roots);
});
test.each(['../../outside.xsd', 'https://example.test/a.xsd'])('unsafe reference %s fails preflight', async location => {
  await expect(prepareXsdFolder([file('Apps/root.xsd', `<xs:include schemaLocation="${location}"/>`)], 'Apps/root.xsd')).rejects.toThrow();
});

test('external import resolves a supplied local companion without altering originals', async () => {
  const root = file('root.xsd', '<xs:import namespace="urn:signature" schemaLocation="https://example.test/xmldsig-core-schema.xsd"/>');
  const companion = file('Library/xmldsig-core-schema.xsd', '');
  companion.text = async () => '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:signature"/>';
  const result = await prepareXsdFolder([root, companion], 'root.xsd');
  expect(result.paths).toBe('Library/xmldsig-core-schema.xsd');
  expect(await root.text()).toContain('https://example.test');
  const read = blob => new Promise(resolve => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.readAsText(blob); });
  expect(await read(result.root)).toContain('schemaLocation="Library/xmldsig-core-schema.xsd"');
});

test('external companion with wrong namespace is rejected', async () => {
  await expect(prepareXsdFolder([file('root.xsd', '<xs:import namespace="urn:signature" schemaLocation="https://example.test/sig.xsd"/>'), file('sig.xsd', '')], 'root.xsd')).rejects.toThrow('namespace');
});

test('reselected folder files retain the correct paths without preflight', async () => {
  const replacement = file('Library/part.xsd', '');
  const original = new File([await replacement.text()], 'part.xsd');
  original.text = replacement.text;
  const bundle = await combineXsdFiles([original], [replacement]);
  expect(bundle.files).toEqual([replacement]);
  expect(bundle.paths).toBe('Library/part.xsd');
});

test('recovery rejects a changed source with the same filename', async () => {
  await expect(combineXsdFiles([file('part.xsd', '')], [file('part.xsd', '<xs:element name="changed"/>')], true)).rejects.toThrow('differs from the original');
});

test('oversized external companion is rejected before reading it', async () => {
  const companion = file('sig.xsd', '');
  Object.defineProperty(companion, 'size', { value: 26 * 1024 * 1024 });
  companion.text = () => { throw new Error('must not read'); };
  await expect(prepareXsdFolder([file('root.xsd', '<xs:import schemaLocation="https://example.test/sig.xsd"/>'), companion], 'root.xsd')).rejects.toThrow('25 MiB');
});

test('empty sources and case-colliding paths fail before upload', async () => {
  await expect(combineXsdFiles([])).rejects.toThrow('at least one');
  await expect(combineXsdFiles([file('part.xsd', ''), file('PART.xsd', '')])).rejects.toThrow('unique');
});
