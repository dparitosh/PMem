"""Conservative routing for supported product-development questions."""
import re

def intent(question):
    text=question.casefold()
    if re.search(r'\b(ontology|schema|owl|class|classes|vocabulary|mapping|mappings)\b',text): return ''
    if re.search(r'\brequirements?\b',text) and re.search(r'\b(associated|related|linked|for|with|of)\b',text): return 'associated_requirements'
    if re.search(r'\b(pmi|product manufacturing information)\b',text) and re.search(r'\b(part|parts|product|products)\b',text): return 'parts_with_pmi'
    if re.search(r'\b(product and assembly|products and assemblies)\b',text) and 'information' in text: return 'product_assembly'
    if re.fullmatch(r'(?:please )?(?:find|list|show)(?: all| available| loaded| existing| the)? (?:products|parts|assemblies)[.!?]*',text.strip()): return 'product_assembly'
    return ''


def requirement_subject(question):
    """Retain the explicit business subject; never replace it with schema words."""
    match = re.search(r'\b(?:associated\s+with|related\s+to|linked\s+to|for|of)\s+(.+?)[?.!]*$', question.strip(), re.I)
    return match.group(1).strip(' .?!')[:220] if match else ''
