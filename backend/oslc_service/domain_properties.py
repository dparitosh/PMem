"""Project retained domain values without inventing status or workflow state."""
from urllib.parse import urlsplit


def project_properties(properties, types):
    projected = {}
    for predicate, aliases in {
        'dcterms:title': ('dcterms:title', 'title', 'name', 'label'),
        'dcterms:description': ('dcterms:description', 'description', 'definition', 'comment'),
        'dcterms:identifier': ('dcterms:identifier', 'identifier', 'id', 'code'),
    }.items():
        for alias in aliases:
            if properties.get(alias) not in (None, ''):
                projected[predicate] = properties[alias]
                break
    for namespace, resource in [('cm', 'ChangeRequest'), ('qm', 'TestResult')]:
        if f'http://open-services.net/ns/{namespace}#{resource}' in types:
            key = f'oslc_{namespace}:status'
            value = properties.get(key, properties.get('status'))
            if value not in (None, ''):
                projected[key] = value
    if 'http://open-services.net/ns/rm#RequirementCollection' in types:
        values = properties.get('oslc_rm:uses', properties.get('uses', []))
        if isinstance(values, str):
            values = [values]
        if isinstance(values, list):
            links = [value for value in values if isinstance(value, str) and urlsplit(value).scheme in {'http', 'https', 'urn'}]
            if links:
                projected['oslc_rm:uses'] = links
    return projected
