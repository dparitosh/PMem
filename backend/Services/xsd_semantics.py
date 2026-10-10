"""Preflight for constructs the current XSD-to-OWL translator can preserve."""
from xml.etree import ElementTree as ET

X = '{http://www.w3.org/2001/XMLSchema}'


def inspect_conversion_schemas(paths, primitive_types=()):
    identities = {}
    diagnostics = set()
    for path in paths:
        content = path.read_bytes()
        if b'<!DOCTYPE' in content.upper():
            raise ValueError('DOCTYPE is not permitted in conversion schemas')
        root = ET.fromstring(content)
        if root.tag != X + 'schema':
            raise ValueError(f'{path.name}: expected an XML Schema root')
        namespace = root.get('targetNamespace', '')
        for declaration in root:
            if declaration.tag in {X + 'complexType', X + 'simpleType'} and declaration.get('name'):
                name = declaration.get('name')
                if name in primitive_types:
                    raise ValueError(f'Type {name} shadows an XSD primitive; namespace-qualified type resolution is required')
                previous = identities.get(name)
                if previous is not None and previous != namespace:
                    raise ValueError(f'Namespace collision for type {name}; conversion requires namespace-qualified type identities')
                identities[name] = namespace
        for node in root.iter():
            kind = node.tag.removeprefix(X)
            for bound in ('minOccurs', 'maxOccurs'):
                value = node.get(bound)
                if value is not None and not (bound == 'maxOccurs' and value == 'unbounded') and (not value.isdigit()):
                    raise ValueError(f'{path.name}: invalid {bound}')
            if node.get('maxOccurs') not in (None, 'unbounded') and int(node.get('minOccurs', '1')) > int(node.get('maxOccurs')):
                raise ValueError(f'{path.name}: minOccurs exceeds maxOccurs')
            if kind in {'redefine', 'override', 'group', 'attributeGroup'}:
                raise ValueError(f'{path.name}: unsupported xs:{kind}; no partial ontology was generated')
            if kind in {'list', 'union', 'pattern', 'minInclusive', 'maxInclusive', 'minExclusive', 'maxExclusive', 'length', 'minLength', 'maxLength', 'totalDigits', 'fractionDigits', 'enumeration', 'unique', 'key', 'keyref', 'any', 'anyAttribute', 'assert', 'alternative'}:
                diagnostics.add(f'xs:{kind} is retained in source but is not fully represented by generated OWL/SHACL constraints')
            if kind == 'import' and not node.get('schemaLocation'):
                diagnostics.add('Namespace-only imports require separately supplied schema resolution; their semantics are not fully resolved')
            if kind in {'element', 'attribute'} and node.get('ref') and not node.get('type'):
                diagnostics.add('Referenced global declarations require QName resolution; unresolved property types are omitted by strict conversion')
    return sorted(diagnostics)


def element_particles(node, minimum=1, maximum=1):
    """Yield owned elements with compositor occurrence bounds preserved."""
    for child in node:
        if child.tag == X + 'complexType':
            continue
        if child.tag == X + 'choice':
            # A branch is optional individually; the choice group is validated separately.
            yield from element_particles(child, 0, maximum)
        elif child.tag in {X + 'sequence', X + 'all'}:
            lo = minimum * int(child.get('minOccurs', '1'))
            hi = None if maximum is None or child.get('maxOccurs') == 'unbounded' else maximum * int(child.get('maxOccurs', '1'))
            yield from element_particles(child, lo, hi)
        elif child.tag == X + 'element':
            lo = minimum * int(child.get('minOccurs', '1'))
            hi = None if maximum is None or child.get('maxOccurs') == 'unbounded' else maximum * int(child.get('maxOccurs', '1'))
            yield child, str(lo), 'unbounded' if hi is None else str(hi)
        else:
            yield from element_particles(child, minimum, maximum)
