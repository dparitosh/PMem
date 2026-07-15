"""Safety helpers for natural-language generated Cypher."""

from __future__ import annotations

import re


class UnsafeCypherError(ValueError):
    """Raised when a query is not provably read-only."""


_WRITE_CLAUSE = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|ALTER|RENAME|GRANT|DENY|REVOKE|FOREACH|LOAD\s+CSV)\b",
    re.IGNORECASE,
)


def _without_literals_and_comments(query: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", str(query or ""), flags=re.DOTALL)
    text = re.sub(r"//[^\r\n]*", " ", text)
    text = re.sub(r"'(?:\\.|''|[^'])*'", "''", text)
    text = re.sub(r'"(?:\\.|""|[^"])*"', '""', text)
    return text


def assert_read_only_cypher(query: str) -> str:
    """Return *query* when it is a single, read-only Cypher statement."""
    raw = str(query or "").strip()
    if not raw:
        raise UnsafeCypherError("Cypher query is empty")
    inspected = _without_literals_and_comments(raw)
    if ";" in inspected.rstrip(";"):
        raise UnsafeCypherError("Multiple Cypher statements are not allowed")
    if re.search(r"\bCALL\b", inspected, flags=re.IGNORECASE):
        raise UnsafeCypherError("Procedure calls are not allowed in generated Cypher")
    match = _WRITE_CLAUSE.search(inspected)
    if match:
        raise UnsafeCypherError(
            f"Generated Cypher must be read-only; blocked clause: {match.group(1).upper()}"
        )
    if not re.search(
        r"\b(MATCH|OPTIONAL\s+MATCH|RETURN|WITH|UNWIND)\b",
        inspected,
        flags=re.IGNORECASE,
    ):
        raise UnsafeCypherError("Generated Cypher does not contain a supported read clause")
    return raw