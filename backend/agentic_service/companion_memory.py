"""Conversation text may refine retrieval only within the same retained scope."""
import re
from .context_scope import same_companion_scope


def retrieval_query(message, turns, scope):
    # An independent short question such as 'QIF mappings' must not inherit an
    # unrelated AP242/product question. Only explicit anaphoric follow-ups do.
    if len(message.split())>200 or not re.search(r'\b(it|its|they|them|their|this|those|these|that|same|above|more)\b',message,re.I):
        return message
    # A selected model identity already resolves its own requirement attributes.
    if scope.get('page') == 'modeling' and scope.get('node_id') and re.search(r'\brequirement\s+(?:value|text|number|details?|description)\b', message, re.I):
        return message
    from backend.depo_platform.plm_questions import requirement_subject
    explicit_subject = requirement_subject(message)
    if (explicit_subject and not re.search(r'\b(it|its|they|them|their|this|that|these|those|same|above)\b', explicit_subject, re.I)) or re.search(r'\b(?:more|details?)\s+(?:about|on)\s+(?!it\b|them\b|that\b|these\b|those\b)\S+', message, re.I):
        return message
    # The selected identity already resolves the pronoun. Never prepend a
    # previous task (e.g. requirements) when the user switches to PMI.
    for turn in recall_turns(message, turns, scope):
        if turn.get('answerable') is False or turn.get('status') in {'failed', 'interrupted', 'timed_out'}:
            continue
        previous=turn.get('graph_context') or {}
        if not same_companion_scope(previous, scope):continue
        if scope.get('node_id') and re.search(r'\bpmi\b', message, re.I):
            return 'Show PMI for it'
        text=turn.get('resolved_query') or turn.get('user_request')
        if isinstance(text,str) and text.strip():
            from backend.depo_platform.plm_questions import requirement_subject
            subject = requirement_subject(text)
            reference = r'\b(?:(?:this|that|the selected)\s+(?:part|product|component|assembly|object|record)|it|its|them|their)\b'
            if subject and re.search(reference, message, re.I):
                rewritten = re.sub(reference, lambda _: subject, message, flags=re.I)
                if not requirement_subject(rewritten):
                    if re.search(r'\b(requirements?|specifications?)\b',message,re.I):
                        return 'Show requirements for '+subject
                    if re.search(r'\bpmi\b',message,re.I):
                        return 'Show PMI for '+subject
                return rewritten
            return f'{text[:1000]} {message}'
    return message


def active_turns(turns, scope):
    """An unresolved new subject ends recall of the older engineering subject."""
    active = []
    for turn in turns:
        if not same_companion_scope(turn.get('graph_context'), scope): continue
        if (turn.get('retrieval') or {}).get('context_invalidated'): break
        if turn.get('answerable') is not False and turn.get('status') not in {'failed','interrupted','timed_out'}:
            active.append(turn)
            if len(active) >= 50: break
    return active


def unselected_reference(message, scope):
    if any(scope.get(key) for key in ('node_id','run_id','product_id','reconciliation_id')): return False
    if not re.search(r'\b(it|its|this part|that part|this component|that component)\b', message, re.I): return False
    from backend.depo_platform.plm_questions import requirement_subject
    subject = requirement_subject(message)
    return not subject or bool(re.fullmatch(r'(?:it|its|this|that|(?:this|that|the selected) (?:part|component|record|object))', subject, re.I))


def followup_needs_subject(message, turns, scope):
    if not unselected_reference(message, scope): return False
    previous = next((turn for turn in turns if same_companion_scope(turn.get('graph_context'), scope)), None)
    return previous is None or previous.get('answerable') is False or bool((previous.get('retrieval') or {}).get('context_invalidated'))


