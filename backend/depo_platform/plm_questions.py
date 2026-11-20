"""Conservative routing for supported product-development questions."""
import re

def intent(question):
    text=question.casefold()
    if re.search(r'\b(ontology|schema|owl|class|classes|vocabulary|mapping|mappings)\b',text): return ''
    # A requirement's own attributes need scoped property evidence, not a product-to-requirement path.
    if re.search(r'\brequirement\s+(?:value|text|number|details?|description)\b', text): return ''
    if re.search(r'\b(requirements?|specifications?)\b',text) and re.search(r'\b(associated|related|linked|for|with|of|does|have|has|its|their)\b',text): return 'associated_requirements'
    if re.search(r'\b(pmi|product manufacturing information)\b',text) and re.search(r'\b(part|parts|product|products|for|does|have|has)\b',text): return 'parts_with_pmi'
    # Detailed CAD/AP242 questions need property and relationship evidence,
    # not the name/type-only product inventory endpoint.
    if re.search(r'\b(cad|ap242|geometry|shape|material|revision|part number)\b',text) and re.search(r'\b(details?|describe|show)\b',text): return ''
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
    reference = re.split(r'[?!]|\.(?:\s|$)', subject, maxsplit=1)[0].strip().casefold()
    if node_id and (reference in {'it','its','them','their','this','that'} or re.fullmatch(
        r'(?:this|that|the selected|selected) (?:part|product|housing|bearing|shaft|race|feature|component|assembly|object|item|design|model|record)', reference
    )):
        return ''
    return subject


def property_subject(question):
    """Extract only an explicit subject of a property request, not a guessed entity."""
    text = question.strip()
    # A decision task is not an exact property lookup. Do not treat the rest
    # of a multi-clause request as a literal source-record name.
    if re.search(r'(?:^|[,;]\s*|\b(?:then|and)\s+)(?:compare|recommend|rank|choose)\b', text, re.I):
        return ''
    if re.search(r'\b(ontology|schema|owl|classes|vocabulary|mapping)\b', text, re.I):
        return ''
    match = re.search(r'\b(?:for|of)\s+(.+?)(?:[.!?](?:\s|$)|$)', text, re.I)
    if not match:
        return ''
    subject = re.split(r'\s+(?:with|and)\s+(?:source|evidence|citations?)\b', match.group(1), flags=re.I)[0].strip(' .?!')
    if re.fullmatch(r'(?:it|its|this|that|(?:this|that|the selected) (?:part|record|component|assembly|object))', subject, re.I):
        return ''
    return subject[:220]
