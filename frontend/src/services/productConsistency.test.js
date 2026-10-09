import { describe, it, expect, vi } from 'vitest';
import { loadProductCollection } from './productCollection';
import { productDraftFromRun, productDraftFromOntology, publicationFromDraft } from './analyticsProductDraft';

describe('shared product collection and evidence boundary', () => {
  it('accepts RDF evidence while preserving selected ontology lineage and review requirements', () => {
    const original = { contract: 'ontology-evidence-data-product-v1', product_kind: 'ontology-evidence', quality_status: 'requires_review', artifacts: [{ artifact_id: 'retained-rdf' }] };
    const draft = productDraftFromOntology({ ontology_id: 'spqm_registered', prefix: 'spqm', artifact_id: 'retained-rdf', data_product_draft: original });
    const payload = publicationFromDraft(draft, {product_id:'rdf',name:'RDF',version:'1.0.0',owner:'owner',steward:'steward',classification:'internal',approved_by:'approver',asset_id:'approved-release',release_version:'1.0.0'}, 'rdf-request');
    expect(payload.product_kind).toBe('ontology-evidence');
    expect(payload.quality_status).toBe('requires_review');
    expect(payload.ontologies[0].ontology_id).toBe('spqm_registered');
    expect(payload.sources[0].ontology_id).toBe('spqm_registered');
    expect(payload.semantic_releases[0].asset_id).toBe('approved-release');
    expect(original).not.toHaveProperty('ontologies');
  });
  it('keeps XML load readiness and source lineage in a retained pipeline draft', () => {
    const retained = { product_kind: 'pipeline-evidence', artifacts: [{artifact_id:'receipt'}], analytics_readiness:'structural-data-loaded; business-metrics-not-defined', sources:[{schema:'depo_analytics_test'}] };
    expect(productDraftFromRun({run_id:'xml-load',status:'completed',output_manifest:{data_product_draft:retained}})).toEqual(retained);
  });
  it('preserves the declared total and flags partial retrieval', async () => {
    const result = await loadProductCollection(vi.fn().mockResolvedValue({data:{total:3,products:[{product_id:'a',version:'1'}],next_offset:null}}));
    expect(result.total).toBe(3);
    expect(result.rows).toHaveLength(1);
    expect(result.warning).toMatch(/declared total/);
  });
  it('deduplicates overlapping version pages instead of inflating displayed counts', async () => {
    const request = vi.fn().mockResolvedValueOnce({data:{products:[{product_id:'a',version:'1'}],total:2,next_offset:1}})
      .mockResolvedValueOnce({data:{products:[{product_id:'a',version:'1'},{product_id:'b',version:'1'}],total:2,next_offset:null}});
    const result = await loadProductCollection(request);
    expect(result.rows).toHaveLength(2);
    expect(result.warning).toMatch(/Duplicate/);
  });
  it('uses retained artifacts from a completed run without certifying quality', () => {
    const draft = productDraftFromRun({run_id:'run-1',status:'completed',job_type:'profile',output_manifest:{partition_artifacts:{accepted:'evidence-1',rejected:'evidence-2'}}});
    expect(draft.artifacts).toEqual([{artifact_id:'evidence-1'},{artifact_id:'evidence-2'}]);
    expect(draft.quality_status).toBe('requires_review');
    const payload = publicationFromDraft(draft, {product_id:'profile',name:'Profile',version:'1.0.0',owner:'owner',steward:'steward',classification:'internal',approved_by:'approver',asset_id:'release',release_version:'1.0.0'}, 'stable-id');
    expect(payload.sources[0].run_id).toBe('run-1');
    expect(payload.product_kind).toBe('pipeline-evidence');
  });
  it('rejects unfinished runs and evidence without retained references', () => {
    expect(() => productDraftFromRun({run_id:'run-1',status:'running'})).toThrow(/completed/);
    expect(() => productDraftFromRun({run_id:'run-1',status:'completed',output_manifest:{}})).toThrow(/retained output artifacts/);
  });
});
