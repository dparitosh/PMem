"""Preflight for constructs the current XSD-to-OWL translator can preserve."""
from xml.etree import ElementTree as ET
import io

X = '{http://www.w3.org/2001/XMLSchema}'


def validate_xsd_schema_set(root_path):
    """Compile the supplied local closure before translating or retaining output."""
    from lxml import etree
    try:
        document = etree.parse(str(root_path), etree.XMLParser(resolve_entities=False, no_network=True))
        etree.XMLSchema(document)
    except (etree.XMLSyntaxError, etree.XMLSchemaParseError) as exc:
        message = exc.error_log.last_error.message if exc.error_log.last_error else 'invalid schema set'
        raise ValueError(f'XSD schema-set validation failed: {message}') from exc


def inspect_conversion_schemas(paths, primitive_types=()):
    identities = {}
    diagnostics = set()
    for path in paths:
        content = path.read_bytes()
        probe = content.replace(b'\x00', b'').upper()
        if b'<!DOCTYPE' in probe or b'<!ENTITY' in probe:
            raise ValueError('DOCTYPE/entities are not permitted in conversion schemas')
        root = ET.fromstring(content)
        if root.tag != X + 'schema':
            raise ValueError(f'{path.name}: expected an XML Schema root')
        namespace = root.get('targetNamespace', '')
        for declaration in root:
            if declaration.tag in {X + 'complexType', X + 'simpleType'} and declaration.get('name'):
                name = declaration.get('name')
                if name in primitive_types:
                    diagnostics.add(f'Type {name} shadows an XSD primitive and uses a qualified conversion identity')
                previous = identities.get(name)
                if previous is not None and previous != namespace:
                    diagnostics.add(f'Namespace collision for type {name} is preserved using qualified conversion identities')
                identities[name] = namespace
        for node in root.iter():
            kind = node.tag.removeprefix(X)
            for bound in ('minOccurs', 'maxOccurs'):
                value = node.get(bound)
                if value is not None and not (bound == 'maxOccurs' and value == 'unbounded') and (not value.isdigit()):
                    raise ValueError(f'{path.name}: invalid {bound}')
            if node.get('maxOccurs', '1') != 'unbounded' and int(node.get('minOccurs', '1')) > int(node.get('maxOccurs', '1')):
                raise ValueError(f'{path.name}: minOccurs exceeds maxOccurs')
            if kind in {'redefine', 'override'}:
                raise ValueError(f'{path.name}: unsupported xs:{kind}; no partial ontology was generated')
            if kind in {'list', 'union', 'pattern', 'minInclusive', 'maxInclusive', 'minExclusive', 'maxExclusive', 'length', 'minLength', 'maxLength', 'totalDigits', 'fractionDigits', 'enumeration', 'unique', 'key', 'keyref', 'any', 'anyAttribute', 'assert', 'alternative'}:
                diagnostics.add(f'xs:{kind} is retained in source but is not fully represented by generated OWL/SHACL constraints')
            if kind == 'import' and not node.get('schemaLocation'):
                diagnostics.add('Namespace-only imports require separately supplied schema resolution; their semantics are not fully resolved')
            if kind == 'choice':
                diagnostics.add('XSD choices preserve property ranges; nested and repeating compositor semantics require source XSD validation and are not fully enforced by generated SHACL')
            if kind in {'element', 'attribute'} and node.get('ref') and not node.get('type'):
                diagnostics.add('Referenced global declarations require QName resolution; unresolved property types are omitted by strict conversion')
    return sorted(diagnostics)


