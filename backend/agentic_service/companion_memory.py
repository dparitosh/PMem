"""Conversation text may refine retrieval only within the same retained scope."""
import re


def retrieval_query(message, turns, scope):
    # An independent short question such as 'QIF mappings' must not inherit an
    # unrelated AP242/product question. Only explicit anaphoric follow-ups do.
    if len(message.split())>8 or not re.search(r'\b(it|its|they|them|their|those|these|that|same|above|more)\b',message,re.I):
        return message
    selected={key:scope.get(key,'') for key in ('ontology','ontology_prefix','page')}
    for turn in turns:
        previous=turn.get('graph_context') or {}
        if {key:previous.get(key,'') for key in selected} != selected:continue
        text=turn.get('user_request')
        if isinstance(text,str) and text.strip():return f'{text[:1000]} {message}'
    return message
