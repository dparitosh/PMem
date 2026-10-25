"""Conservative routing for supported product-development questions."""
import re

def intent(question):
    text=question.casefold()
    if re.search(r'\b(ontology|schema|owl|class|classes|vocabulary|mapping|mappings)\b',text): return ''
    if re.search(r'\b(pmi|product manufacturing information)\b',text) and re.search(r'\b(part|parts|product|products)\b',text): return 'parts_with_pmi'
    if re.search(r'\b(product and assembly|products and assemblies)\b',text) and 'information' in text: return 'product_assembly'
    if re.fullmatch(r'(?:please )?(?:find|list|show)(?: all| available| loaded| existing| the)? (?:products|parts|assemblies)[.!?]*',text.strip()): return 'product_assembly'
    return ''
