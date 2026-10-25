"""Stable document snapshot scopes for canonical batch publications."""
import hashlib
import json
import os
import re

def publication_scope(payload, record, batch):
    explicit=str(payload.get('ontology_id') or '').strip().lower()
    if explicit: return explicit
    pinned=str(((record.get('output_manifest') or {}).get('publication_intent') or {}).get('ontology_id') or '').strip()
    if pinned: return pinned
    standard=re.sub(r'[^a-z0-9_-]','-',str(batch.get('standard') or record.get('source_standard') or 'batch').lower())
    documents=sorted({str((e.get('provenance') or {}).get('source_document_sha256')) for e in batch.get('entities',[]) if (e.get('provenance') or {}).get('source_document_sha256')})
    identity=documents or [(record.get('input_manifest') or {}).get('payload_digest') or record['run_id']]
    source=payload.get('source_system') or batch.get('source_system') or record.get('source_system') or ''
    scope=hashlib.sha256(json.dumps([os.getenv('DEPO_TENANT_ID','default'),os.getenv('DEPO_PROJECT_ID','default'),source,identity],separators=(',',':')).encode()).hexdigest()[:24]
    return f'ceim-{standard}-{scope}'
