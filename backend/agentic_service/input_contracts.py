"""Bounded validation of the OpenAPI 3 schema subset used by DEPO services."""
import re


def validate_bindings(value, completed_steps, depth=0):
    if depth > 40:
        raise ValueError('Workflow inputs exceed 40 nesting levels')
    if isinstance(value, str) and value.startswith('$steps.'):
        match = re.fullmatch(r'\$steps\.([1-9][0-9]*)\.result(?:\.[^\s.]+)*', value)
        if not match or int(match.group(1)) > completed_steps:
            raise ValueError('Workflow inputs must reference a prior step')
    elif isinstance(value, dict):
        for item in value.values():
            validate_bindings(item, completed_steps, depth+1)
    elif isinstance(value, list):
        for item in value:
            validate_bindings(item, completed_steps, depth+1)


def resolve(schema, document):
    visited = set()
    while '$ref' in schema:
        reference = schema['$ref']
        if not reference.startswith('#/') or reference in visited:
            raise ValueError('External or cyclic schema aliases are not supported')
        visited.add(reference)
        target = document
        for part in reference[2:].split('/'):
            target = target[part.replace('~1', '/').replace('~0', '~')]
        schema = {**target, **{key: value for key, value in schema.items() if key != '$ref'}}
    return schema


def validate(value, schema, document, *, deferred=False, path='inputs', depth=0):
    if depth > 40:
        raise ValueError('Input schema nesting exceeds 40 levels')
    if deferred and isinstance(value, str) and value.startswith('$steps.'):
        if not re.fullmatch(r'\$steps\.[1-9][0-9]*\.result(?:\.[^\s.]+)*', value):
            raise ValueError('Invalid workflow result reference')
        return
    if schema is True:
        return
    if schema is False:
        raise ValueError(f'{path} is not allowed')
    schema = resolve(schema, document)
    for unsupported in ('not', 'if', 'then', 'else', 'patternProperties', 'dependentSchemas',
                        'dependentRequired', 'unevaluatedProperties', 'prefixItems', 'contains',
                        'propertyNames', '$dynamicRef'):
        if unsupported in schema:
            raise ValueError(f'Unsupported input schema constraint: {unsupported}')
    if value is None and schema.get('nullable'):
        return
    for branch in schema.get('allOf', []):
        validate(value, branch, document, deferred=deferred, path=path, depth=depth+1)
    for union in ('anyOf', 'oneOf'):
        if union in schema:
            matches = 0
            for branch in schema[union]:
                try:
                    validate(value, branch, document, deferred=deferred, path=path, depth=depth+1)
                    matches += 1
                except ValueError:
                    pass
            if not matches or (union == 'oneOf' and matches != 1):
                raise ValueError(f'{path} does not match {union}')
    types = {'object': lambda x: isinstance(x, dict), 'array': lambda x: isinstance(x, list),
             'string': lambda x: isinstance(x, str), 'boolean': lambda x: isinstance(x, bool),
             'integer': lambda x: isinstance(x, int) and not isinstance(x, bool),
             'number': lambda x: isinstance(x, (int, float)) and not isinstance(x, bool), 'null': lambda x: x is None}
    kind = schema.get('type')
    if kind and not any(types[item](value) for item in (kind if isinstance(kind, list) else [kind])):
        raise ValueError(f'{path} has the wrong type')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError(f'{path} is not an allowed value')
    if 'const' in schema and value != schema['const']:
        raise ValueError(f'{path} does not match its constant')
    if isinstance(value, dict):
        if len(value) < schema.get('minProperties', 0) or len(value) > schema.get('maxProperties', float('inf')):
            raise ValueError(f'{path} has an invalid property count')
        properties = schema.get('properties', {})
        for key in schema.get('required', []):
            if key not in value:
                raise ValueError(f'{path}.{key} is required')
        for key, item in value.items():
            child = properties.get(key, schema.get('additionalProperties', True))
            validate(item, child, document, deferred=deferred, path=f'{path}.{key}', depth=depth+1)
    if isinstance(value, list):
        if len(value) < schema.get('minItems', 0) or len(value) > schema.get('maxItems', float('inf')):
            raise ValueError(f'{path} has an invalid item count')
        if schema.get('uniqueItems') and any(item in value[:index] for index, item in enumerate(value)):
            raise ValueError(f'{path} contains duplicate items')
        for item in value:
            validate(item, schema.get('items', True), document, deferred=deferred, path=path+'[]', depth=depth+1)
    if isinstance(value, str):
        if len(value) < schema.get('minLength', 0) or len(value) > schema.get('maxLength', float('inf')):
            raise ValueError(f'{path} has an invalid length')
        if schema.get('pattern') and not re.search(schema['pattern'], value):
            raise ValueError(f'{path} does not match its pattern')
        from datetime import datetime, date, time
        from urllib.parse import urlsplit
        from uuid import UUID
        import ipaddress
        format_name = schema.get('format')
        try:
            if format_name == 'date':
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                    raise ValueError('Invalid date')
                date.fromisoformat(value)
            elif format_name == 'date-time':
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}[Tt].+(?:[Zz]|[+-]\d{2}:\d{2})', value):
                    raise ValueError('Invalid date-time')
                datetime.fromisoformat(value.upper().replace('Z', '+00:00'))
            elif format_name == 'time':
                time.fromisoformat(value.upper().replace('Z', '+00:00'))
            elif format_name == 'uuid':
                UUID(value)
            elif format_name in {'ipv4', 'ipv6'}:
                address = ipaddress.ip_address(value)
                if address.version != (4 if format_name == 'ipv4' else 6):
                    raise ValueError('Wrong IP version')
            elif format_name in {'uri', 'url'}:
                if not urlsplit(value).scheme or any(character.isspace() for character in value):
                    raise ValueError('Invalid URI')
            elif format_name not in {None, 'binary', 'byte', 'password'}:
                raise ValueError('Unsupported string format: '+format_name)
        except ValueError as exc:
            raise ValueError(f'{path} has an invalid or unsupported {format_name} format') from exc
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        import math
        if not math.isfinite(value):
            raise ValueError(f'{path} must be finite')
        if value < schema.get('minimum', -float('inf')) or value > schema.get('maximum', float('inf')):
            raise ValueError(f'{path} is outside its allowed range')
        for name, boundary, comparison in (
            ('exclusiveMinimum', 'minimum', lambda a,b: a <= b),
            ('exclusiveMaximum', 'maximum', lambda a,b: a >= b)):
            if name in schema:
                edge = schema.get(boundary) if isinstance(schema[name], bool) else schema[name]
                if schema[name] is not False and edge is not None and comparison(value, edge):
                    raise ValueError(f'{path} is outside its exclusive range')
        if 'multipleOf' in schema:
            ratio = value / schema['multipleOf']
            if not math.isclose(ratio, round(ratio), rel_tol=0, abs_tol=1e-9):
                raise ValueError(f'{path} is not a valid multiple')


