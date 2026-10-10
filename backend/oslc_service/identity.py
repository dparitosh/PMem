"""Prefer retained RDF identities while accepting legacy graph element IDs."""
from urllib.parse import urlsplit, quote


def resource_reference(properties, element_id):
    for key in ('uri', 'rdf_uri'):
        value = str(properties.get(key) or '')
        if urlsplit(value).scheme in {'http', 'https', 'urn'} and not any(c.isspace() for c in value):
            return 'uri:' + value
    return str(element_id)


def resource_uri(base, properties, element_id):
    return base.rstrip('/') + '/oslc/resources/' + quote(resource_reference(properties, element_id), safe='')
