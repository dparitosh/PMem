"""Validate uploaded schema paths before conversion or artifact writes."""
from pathlib import PurePosixPath, PureWindowsPath
from backend.depo_platform.upload_limits import ontology_upload_limit
import posixpath
from defusedxml import ElementTree as ET
from urllib.parse import urlsplit, unquote


def validate_schema_upload(filename: str, content: bytes, dependencies=None, *, require_dependencies=True) -> dict[str, bytes]:
    if (not isinstance(filename, str) or not filename or filename in {'.', '..'}
            or '/' in filename or '\\' in filename or ':' in filename or '\x00' in filename
            or PureWindowsPath(filename).is_absolute()):
        raise ValueError('Source filename must be a plain filename without path components')
    if dependencies is None:
        dependencies = {}
    if not isinstance(dependencies, dict) or len(dependencies) > 63:
        raise ValueError('schema_files must contain at most 63 local XSD dependencies')
    if dependencies and not filename.lower().endswith('.xsd'):
        raise ValueError('Companion schemas require an XSD root')
    total = len(content)
    seen = {filename.casefold()}
    for name, data in dependencies.items():
        if not isinstance(name, str) or not isinstance(data, bytes):
            raise ValueError('Schema dependencies require relative names and byte content')
        path = PurePosixPath(name)
        if (path.is_absolute() or ':' in name or '\\' in name or '\x00' in name
                or any(part in {'', '.', '..'} for part in name.split('/'))
                or any(char in name for char in '%?#') or path.suffix.lower() != '.xsd'
                or path.as_posix().casefold() in seen):
            raise ValueError('Schema dependency must be a distinct relative XSD path')
        seen.add(path.as_posix().casefold())
        total += len(data)
    if (dependencies or filename.lower().endswith('.xsd')) and total > min(25 * 1024 * 1024, ontology_upload_limit()):
        raise ValueError('Schema dependency closure exceeds configured ontology/schema-set limit')
    if filename.lower().endswith('.xsd'):
        uploaded = {filename, *dependencies}
        for name, data in {filename: content, **dependencies}.items():
            try:
                root = ET.fromstring(data)
            except Exception as exc:
                raise ValueError(f'{name}: malformed or unsafe XML Schema; check the source file before retrying') from exc
            if root.tag != '{http://www.w3.org/2001/XMLSchema}schema':
                raise ValueError(f'{name}: expected an XML Schema root')
            if not require_dependencies:
                continue
            for element in root.iter():
                if element.tag not in {'{http://www.w3.org/2001/XMLSchema}' + tag for tag in ('include', 'import', 'redefine')}:
                    continue
                location = element.get('schemaLocation')
                if not location:
                    continue
                uri = urlsplit(location)
                if uri.scheme or uri.netloc:
                    companion = PurePosixPath(unquote(uri.path)).name
                    hint = f" Upload '{companion}' as a companion schema and change schemaLocation to its relative uploaded path." if companion.lower().endswith('.xsd') else ' Supply the dependency as a local companion XSD and use its relative uploaded path.'
                    raise ValueError(f'{name}: external schemaLocation is not fetched during upload.' + hint)
                if uri.query or uri.fragment or '%' in location:
                    raise ValueError(f'{name}: schemaLocation must use a literal relative XSD path without URI encoding, query or fragment')
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), location))
                if (':' in location or '\\' in location or location.startswith('/')
                        or resolved == '..' or resolved.startswith('../')):
                    raise ValueError(f'{name}: schemaLocation escapes the uploaded schema set or uses a Windows filesystem path. Upload the companion XSD with its relative folder structure and use a relative path inside that set; absolute paths and external files are not allowed.')
                if resolved not in uploaded:
                    raise ValueError(f"{name}: missing schema dependency '{resolved}'. Upload this companion XSD using that exact relative path before retrying.")
    return dependencies
