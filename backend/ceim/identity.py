"""Explicit, deterministic source-scoped identities for canonical publication."""
from __future__ import annotations
import hashlib
import json
import os

def scope_batch(entities, relationships, *, source_system='', required=False):
    source = str(source_system or '').strip()
    if not source:
        scopes = {str((item.get('provenance') or {}).get('source_system') or '').strip() for item in entities}
        if len(scopes) == 1:
            source = scopes.pop()
    if not source:
        if required: raise ValueError('source_system is required for source-scoped CEIM publication')
        return entities, relationships
    parts = [os.getenv('DEPO_TENANT_ID','default'), os.getenv('DEPO_PROJECT_ID','default'), source]
    if any(not part.strip() or '<' in part or '>' in part for part in parts):
        raise ValueError('Complete DEPO_TENANT_ID, DEPO_PROJECT_ID and source_system before scoped publication')
    scope = hashlib.sha256(json.dumps(parts,separators=(',',':')).encode()).hexdigest()
    ids, output = {}, []
    for entity in entities:
        provenance = dict(entity.get('provenance') or {})
        if provenance.get('identity_scope') and provenance['identity_scope'] != scope:
            raise ValueError('CEIM entity is already bound to a different source scope')
        old = str(entity['id'])
        new = old if provenance.get('identity_scope') else f'scoped:{scope}:{old}'
        ids[old] = new
        output.append({**entity,'id':new,'provenance':{**provenance,'source_system':source,'identity_scope':scope,'identity_version':'source-scoped-v1'}})
    edges = []
    for edge in relationships:
        if edge['source_id'] not in ids or edge['target_id'] not in ids:
            raise ValueError('Scoped relationships must reference entities in the same batch')
        provenance = dict(edge.get('provenance') or {})
        if provenance.get('identity_scope') and provenance['identity_scope'] != scope:
            raise ValueError('CEIM relationship is already bound to a different source scope')
        edges.append({**edge,'source_id':ids[edge['source_id']],'target_id':ids[edge['target_id']],
                      'provenance':{**provenance,'source_system':source,'identity_scope':scope,'identity_version':'source-scoped-v1'}})
    return output, edges
