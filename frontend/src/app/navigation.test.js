import { navigationItems, navigationGroups, normalizePage, pageLabel } from './navigation';

test('every navigation destination uses a distinct icon',()=>{
 expect(new Set(navigationItems.map(item=>item.icon)).size).toBe(navigationItems.length);
});

test('normalizes aliases and rejects unknown or malformed pages', () => {
  expect(normalizePage(' metadata-registry ')).toBe('registry');
  expect(normalizePage('REQIF')).toBe('requirements');
  expect(normalizePage('removed-page')).toBe('graph');
  expect(normalizePage(null)).toBe('graph');
});

test('uses a safe label fallback', () => {
  expect(pageLabel('reports')).toBe('Memory insights');
  expect(pageLabel('unknown')).toBe('Graph Explorer');
});


test('business navigation follows the requested order and owns each destination once',()=>{
 expect(navigationGroups.map(group=>group.label)).toEqual(['Decision intelligence','Ingest','Ontology Junction','Model Explore','Administer']);
 const groups=Object.fromEntries(navigationGroups.map(group=>[group.label,group.items.map(item=>item.id)]));
 expect(groups['Decision intelligence']).toContain('whereused');
 expect(groups['Administer']).toContain('change-control');
 expect(groups['Ontology Junction']).toEqual(['ontology','registry','catalog','data-products','data-quality']);
 expect(groups['Model Explore']).toEqual(['graph','modeling','requirements','qif','code-audit']);
 const ids=navigationGroups.flatMap(group=>group.items.map(item=>item.id));
 expect(new Set(ids).size).toBe(ids.length);
 expect([...ids,'home'].sort()).toEqual(navigationItems.filter(item=>!item.hidden).map(item=>item.id).sort());
 expect(pageLabel('ontology')).toBe('Ontology & Vocabularies');
});
