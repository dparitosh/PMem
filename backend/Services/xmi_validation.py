"""Shared XMI identity and reference guards."""
XMI_NAMESPACES = {'http://www.omg.org/XMI', 'http://www.omg.org/XMI/',
                  'http://www.omg.org/spec/XMI/20110701', 'http://www.omg.org/spec/XMI/20131001',
                  'http://www.omg.org/spec/XMI/20161101'}


def xmi_attribute(element, name):
    if element is None:
        return ''
    for namespace in sorted(XMI_NAMESPACES):
        value = element.get(f'{{{namespace}}}{name}')
        if value:
            return value
    # Plain UML `type` is a referenced classifier, never the XMI metaclass.
    return '' if name == 'type' else element.get(name, '')


def local_reference(value):
    raw = str(value or '').strip()
    if '#' in raw:
        document, identifier = raw.rsplit('#', 1)
        if document:
            raise ValueError('External XMI references require a supplied model resolver; standalone import cannot resolve them')
        return identifier
    return raw


def validate_xmi_root(root):
    tag = str(root.tag)
    local = tag.rsplit('}', 1)[-1]
    namespace = tag[1:].split('}', 1)[0] if tag.startswith('{') else ''
    if not ((local == 'XMI' and namespace in XMI_NAMESPACES)
            or (local in {'Model', 'Package'} and 'UML' in namespace)):
        raise ValueError('The supplied XML is not a supported XMI/UML document')
    ids = set()
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        identifier = xmi_attribute(element, 'id')
        if identifier:
            if identifier in ids:
                raise ValueError(f'Duplicate XMI identifier: {identifier}')
            ids.add(identifier)
