import { describe, expect, it } from 'vitest';
import { hierarchyEdge } from './taxonomyHierarchy';

describe('taxonomy predicate direction', () => {
  for (const mapping_type of ['narrower', 'parentOf']) {
    it(`reverses ${mapping_type} to child-to-parent`, () => {
      const source = { mapping_type, source_term: 'parent', target_term: 'child' };
      expect(hierarchyEdge(source)).toMatchObject({ source_term: 'child', target_term: 'parent' });
      expect(source.source_term).toBe('parent');
    });
  }
  for (const mapping_type of ['broader', 'subClassOf']) {
    it(`retains ${mapping_type} child-to-parent direction`, () => {
      expect(hierarchyEdge({ mapping_type, source_term: 'child', target_term: 'parent' })).toMatchObject({ source_term: 'child', target_term: 'parent' });
    });
  }
});
