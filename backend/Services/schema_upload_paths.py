"""Validate uploaded schema paths before conversion or artifact writes."""
from pathlib import PurePosixPath, PureWindowsPath
import posixpath
from defusedxml import ElementTree as ET


def validate_schema_upload(filename: str, content: bytes, dependencies=None) -> dict[str, bytes]:
    if (not isinstance(filename, str) or not filename or filename in {'.', '..'}
            or '/' in filename or '\\' in filename or ':' in filename or '\x00' in filename
            or PureWindowsPath(filename).is_absolute()):
        raise ValueError('Source filename must be a plain filename without path components')
    if dependencies is None:
        dependencies = {}
    if not isinstance(dependencies, dict) or len(dependencies) > 63:
        raise ValueError('schema_files must contain at most 63 local XSD dependencies')
    total = len(content)
    seen = {filename.casefold()}
    for name, data in dependencies.items():
        if not isinstance(name, str) or not isinstance(data, bytes):
            raise ValueError('Schema dependencies require relative names and byte content')
        path = PurePosixPath(name)
        if (path.is_absolute() or ':' in name or '\\' in name or '\x00' in name
                or '..' in path.parts or path.suffix.lower() != '.xsd'
                or path.as_posix().casefold() in seen):
            raise ValueError('Schema dependency must be a distinct relative XSD path')
        seen.add(path.as_posix().casefold())
        total += len(data)
    if dependencies and total > 25 * 1024 * 1024:
        raise ValueError('Schema dependency closure exceeds 25 MiB')
    if filename.lower().endswith('.xsd'):
        for name, data in {filename: content, **dependencies}.items():
            root = ET.fromstring(data)
            for element in root.iter():
                if element.tag not in {'{http://www.w3.org/2001/XMLSchema}' + tag for tag in ('include', 'import', 'redefine')}:
                    continue
                location = element.get('schemaLocation')
                if not location:
                    continue
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), location))
                if (':' in location or '\\' in location or location.startswith('/')
                        or resolved == '..' or resolved.startswith('../')):
                    raise ValueError('Schema dependency location must remain inside the uploaded schema set')
    return dependencies
