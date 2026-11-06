"""Model-visible input contracts derived from the same live OpenAPI as dispatch."""
from .input_contracts import resolve


def expand(value, document, depth=0):
    if depth > 30: raise ValueError('Proposal schema is cyclic or too deeply nested')
    if isinstance(value, list): return [expand(item, document, depth+1) for item in value]
    if not isinstance(value, dict): return value
    value = resolve(value, document)
    return {key: expand(item, document, depth+1) for key, item in value.items()}


def input_schema(document, tool):
    path = document.get('paths', {}).get('/api/v1'+tool['path']) or document.get('paths', {}).get(tool['path']) or {}
    operation = path.get(tool['method'].lower())
    if not operation: raise ValueError('Tool is absent from its live OpenAPI contract')
    media = 'multipart/form-data' if tool.get('input_kind') == 'multipart' else 'application/x-www-form-urlencoded' if tool.get('input_kind') == 'form' else 'application/json'
    body = resolve(operation.get('requestBody', {}), document)
    schema = expand(body.get('content', {}).get(media, {}).get('schema', {'type': 'object'}), document)
    if schema.get('type', 'object') != 'object': raise ValueError('Tool proposal requires an object input contract')
    properties = dict(schema.get('properties', {}))
    required = list(schema.get('required', []))
    for key in ('approved_by', 'approval_token', 'authorization', 'api_key'):
        properties.pop(key, None)
        if key in required: required.remove(key)
    if media == 'multipart/form-data':
        upload = 'artifact' if tool['id'] == 'ontology.register' else 'file'
        properties.pop(upload, None)
        required = [key for key in required if key != upload]
        schema = {'type': 'object', 'properties': {'form': {**schema, 'properties': properties, 'required': required},
            'file': {'type': 'object', 'properties': {'filename': {'type': 'string'}, 'content_base64': {'type': 'string'}},
                     'required': ['filename', 'content_base64']}}, 'required': ['file']}
        properties, required = schema['properties'], schema['required']
    for raw in path.get('parameters', []) + operation.get('parameters', []):
        parameter = resolve(raw, document)
        if parameter.get('in') in {'path', 'query'}:
            properties[parameter['name']] = expand(parameter.get('schema', {}), document)
            if parameter.get('required') and parameter['name'] not in required: required.append(parameter['name'])
    return {**schema, 'properties': properties, 'required': required}


def proposal_mode():
    import os
    mode = os.getenv('OLLAMA_PROPOSAL_MODE', 'structured').strip().lower()
    if mode not in {'structured', 'native'}: raise ValueError('OLLAMA_PROPOSAL_MODE must be structured or native')
    return mode
