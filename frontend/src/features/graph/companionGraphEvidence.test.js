import {describe, expect, it} from 'vitest';
import {companionOntologyScope} from './companionGraphEvidence';

describe('Companion ontology scope retention', () => {
  const options = [{value:'bearing-ods',prefix:'bearing'}, {value:'other-ods',prefix:'other'}];
  it('retains the selected registration when projection metadata is absent', () => {
    expect(companionOntologyScope({elementId:'node-1',properties:{name:'Past case'}},'bearing-ods',options))
      .toEqual({ontologyId:'bearing-ods',ontologyPrefix:'bearing'});
  });
  it('preserves an explicitly scoped cross-registration node', () => {
    expect(companionOntologyScope({properties:{ontology_id:'other-ods'}},'bearing-ods',options))
      .toEqual({ontologyId:'other-ods',ontologyPrefix:'other'});
  });
  it('handles top-level graph transport metadata', () => {
    expect(companionOntologyScope({ontology_id:'other-ods',ontology_prefix:'canonical'},'bearing-ods',options))
      .toEqual({ontologyId:'other-ods',ontologyPrefix:'canonical'});
  });
  it('does not silently choose the first registration for an all-sources graph', () => {
    expect(companionOntologyScope({properties:{}},'ALL',options))
      .toEqual({ontologyId:'',ontologyPrefix:''});
  });
});
