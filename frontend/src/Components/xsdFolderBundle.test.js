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
