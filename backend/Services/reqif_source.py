"""Bounded ReqIF/ReqIFZ decoding shared by both import paths."""
import io
import zipfile


def reqif_xml(content: bytes, max_bytes: int = 25 * 1024 * 1024) -> bytes:
    if not content or len(content) > max_bytes:
        raise ValueError('ReqIF source is empty or exceeds the byte limit')
    if content[:2] == b'PK':
        try:
            archive_file = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile as exc:
            raise ValueError('ReqIFZ archive is invalid') from exc
        with archive_file as archive:
            entries = archive.infolist()
            if len(entries) > 1000 or sum(item.file_size for item in entries) > max_bytes:
                raise ValueError('ReqIFZ archive exceeds the entry or expanded-byte limit')
            members = [item for item in entries if not item.is_dir() and item.filename.lower().endswith('.reqif')]
            if not members:
                members = [item for item in entries if not item.is_dir() and item.filename.lower().endswith('.xml')]
            if len(members) != 1:
                raise ValueError('ReqIFZ must contain exactly one ReqIF document; import multiple documents separately')
            with archive.open(members[0]) as stream:
                content = stream.read(max_bytes + 1)
            if len(content) > max_bytes:
                raise ValueError('ReqIFZ document exceeds the expanded-byte limit')
    if b'<!DOCTYPE' in content.replace(b'\x00', b'').upper() or b'<!ENTITY' in content.replace(b'\x00', b'').upper():
        raise ValueError('ReqIF DTD and entity declarations are not supported')
    return content


def parse_reqif(content: bytes):
    from defusedxml import ElementTree as ET
    try:
        root = ET.fromstring(reqif_xml(content))
    except ET.ParseError as exc:
        raise ValueError('ReqIF XML is invalid') from exc
    if root.tag not in {'REQ-IF', '{http://www.omg.org/spec/ReqIF/20110401/reqif.xsd}REQ-IF'}:
        raise ValueError('The supplied XML is not a supported ReqIF document')
    identifiers = set()
    for element in root.iter():
        identifier = element.get('IDENTIFIER')
        kind = str(element.tag).rsplit('}', 1)[-1]
        if kind in {'SPEC-OBJECT', 'SPECIFICATION', 'SPEC-RELATION', 'SPEC-HIERARCHY'} and not str(identifier or '').strip():
            raise ValueError(f'ReqIF {kind} requires an IDENTIFIER')
        if identifier:
            if identifier in identifiers:
                raise ValueError(f'ReqIF duplicate IDENTIFIER: {identifier}')
            identifiers.add(identifier)
    return root
