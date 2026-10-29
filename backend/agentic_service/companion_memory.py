"""Conversation text may refine retrieval only within the same retained scope."""
import re
from .context_scope import same_companion_scope


def retrieval_query(message, turns, scope):
    # An independent short question such as 'QIF mappings' must not inherit an
    # unrelated AP242/product question. Only explicit anaphoric follow-ups do.
    if len(message.split())>8 or not re.search(r'\b(it|its|they|them|their|those|these|that|same|above|more)\b',message,re.I):
        return message
    for turn in turns:
        previous=turn.get('graph_context') or {}
        if not same_companion_scope(previous, scope):continue
        text=turn.get('user_request')
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
