"""Conversation text may refine retrieval only within the same retained scope."""
import re
from .context_scope import same_companion_scope


def retrieval_query(message, turns, scope):
    # An independent short question such as 'QIF mappings' must not inherit an
    # unrelated AP242/product question. Only explicit anaphoric follow-ups do.
    if len(message.split())>8 or not re.search(r'\b(it|its|they|them|their|those|these|that|same|above|more)\b',message,re.I):
        return message
    from backend.depo_platform.plm_questions import requirement_subject
    explicit_subject = requirement_subject(message)
    if (explicit_subject and not re.search(r'\b(it|its|they|them|their|this|that|these|those|same|above)\b', explicit_subject, re.I)) or re.search(r'\b(?:more|details?)\s+(?:about|on)\s+(?!it\b|them\b|that\b|these\b|those\b)\S+', message, re.I):
        return message
    for turn in recall_turns(message, turns, scope):
        if turn.get('answerable') is False or turn.get('status') in {'failed', 'interrupted', 'timed_out'}:
            continue
        previous=turn.get('graph_context') or {}
        if not same_companion_scope(previous, scope):continue
        text=turn.get('resolved_query') or turn.get('user_request')
        if isinstance(text,str) and text.strip():
            from backend.depo_platform.plm_questions import requirement_subject
            subject = requirement_subject(text)
            if subject and re.search(r'\b(it|its|them|their)\b', message, re.I):
                rewritten = re.sub(r'\b(it|its|them|their)\b', lambda _: subject, message, flags=re.I)
                if not requirement_subject(rewritten):
                    if re.search(r'\b(requirements?|specifications?)\b',message,re.I):
                        return 'Show requirements for '+subject
                    if re.search(r'\bpmi\b',message,re.I):
                        return 'Show PMI for '+subject
                return rewritten
            return f'{text[:1000]} {message}'
    return message


def recall_turns(message, turns, scope, limit=6):
    """Request-local Semantica recall; PostgreSQL remains the durable authority.

    LangChain Documents retain provenance. No embedding model, new database,
    provider call or unscoped graph conversation is introduced.
    """
    candidates = [turn for turn in turns if turn.get('answerable') is not False
                  and turn.get('status') not in {'failed','interrupted','timed_out'}
                  and same_companion_scope(turn.get('graph_context'), scope)][:50]
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