def qualify_schema_types(roots, contexts, namespaces):
    # The translator uses local names internally. Qualify ambiguous user types
    # before translation, while resolving each QName in its original XML scope.
    import hashlib
    declarations = {}
    for path, root in roots.items():
        for declaration in root:
            if declaration.tag in {X+'complexType', X+'simpleType', X+'element'} and declaration.get('name'):
                declaration.set('{urn:pmem:conversion}sourceNamespace', namespaces[path])
                declaration.set('{urn:pmem:conversion}sourceName', declaration.get('name'))
    for path, root in roots.items():
        for node in root:
            if node.tag in {X+'complexType', X+'simpleType'} and node.get('name'):
                declarations.setdefault(node.get('name'), set()).add(namespaces[path])
    qualified = {(ns, name): 'ns_' + hashlib.sha256(ns.encode()).hexdigest()[:16] + '_' + name
                 for name, owners in declarations.items() for ns in owners
                 if len(owners) > 1 or name in {
                     'anyType', 'anySimpleType', 'anyAtomicType', 'string', 'boolean', 'decimal', 'float', 'double',
                     'duration', 'dateTime', 'dateTimeStamp', 'time', 'date', 'gYearMonth', 'gYear', 'gMonthDay', 'gDay', 'gMonth',
                     'hexBinary', 'base64Binary', 'anyURI', 'QName', 'NOTATION', 'normalizedString', 'token', 'language',
                     'NMTOKEN', 'NMTOKENS', 'Name', 'NCName', 'ID', 'IDREF', 'IDREFS', 'ENTITY', 'ENTITIES', 'integer',
                     'nonPositiveInteger', 'negativeInteger', 'long', 'int', 'short', 'byte', 'nonNegativeInteger',
                     'unsignedLong', 'unsignedInt', 'unsignedShort', 'unsignedByte', 'positiveInteger',
                     'yearMonthDuration', 'dayTimeDuration'
                 }}
    for path, root in roots.items():
        for node in root.iter():
            for attribute in ('type', 'base', 'memberTypes', 'itemType'):
                if not node.get(attribute):
                    continue
                converted = []
                for value in node.get(attribute).split():
                    scope = contexts[id(node)]
                    if ':' in value:
                        prefix, local = value.split(':', 1)
                        if prefix not in scope:
                            raise ValueError(f'Unbound type prefix: {prefix}')
                        ns = scope[prefix]
                    else:
                        local, ns = value, scope.get('', '')
                    converted.append(qualified.get((ns, local), value))
                node.set(attribute, ' '.join(converted))
        for declaration in root:
            if declaration.tag in {X+'complexType', X+'simpleType'}:
                key = (namespaces[path], declaration.get('name'))
                if key in qualified:
                    declaration.set('name', qualified[key])

    element_owners = {}
    for path, root in roots.items():
        for element in root.findall(X+'element'):
            if element.get('name'):
                element_owners.setdefault(element.get('name'), set()).add(namespaces[path])
    element_names = {(ns, name): 'element_' + hashlib.sha256(ns.encode()).hexdigest()[:16] + '_' + name
                     for name, owners in element_owners.items() for ns in owners
                     if len(owners) > 1 or ns in declarations.get(name, set())}
    for path, root in roots.items():
        for node in root.iter(X+'element'):
            for attr in ('ref', 'substitutionGroup'):
                ref = node.get(attr)
                if not ref:
                    continue
                scope = contexts[id(node)]
                if ':' in ref:
                    prefix, local = ref.split(':', 1)
                    if prefix not in scope:
                        raise ValueError(f'Unbound element prefix: {prefix}')
                    ns = scope[prefix]
                else:
                    local, ns = ref, scope.get('', '')
                node.set(attr, element_names.get((ns, local), ref))
        for element in root.findall(X+'element'):
            key = (namespaces[path], element.get('name'))
            if key in element_names:
                element.set('name', element_names[key])