def recall_turns(message, turns, scope, limit=6):
    """Request-local Semantica recall; PostgreSQL remains the durable authority.

    LangChain Documents retain provenance. No embedding model, new database,
    provider call or unscoped graph conversation is introduced.
    """
    candidates = active_turns(turns, scope)
    if not candidates: return []
    try:
        from langchain_core.documents import Document
        documents=[]; budget=16000
        for index, turn in enumerate(candidates):
            text=turn.get('resolved_query') or turn.get('user_request') or ''
            if not isinstance(text,str) or not text.strip():continue
            text=text[:min(1000,budget)]
            if not text:break
            documents.append(Document(page_content=text, metadata={'index':index,'job_id':turn.get('job_id',''), 'advisory_only':True}))
            budget-=len(text)
        if not documents:return []
        from semantica.context.agent_memory import AgentMemory
        from .prompt_security import protect
        memory=AgentMemory(max_memory_size=50,short_term_limit=50)
        for document in documents:
            memory.store(protect(document.page_content),metadata=document.metadata,skip_vector=True,skip_graph=True)
        matches=memory.retrieve(protect(message)[:1000],max_results=limit)
        indexes=[item.get('metadata',{}).get('index') for item in matches]
        # Pronouns refer first to the latest successful scoped subject, even
        # when keyword recall ranks an older topic more highly.
        latest = [documents[0].metadata['index']] if re.search(r'\b(it|its|they|them|their|this|that|these|those|same|above)\b', message, re.I) else []
        ordered=[*latest,*indexes,*[d.metadata['index'] for d in documents]]
        chosen=list(dict.fromkeys(index for index in ordered if isinstance(index,int) and 0<=index<len(candidates)))[:limit]
        return [candidates[index] for index in chosen]
    except Exception:
        import logging
        logging.getLogger(__name__).warning('Context recall unavailable; using bounded scoped history')
        return candidates[:limit]


def evidence_grounding(evidence, root_id=''):
    """Retain observed identities, not a guessed selection or model prose."""
    resources = {}
    roots = {}
    relationship_ids = set()
    incomplete = False
    for item in evidence:
        if item.get('evidence_type') == 'graph_resource':
            identity = item.get('resource_id')
            if not isinstance(identity, str) or not identity: continue
            props = item.get('properties') or {}
            resource = {'resource_id': identity, 'label': item.get('label'),
                        'ontology_id': item.get('ontology_id'),
                        'publication_revision': props.get('publication_revision'),
                        'property_names': sorted(props), 'path': item.get('why_included')}
            resources[(identity, resource['ontology_id'])] = resource
            if identity == root_id: roots[(identity, resource['ontology_id'])] = resource
        elif item.get('evidence_type') == 'graph_relationship':
            if item.get('resource_id'): relationship_ids.add(item['resource_id'])
        elif item.get('evidence_type') == 'business_answer':
            incomplete = incomplete or bool((item.get('coverage') or {}).get('has_more'))
            fields = {'associated_requirements': [('subject_id', 'subject'), ('requirement_id', 'requirement')],
                      'parts_with_pmi': [('part_id', 'part'), ('pmi_id', 'pmi')],
                      'product_assembly': [('node_id', 'name')]}.get(item.get('intent'), [])
            for row in item.get('rows', [])[:20]:
                for index, (identity_key, label_key) in enumerate(fields):
                    identity = row.get(identity_key)
                    if not isinstance(identity, str) or not identity: continue
                    source = row.get('subject_source') if identity_key == 'subject_id' else row.get('source')
                    source = source or row.get('source')
                    resource = {'resource_id': identity, 'label': row.get(label_key),
                                'ontology_id': source, 'ontology_prefix': row.get('prefix'),
                                'publication_revision': row.get('publication_revision') if index == 0 else None,
                                'property_names': [], 'path': row.get('path')}
                    resources[(identity, source)] = resource
                    if index == 0 and (item.get('intent') == 'product_assembly' or identity == root_id):
                        roots[(identity, source)] = resource
                for edge in row.get('path', []):
                    if edge.get('id'): relationship_ids.add(edge['id'])
                if row.get('relationship_id'): relationship_ids.add(row['relationship_id'])
    resolved = next(iter(roots.values())) if len(roots) == 1 and not incomplete else None
    return {'resources': list(resources.values()), 'relationship_ids': sorted(relationship_ids),
            'resolved_identity': resolved,
            'memory_use': 'historical_evidence_requires_current_graph_read',
            'semantic_entailment_verified': False}


def followup_context(message, turns, scope):
    """Use a unique observed subject only for an explicit same-scope follow-up.

    This narrows the next authenticated graph read; it never reuses old facts.
    Keep the user's search scope unchanged in the retained record.
    """
    if not unselected_reference(message, scope): return dict(scope)
    previous = next(iter(active_turns(turns, scope)), None)
    identity = (((previous or {}).get('retrieval') or {}).get('grounding') or {}).get('resolved_identity')
    if not isinstance(identity, dict): return dict(scope)
    node, source = identity.get('resource_id'), identity.get('ontology_id')
    if not isinstance(node, str) or not node or len(node)>256 or not isinstance(source, str) or not source or len(source)>300:
        return dict(scope)
    if scope.get('ontology') and scope['ontology'] != source: return dict(scope)
    prefix = identity.get('ontology_prefix') or ''
    if scope.get('ontology_prefix') and scope['ontology_prefix'] != prefix: return dict(scope)
    return {**scope, 'node_id': node, 'ontology': source,
            'ontology_prefix': scope.get('ontology_prefix') or prefix}
