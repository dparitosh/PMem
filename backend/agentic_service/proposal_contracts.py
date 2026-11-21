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
    # FastAPI represents optional request bodies as object | null. Agent inputs
    # are always an object containing path/query fields, so expose the object
    # branch rather than an invalid nullable function-parameter root. Dispatch
    # still validates against the original live OpenAPI contract.
    # OpenAPI 3.0 deployments wrap the same optional body in a single allOf
    # reference plus nullable=true. Only unwrap this annotation-only wrapper;
    # never flatten arbitrary intersecting contracts or overwrite constraints.
    conjunction = schema.get('allOf')
    wrapper_keys = {'allOf','type','nullable','title','description','default','deprecated'}
    if (isinstance(conjunction,list) and len(conjunction)==1
            and conjunction[0].get('type')=='object' and set(schema)<=wrapper_keys):
        schema = {**{key:value for key,value in schema.items() if key not in {'allOf','nullable'}}, **conjunction[0]}
    branches = schema.get('anyOf')
    if isinstance(branches, list) and len(branches) == 2:
        objects = [branch for branch in branches if branch.get('type') == 'object']
        nulls = [branch for branch in branches if branch.get('type') == 'null']
        if len(objects) == len(nulls) == 1:
            schema = {**{key:value for key,value in schema.items() if key != 'anyOf'}, **objects[0]}
    if schema.get('type', 'object') != 'object' or any(key in schema for key in ('anyOf','oneOf','allOf')):
        raise ValueError('Tool proposal requires an unambiguous object input contract')
    schema.setdefault('type', 'object')
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