def expand_model_groups(paths):
    """Resolve model-group QNames across the selected schema closure in memory.

    Source files remain untouched. Reference occurrence bounds stay on a
    sequence wrapper so nested group and compositor bounds multiply correctly.
    """
    roots, contexts, groups, attribute_groups = {}, {}, {}, {}
    for path in paths:
        content = path.read_bytes()
        probe = content.replace(b'\x00', b'').upper()
        if b'<!DOCTYPE' in probe or b'<!ENTITY' in probe:
            raise ValueError('DOCTYPE/entities are not permitted in conversion schemas')
        scopes, pending, root = [{}], {}, None
        for event, item in ET.iterparse(io.BytesIO(content), events=('start-ns', 'start', 'end')):
            if event == 'start-ns':
                pending[item[0]] = item[1]
            elif event == 'start':
                scope = {**scopes[-1], **pending}
                pending = {}
                scopes.append(scope)
                if root is None:
                    root = item
                contexts[id(item)] = scope
            else:
                scopes.pop()
        roots[path] = root
        if root is None or root.tag != X+'schema':
            raise ValueError(f'{path.name}: expected an XML Schema root')

    # Chameleon includes inherit the including schema's target namespace.
    by_path = {path.resolve(): path for path in roots}
    namespaces = {path: root.get('targetNamespace', '') for path, root in roots.items()}
    for _ in range(len(roots)):
        changed = False
        for path, root in roots.items():
            for include in root.findall(X+'include'):
                location = include.get('schemaLocation')
                if not location:
                    raise ValueError(f'{path.name}: include requires schemaLocation')
                dependency = by_path.get((path.parent / location).resolve())
                if dependency is None:
                    raise ValueError(f'{path.name}: missing included schema dependency')
                declared = roots[dependency].get('targetNamespace', '')
                owner_namespace = namespaces[path]
                if declared and declared != owner_namespace and (owner_namespace or root.get('targetNamespace') is not None):
                    raise ValueError(f'{path.name}: included schema has a different targetNamespace')
                if not declared and owner_namespace:
                    if namespaces[dependency] and namespaces[dependency] != owner_namespace:
                        raise ValueError('A chameleon schema included into multiple namespaces requires separate conversion contexts')
                    if namespaces[dependency] != owner_namespace:
                        namespaces[dependency] = owner_namespace
                        changed = True
        if not changed:
            break
    qualify_schema_types(roots, contexts, namespaces)

    for path, root in roots.items():
        namespace = namespaces[path]
        for group in root.findall(X + 'group'):
            key = (namespace, group.get('name'))
            if not key[1] or key in groups:
                raise ValueError(f'{path.name}: duplicate or unnamed model group')
            groups[key] = group

    for path, root in roots.items():
        for group in root.findall(X+'attributeGroup'):
            key = (namespaces[path], group.get('name'))
            if not key[1] or key in attribute_groups:
                raise ValueError(f'{path.name}: duplicate or unnamed attribute group')
            attribute_groups[key] = group

    def attributes(node, namespace, stack, budget):
        ref = node.get('ref')
        scope = contexts[id(node)]
        if not ref:
            raise ValueError('Attribute group use requires a ref')
        if ':' in ref:
            prefix, name = ref.split(':', 1)
            if prefix not in scope:
                raise ValueError(f'Unbound attribute group prefix: {prefix}')
            key = (scope[prefix], name)
        else:
            key = (scope.get('', namespace), ref)
        marker = ('attributeGroup', *key)
        if marker in stack:
            raise ValueError(f'Cyclic attribute group reference: {ref}')
        if len(stack) > 64:
            raise ValueError('Attribute group expansion exceeds the supported complexity limit')
        declaration = attribute_groups.get(key)
        if declaration is None:
            raise ValueError(f'Unresolved attribute group reference: {ref}; supply its schema dependency')
        result = []
        for child in declaration:
            if child.tag == X+'annotation':
                continue
            if child.tag == X+'attributeGroup':
                result.extend(attributes(child, key[0], (*stack, marker), budget))
            elif child.tag in {X+'attribute', X+'anyAttribute'}:
                result.append(clone(child, key[0], (*stack, marker), budget))
            else:
                raise ValueError(f'Invalid attribute group declaration: {ref}')
        return result

    def clone(node, namespace, stack=(), budget=None):
        budget = budget if budget is not None else [0]
        budget[0] += 1
        if budget[0] > 1000000 or len(stack) > 64:
            raise ValueError('Model group expansion exceeds the supported complexity limit')
        if node.tag == X + 'group' and node.get('ref'):
            ref = node.get('ref')
            scope = contexts[id(node)]
            if ':' in ref:
                prefix, name = ref.split(':', 1)
                if prefix not in scope:
                    raise ValueError(f'Unbound model group prefix: {prefix}')
                key = (scope[prefix], name)
            else:
                key = (scope.get('', namespace), ref)
            if key in stack:
                raise ValueError(f'Cyclic model group reference: {ref}')
            declaration = groups.get(key)
            if declaration is None:
                raise ValueError(f'Unresolved model group reference: {ref}; supply its schema dependency')
            particle = [child for child in declaration if child.tag != X + 'annotation']
            if len(particle) != 1 or particle[0].tag not in {X+'sequence', X+'choice', X+'all'}:
                raise ValueError(f'Invalid model group declaration: {ref}')
            wrapper = ET.Element(X + 'sequence', {bound: node.get(bound, '1') for bound in ('minOccurs', 'maxOccurs')})
            wrapper.append(clone(particle[0], key[0], (*stack, key), budget))
            return wrapper
        result = ET.Element(node.tag, dict(node.attrib))
        result.text, result.tail = node.text, node.tail
        for child in node:
            # Declarations are expanded only at their use sites.
            if child.tag in {X+'group', X+'attributeGroup'} and child.get('name'):
                continue
            if child.tag == X+'attributeGroup':
                result.extend(attributes(child, namespace, stack, budget))
            else:
                result.append(clone(child, namespace, stack, budget))
        return result

    return {path: clone(root, namespaces[path]) for path, root in roots.items()}


