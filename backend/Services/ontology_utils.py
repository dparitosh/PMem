"""Common ontology helper functions shared across parser engines."""

from __future__ import annotations

import re
from typing import Any

from rdflib import URIRef
from rdflib.namespace import XSD


def local_name(name: str) -> str:
    """Strip XML namespace/prefix and return the local token."""
    text = str(name)
    if "}" in text:
        return text.split("}", 1)[1]
    if ":" in text:
        return text.split(":", 1)[1]
    return text


def safe_fragment(name: str, allow_dot: bool = False) -> str:
    """Convert arbitrary text into a URI-safe local name fragment."""
    pattern = r"[^A-Za-z0-9_\-.]" if allow_dot else r"[^A-Za-z0-9_\-]"
    return re.sub(pattern, "_", str(name))


def safe_local_fragment(name: str, allow_dot: bool = False) -> str:
    """Combine local-name extraction with URI fragment sanitization."""
    return safe_fragment(local_name(name), allow_dot=allow_dot)


def clean_label(name: str) -> str:
    """Normalize labels by removing leading punctuation/whitespace noise."""
    text = str(name).strip()
    while text.startswith((".", "_", " ")):
        text = text[1:]
    return text or str(name)


def infer_scalar_xsd(value: Any) -> URIRef:
    """Best-effort scalar datatype mapping for literal values."""
    if isinstance(value, bool):
        return XSD.boolean
    if isinstance(value, int):
        return XSD.integer
    if isinstance(value, float):
        return XSD.decimal
    return XSD.string


JSON_TYPE_MAP = {
    "string": XSD.string,
    "boolean": XSD.boolean,
    "integer": XSD.integer,
    "number": XSD.decimal,
    "null": XSD.string,
}


XSD_NAME_MAP = {
    "xsd_string": XSD.string,
    "xsd_boolean": XSD.boolean,
    "xsd_integer": XSD.integer,
    "xsd_decimal": XSD.decimal,
    "xsd_float": XSD.float,
    "xsd_double": XSD.double,
    "xsd_date": XSD.date,
    "xsd_dateTime": XSD.dateTime,
    "xsd_time": XSD.time,
    "xsd_language": XSD.language,
    "xsd_normalizedString": XSD.normalizedString,
    "xsd_token": XSD.token,
    "xsd_base64Binary": XSD.base64Binary,
    "xsd_anyURI": XSD.anyURI,
}