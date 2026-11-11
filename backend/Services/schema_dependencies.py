"""Resolve an XSD closure once, then run conversion entirely from local bytes.

Supplied companion files win over network reads. Remote requests never carry
application credentials, use a pinned public address, and obey closure budgets.
QName prefixes in schema attributes must survive rewriting (use lxml, not ET).
"""
from __future__ import annotations

import hashlib
import http.client
import ipaddress
import os
import posixpath
import socket
import time
from urllib.parse import urljoin, urlsplit, unquote

from lxml import etree

from .schema_upload_paths import validate_schema_upload
from backend.depo_platform.upload_limits import ontology_upload_limit

XSD = '{http://www.w3.org/2001/XMLSchema}'
LINKS = {XSD + name for name in ('include', 'import', 'redefine')}
MAX_FILE = 5 * 1024 * 1024


def _public_address(url):
    uri = urlsplit(url)
    if (uri.scheme not in {'http', 'https'} or not uri.hostname or uri.username
            or uri.password or uri.fragment or uri.port not in {None, 80, 443}
            or any(char.isspace() for char in url)):
        raise ValueError('Remote schema requires a public HTTP(S) URL without credentials or fragment')
    allowed = {host.strip().lower() for host in os.getenv('XSD_REMOTE_SCHEMA_HOSTS', '').split(',') if host.strip()}
    if allowed and uri.hostname.lower() not in allowed:
        raise ValueError('Remote schema host is not in XSD_REMOTE_SCHEMA_HOSTS')
    port = uri.port or (443 if uri.scheme == 'https' else 80)
    addresses = socket.getaddrinfo(uri.hostname, port, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError('Remote schemas cannot address private, loopback or reserved networks')
    return uri, port, addresses[0][4][0]


def _download(url, remaining, deadline):
    if os.getenv('XSD_REMOTE_SCHEMA_ENABLED', 'true').lower() not in {'true', '1', 'yes'}:
        raise ValueError('Remote schema fetching is disabled; supply the referenced companion XSD')
    for _ in range(4):
        if time.monotonic() >= deadline:
            raise ValueError('Remote schema dependency resolution exceeded 60 seconds')
        uri, port, address = _public_address(url)
        timeout = max(0.1, min(10, deadline - time.monotonic()))
        cls = http.client.HTTPSConnection if uri.scheme == 'https' else http.client.HTTPConnection
        connection = cls(uri.hostname, port, timeout=timeout)
        # Connect to the validated address without another DNS lookup. HTTPS
        # retains the original hostname for certificate validation and SNI.
        connection._create_connection = lambda target, timeout, source_address=None: socket.create_connection((address, port), timeout, source_address)
        try:
            request_path = (uri.path or '/') + ('?' + uri.query if uri.query else '')
            connection.request('GET', request_path,
                               headers={'Accept': 'application/xml, text/xml', 'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader('Location')
                if not location:
                    raise ValueError('Remote schema redirect has no destination')
                redirected = urljoin(url, location)
                if uri.scheme == 'https' and urlsplit(redirected).scheme != 'https':
                    raise ValueError('Remote schema redirect cannot downgrade HTTPS')
                url = redirected
                continue
            if response.status != 200:
                raise ValueError(f'Remote schema returned HTTP {response.status}; supply a local companion XSD')
            limit = min(MAX_FILE, remaining)
            chunks, size = [], 0
            while True:
                if time.monotonic() >= deadline:
                    raise ValueError('Remote schema dependency resolution exceeded 60 seconds')
                chunk = response.read1(min(65536, limit - size + 1))
                if not chunk:
                    return b''.join(chunks), url
                size += len(chunk)
                if size > limit:
                    raise ValueError('Remote schema exceeds the 5 MiB file or 25 MiB closure limit')
                chunks.append(chunk)
        finally:
            connection.close()
    raise ValueError('Remote schema exceeded three redirects')


def _parse(data, name):
    try:
        root = etree.fromstring(data, etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False))
        if root.getroottree().docinfo.doctype or root.tag != XSD + 'schema':
            raise ValueError()
        return root
    except (etree.XMLSyntaxError, ValueError) as exc:
        raise ValueError(f'{name}: expected a safe XML Schema without DTD/entities') from exc


def resolve_schema_dependencies(filename, content, dependencies=None):
    """Return a validated, portable root and dependency map; no caller mutation."""
    dependencies = validate_schema_upload(filename, content, dependencies, require_dependencies=False)
    if not filename.lower().endswith('.xsd'):
        return content, dependencies
    files = {filename: content, **dependencies}
    documents = {name: _parse(data, name) for name, data in files.items()}
    origins, urls, changed = {}, {}, set()
    pending = list(files)
    deadline = time.monotonic() + 60
    budget = min(25 * 1024 * 1024, ontology_upload_limit())
    while pending:
        name = pending.pop(0)
        root = documents[name]
        for link in root:
            if link.tag not in LINKS or not link.get('schemaLocation'):
                continue
            location = link.get('schemaLocation').strip()
            remote = urlsplit(location).scheme in {'http', 'https'}
            if not remote and name not in origins:
                continue  # existing strict relative-path validator handles local links
            url = urljoin(origins[name], location) if name in origins else location
            if urlsplit(url).scheme not in {'http', 'https'}:
                raise ValueError('Unsupported remote schema URL scheme')
            basename = posixpath.basename(unquote(urlsplit(url).path))
            expected = link.get('namespace', '') if link.tag == XSD + 'import' else root.get('targetNamespace', '')
            local = [path for path in documents if path not in origins and posixpath.basename(path) == basename]
            candidates = [path for path in local
                          if (documents[path].get('targetNamespace', '') == expected or
                              (link.tag != XSD + 'import' and not documents[path].get('targetNamespace')))]
            if local and not candidates:
                raise ValueError(f'{name}: supplied companion namespace does not match {basename}')
            if len(candidates) > 1:
                raise ValueError(f'{name}: ambiguous local companion {basename}; select one matching schema')
            target = candidates[0] if candidates else urls.get(url)
            if not target:
                if len(files) >= 64:
                    raise ValueError('Schema dependency closure exceeds 64 files')
                target = '_remote/' + hashlib.sha256(url.encode()).hexdigest() + '.xsd'
                if target in files:
                    raise ValueError('Remote schema path collides with an uploaded dependency')
                try:
                    data, final_url = _download(url, budget - sum(map(len, files.values())), deadline)
                except (OSError, http.client.HTTPException) as exc:
                    raise ValueError(f'{name}: remote schema {basename or "dependency"} could not be retrieved; supply a local companion XSD and retry') from exc
                documents[target] = _parse(data, basename or 'remote schema')
                files[target] = data
                origins[target] = final_url
                urls[url] = target
                urls.setdefault(final_url, target)
                pending.append(target)
            actual = documents[target].get('targetNamespace', '')
            if actual != expected and (link.tag == XSD + 'import' or actual):
                raise ValueError(f'{name}: remote companion namespace does not match {basename}')
            link.set('schemaLocation', posixpath.relpath(target, posixpath.dirname(name) or '.'))
            changed.add(name)
    for name in changed:
        files[name] = etree.tostring(documents[name], encoding='UTF-8', xml_declaration=True)
    root = files.pop(filename)
    validate_schema_upload(filename, root, files)
    return root, files