def validate_operation(document, tool, inputs, *, deferred=False):
    path = document.get('paths', {}).get('/api/v1'+tool['path']) or document.get('paths', {}).get(tool['path'])
    operation = (path or {}).get(tool['method'].lower())
    if not operation:
        raise ValueError('Tool is absent from its live OpenAPI contract')
    parameters = [resolve(item, document) for item in path.get('parameters', []) + operation.get('parameters', [])]
    for parameter in parameters:
        if parameter.get('in') not in {'path', 'query'}:
            continue
        key = parameter['name']
        if parameter.get('required') and key not in inputs:
            raise ValueError(f'inputs.{key} is required')
        if key in inputs:
            validate(inputs[key], parameter.get('schema', {}), document, deferred=deferred, path='inputs.'+key)
    body = resolve(operation.get('requestBody', {}), document)
    content = body.get('content', {})
    media = 'multipart/form-data' if tool.get('input_kind') == 'multipart' else 'application/x-www-form-urlencoded' if tool.get('input_kind') == 'form' else 'application/json'
    if body.get('required') and media not in content:
        raise ValueError('Tool input encoding does not match its required request body')
    if media in content:
        if deferred and media == 'multipart/form-data' and isinstance(inputs.get('form'), str):
            validate(inputs['form'], {'type':'object'}, document, deferred=True)
            return operation
        values = dict(inputs.get('form', {})) if media == 'multipart/form-data' else dict(inputs)
        if media == 'multipart/form-data':
            values['artifact' if tool['id'] == 'ontology.register' else 'file'] = 'validated-upload'
        # These values are injected from verified service credentials during dispatch.
        if tool.get('mutates'):
            values.update(approved_by='verified-actor', approval_token='verified-token')
        for parameter in parameters:
            if parameter.get('in') == 'path':
                values.pop(parameter['name'], None)
        validate(values, content[media].get('schema', {}), document, deferred=deferred)
    return operation
