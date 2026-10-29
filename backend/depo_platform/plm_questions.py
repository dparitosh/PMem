"""Conservative routing for supported product-development questions."""
import re

def intent(question):
    text=question.casefold()
    if re.search(r'\b(ontology|schema|owl|class|classes|vocabulary|mapping|mappings)\b',text): return ''
    if re.search(r'\b(requirements?|specifications?)\b',text) and re.search(r'\b(associated|related|linked|for|with|of|does|have|has|its|their)\b',text): return 'associated_requirements'
    if re.search(r'\b(pmi|product manufacturing information)\b',text) and re.search(r'\b(part|parts|product|products|for|does|have|has)\b',text): return 'parts_with_pmi'
    if re.search(r'\b(products?|parts?|assembl(?:y|ies))\b',text) and re.search(r'\b(details?|information|describe)\b',text): return 'product_assembly'
    if re.search(r'\b(product and assembly|products and assemblies)\b',text) and 'information' in text: return 'product_assembly'
    if re.fullmatch(r'(?:please )?(?:find|list|show)(?: all| available| loaded| existing| the)? (?:products|parts|assemblies)[.!?]*',text.strip()): return 'product_assembly'
    return ''


def requirement_subject(question):
    """Retain the explicit business subject; never replace it with schema words."""
    for pattern in (
        r'\b(?:requirements?|specifications?)\s+(?:does|do)\s+(.+?)\s+(?:have|include|contain)\b',
        r'^\s*(?:does|do)\s+(.+?)\s+(?:have|include|contain)\s+(?:any\s+)?(?:pmi|requirements?|specifications?)\b',
        r'\b(?:associated\s+with|related\s+to|linked\s+to|for|of)\s+(.+?)[?.!]*$',
    ):
        match = re.search(pattern, question.strip(), re.I)
        if match:
            subject = re.split(r'\s+with\s+source\s+references?\b', match.group(1), flags=re.I)[0]
            return subject.strip(' .?!\"\'')[:220]
    return ''


def business_subject(question, node_id=''):
    subject = requirement_subject(question)
    # A selected identity resolves pronouns; do not search its label for "it".
    if node_id and subject.casefold() in {'it','its','them','their','this','that','this part','this product','the selected part','the selected product'}:
        return ''
    return subject
