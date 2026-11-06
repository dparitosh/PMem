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
    # Comments and strings must be recognized in one pass. Removing comments
    # first lets a URL or comment marker inside a string hide later clauses.
    text, output, index = str(query or ''), [], 0
    while index < len(text):
        if text.startswith('//',index):
            end=re.search(r'[\r\n]',text[index+2:])
            index=len(text) if end is None else index+2+end.start()
            output.append(' ')
        elif text.startswith('/*',index):
            end=text.find('*/',index+2)
            if end<0:raise UnsafeCypherError('Unterminated Cypher comment')
            index=end+2;output.append(' ')
        elif text[index] in {'\"',"'",'`'}:
            quote=text[index];index+=1;closed=False
            while index<len(text):
                if text[index]=='\\' and quote!='`':index+=2;continue
                if text[index]==quote:
                    if index+1<len(text) and text[index+1]==quote:index+=2;continue
                    index+=1;closed=True;break
                index+=1
            if not closed:raise UnsafeCypherError('Unterminated Cypher literal or identifier')
            output.append(' ')
        else:
            output.append(text[index]);index+=1
    return ''.join(output)


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
