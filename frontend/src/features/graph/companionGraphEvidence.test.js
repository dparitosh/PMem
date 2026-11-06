import {describe, it, expect} from 'vitest';
import {companionEvidenceIds, focusCompanionEvidence} from './companionGraphEvidence';
describe('Companion graph evidence', () => {
  const evidence=[{evidence_type:'business_answer',rows:[{subject_id:'part',requirement_id:'req'}]}];
  it('uses typed identities, not generated prose or citation IDs',()=>{
    expect(companionEvidenceIds(evidence,'part')).toEqual(['part','req']);
    expect(companionEvidenceIds([{resource_id:'part',description:'req'}],'part')).toEqual([]);
  });
  it('rejects evidence for another selected subject',()=>expect(companionEvidenceIds(evidence,'other')).toEqual([]));
  it('does not invent an edge or mutate the complete slice',()=>{
    const data={nodes:[{elementId:'part'},{elementId:'req'},{elementId:'cad'}],links:[{source:{elementId:'part'},target:'req'},{source:'part',target:'cad'}]};
    const focused=focusCompanionEvidence(data,['part','req']);
    expect(focused.nodes).toHaveLength(2);expect(focused.links).toHaveLength(1);expect(data.nodes).toHaveLength(3);
    expect(focusCompanionEvidence({...data,links:[]},['part','req']).links).toEqual([]);
    expect(focusCompanionEvidence(data,null)).toBe(data);
  });
});