def element_particles(node, minimum=1, maximum=1):
    """Yield owned elements with compositor occurrence bounds preserved."""
    for child in node:
        if child.tag == X + 'complexType':
            continue
        if child.tag == X + 'choice':
            # A branch is optional individually; the choice group is validated separately.
            branches = [branch for branch in child if branch.tag != X+'annotation']
            lo = minimum * int(child.get('minOccurs', '1')) if len(branches) == 1 else 0
            hi = _upper_bound(maximum, child.get('maxOccurs', '1'))
            yield from element_particles(child, lo, hi)
        elif child.tag in {X + 'sequence', X + 'all'}:
            lo = minimum * int(child.get('minOccurs', '1'))
            hi = _upper_bound(maximum, child.get('maxOccurs', '1'))
            yield from element_particles(child, lo, hi)
        elif child.tag == X + 'element':
            lo = minimum * int(child.get('minOccurs', '1'))
            hi = _upper_bound(maximum, child.get('maxOccurs', '1'))
            yield child, str(lo), 'unbounded' if hi is None else str(hi)
        else:
            yield from element_particles(child, minimum, maximum)


def _upper_bound(parent, declared):
    child = None if declared == 'unbounded' else int(declared)
    if parent == 0 or child == 0:
        return 0
    return None if parent is None or child is None else parent * child


def consolidated_element_particles(node):
    """Avoid intersecting separate occurrence limits on one RDF property.

    RDF collapses repeated occurrences to a property path. Sum their bounds;
    choice alternatives may produce a conservative upper bound, not an XSD
    conformance constraint. Conflicting declarations require reviewed mapping.
    """
    rows = {}
    for element, low, high in element_particles(node):
        identity = element.get('name') or element.get('ref')
        if identity not in rows:
            rows[identity] = [element, int(low), None if high == 'unbounded' else int(high)]
            continue
        previous, minimum, maximum = rows[identity]
        signature = lambda value: (value.get('type'), value.get('ref'), value.get('nillable', 'false'), value.get('fixed'), value.get('default'), tuple(ET.tostring(child) for child in value if child.tag in {X+'complexType', X+'simpleType'}))
        if signature(previous) != signature(element):
            raise ValueError(f'Repeated property {identity} has conflicting declarations; review schema mapping')
        rows[identity][1] = minimum + int(low)
        rows[identity][2] = None if maximum is None or high == 'unbounded' else maximum + int(high)
    for element, low, high in rows.values():
        yield element, str(low), 'unbounded' if high is None else str(high)
