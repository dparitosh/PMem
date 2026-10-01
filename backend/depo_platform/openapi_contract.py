"""Normalize FastAPI's JSON Schema output for the published OAS 3.0 contract."""
from copy import deepcopy
import inspect


def normalize_openapi(document: dict) -> dict:
    result = deepcopy(document)
    schemas = result.get('components', {}).get('schemas', {})

    def convert(value):
        if isinstance(value, list):
            return [convert(item) for item in value]
        if not isinstance(value, dict):
            return value
        value = {key: ({name: convert(schema) for name, schema in item.items()}
                       if key in {'properties', 'schemas'} and isinstance(item, dict) else
                       convert(item)) if key not in {'example', 'default', 'enum', 'const'} else item
                 for key, item in value.items()}
        if 'const' in value:
            value['enum'] = [value.pop('const')]
        if 'examples' in value and isinstance(value['examples'], list):
            examples = value.pop('examples')
            if examples:
                value.setdefault('example', examples[0])
        for key, boundary in [('exclusiveMinimum', 'minimum'), ('exclusiveMaximum', 'maximum')]:
            if key in value and not isinstance(value[key], bool):
                value[boundary] = value[key]
                value[key] = True
        if value.get('type') == 'null':
            value.pop('type')
            value['enum'] = [None]
        # Null branches become typed nullable branches. Keep reference siblings
        # inside allOf because OAS 3.0 ignores siblings of a Reference Object.
        for union in ('anyOf', 'oneOf'):
            branches = value.get(union)
            if branches and any(branch == {'enum': [None]} for branch in branches):
                branches = [branch for branch in branches if branch != {'enum': [None]}]
                for branch in branches:
                    if '$ref' in branch:
                        target = schemas.get(branch['$ref'].rsplit('/', 1)[-1], {})
                        reference = branch.pop('$ref')
                        branch['allOf'] = [{'$ref': reference}]
                        branch['type'] = target.get('type', 'object')
                    branch['nullable'] = True
                if len(branches) == 1:
                    value.pop(union)
                    value = {**branches[0], **value}
                else:
                    value[union] = branches or [{'enum': [None]}]
        return value

    result = convert(result)
    result['openapi'] = '3.0.3'
    return result


def describe_security(document, routes):
    schemes = document.setdefault('components', {}).setdefault('securitySchemes', {})
    schemes.update({'BearerKey': {'type': 'http', 'scheme': 'bearer', 'description': 'Runtime service API key or gateway bearer. Credential scopes differ by service and operation.'},
                    'ApiKey': {'type': 'apiKey', 'in': 'header', 'name': 'X-API-Key'}})
    for route in routes:
        path = getattr(route, 'path_format', None)
        if path not in document.get('paths', {}):
            continue
        try:
            source = inspect.getsource(route.endpoint)
        except (TypeError, OSError):
            source = ''
        dependency_names = set()
        def visit(dependant):
            for dependency in getattr(dependant, 'dependencies', []):
                dependency_names.add(getattr(dependency.call, '__name__', ''))
                visit(dependency)
        visit(getattr(route, 'dependant', None))
        header_required = bool(dependency_names & {'graph_read_identity', '_qif_identity', '_ingestion_identity', '_modeling_identity', '_metadata_registry_identity'})
        approval = 'approval_identity(' in source
        header_required = header_required or 'graph_read_identity(' in source or 'service_write_identity(' in source
        for method in getattr(route, 'methods', []):
            operation = document['paths'][path].get(method.lower())
            if not operation:
                continue
            # Public QIF/ingestion reads remain public; modeling reads require
            # graph-read identity. Body approval is a separate documented path.
            public_read = method in {'GET', 'HEAD'} and dependency_names and dependency_names <= {'_qif_identity', '_ingestion_identity', '_metadata_registry_identity'}
            if 'require_admin_api_key' in dependency_names:
                operation['security'] = [{'ApiKey': []}]
                operation.setdefault('responses', {}).setdefault('401', {'description': 'Invalid or missing administrator API key'})
            elif header_required and not public_read:
                operation['security'] = [{'BearerKey': []}, {'ApiKey': []}]
            elif approval:
                operation['security'] = [{'BearerKey': []}, {'ApiKey': []}, {}]
            if approval or (header_required and not public_read):
                operation['x-depo-authorization'] = {'approval_fields': ['approved_by', 'approval_token'] if approval else [],
                    'note': 'Runtime authorization remains enforced. Approval requires the configured operation token or trusted gateway role; the global read key does not grant write permission.'}
                operation.setdefault('responses', {}).setdefault('403', {'description': 'Required identity, API key or approval is absent or invalid'})
    return document


def contract_errors(document):
    errors = []
    if not isinstance(document, dict):
        return ['OpenAPI document must be an object']
    operation_ids = set()
    if document.get('openapi') != '3.0.3':
        errors.append('Expected OpenAPI 3.0.3')
    def walk(value, location):
        if isinstance(value, dict):
            if value.get('type') == 'null':
                errors.append(f'{location}: null type is incompatible with OAS 3.0')
            if isinstance(value.get('type'), list):
                errors.append(f'{location}: type arrays are incompatible with OAS 3.0')
            for key, item in value.items():
                if key not in {'example', 'default', 'enum'}:
                    walk(item, location + '/' + key)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f'{location}/{index}')
    walk(document.get('components', {}).get('schemas', {}), 'schemas')
    for path, operations in document.get('paths', {}).items():
        for method, operation in operations.items():
            if method not in {'get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'trace'}:
                continue
            walk(operation, path + '/' + method)
            identity = operation.get('operationId')
            if not identity or identity in operation_ids:
                errors.append(f'{path}/{method}: missing or duplicate operationId')
            operation_ids.add(identity)
    return errors


if __name__ == '__main__':
    import json
    import sys
    errors = contract_errors(json.load(sys.stdin))
    print(json.dumps({'valid': not errors, 'errors': errors}))
    sys.exit(1 if errors else 0)
