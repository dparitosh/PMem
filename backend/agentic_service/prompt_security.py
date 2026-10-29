"""Bounded credential redaction and reproducible prompt identity."""
import hashlib
import os
import re

SECRET_KEYS = {'authorization', 'api_key', 'admin_api_key', 'password', 'secret', 'access_token', 'approval_token', 'subscription_key', 'ocp_apim_subscription_key', 'depo_database_url', 'database_url', 'neo4j_pass'}
SECRET_KEYS |= {'refresh_token', 'client_secret', 'connection_string'}
SECRET_KEYS |= {'token', 'private_key', 'credential', 'credentials'}
SECRET_COMPACT_KEYS = {key.replace('_', '') for key in SECRET_KEYS}


def secret_key(key):
    key = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', str(key)).lower().replace('-', '_')
    return key.replace('_', '') in SECRET_COMPACT_KEYS or key.endswith(('_token', '_api_key', '_password', '_secret', '_connection_string', '_pass'))


def protect(value):
    """Redact named credentials and known configured secrets before inference/storage."""
    secrets = sorted({item for key, item in os.environ.items() if secret_key(key) and len(item) >= 8}, key=len, reverse=True)
    def walk(item):
        if isinstance(item, dict):
            return {key: '[REDACTED]' if secret_key(key) else walk(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [walk(child) for child in item]
        if isinstance(item, str):
            for secret in secrets:
                item = item.replace(secret, '[REDACTED]')
            item = re.sub(r'(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*', 'Bearer [REDACTED]', item)
            item = re.sub(r'''(["'])([A-Za-z][A-Za-z0-9_-]*)\1(\s*:\s*)(?:"[^"]*"|'[^']*'|[^\s,;}]+)''',
                          lambda match: match[1] + match[2] + match[1] + match[3] + '"[REDACTED]"'
                          if secret_key(match[2]) else match[0], item)
            item = re.sub(r'(?i)(\b(?:[a-z0-9_]*(?:api_key|password|secret|token)|authorization)\s*[:=]\s*)([^\s,;]+)', r'\1[REDACTED]', item)
            item = re.sub(r'\b([A-Za-z][A-Za-z0-9_-]*)(\s*[:=]\s*)([^\s,;]+)',
                          lambda match: match[1] + match[2] + '[REDACTED]' if secret_key(match[1]) else match[0], item)
            item = re.sub(r'(\w+://[^:/\s]+:)([^@/\s]+)(@)', r'\1[REDACTED]\3', item)
            return item
        return item
    return walk(value)


def protect_schema(schema, sensitive=False):
    """Keep schema keywords/property names intact; redact annotation values.

    The original schema remains the execution validator's authority, never this
    model-visible projection. A property called password must remain a schema.
    """
    if isinstance(schema, dict):
        result = {}
        for key, value in schema.items():
            if sensitive and key in {'default', 'examples', 'example', 'enum', 'const', 'description', 'title'}:
                continue
            if key == 'properties' and isinstance(value, dict):
                result[key] = {name: protect_schema(definition, secret_key(name)) for name, definition in value.items()}
            else:
                result[key] = protect(value) if key in {'default', 'examples', 'example'} else protect_schema(value, sensitive)
        return result
    if isinstance(schema, list):
        return [protect_schema(value, sensitive) for value in schema]
    return protect(schema)


def citation_targets(item):
    """Citation aliases of one projected record, never arbitrary nested IDs."""
    if not isinstance(item, dict):
        return []
    properties = item.get('properties') or {}
    values = [item.get('resource_id'), item.get('elementId'), item.get('iri'),
              properties.get('iri') if isinstance(properties, dict) else None, item.get('source_id')]
    return list(dict.fromkeys(value for value in values if isinstance(value, str) and 0 < len(value) <= 2000))


def prompt_identity(system):
    return {'system_prompt_sha256': hashlib.sha256(system.encode('utf-8')).hexdigest()}


def evidence_ids(evidence):
    if isinstance(evidence, list):
        records = evidence
    elif isinstance(evidence, dict):
        records = [evidence] + [item for key in ('nodes', 'evidence')
                                for item in (evidence[key] if isinstance(evidence.get(key), list) else [])]
    else:
        records = []
    targets = [citation_targets(item) for item in records]
    # Reserve the owning record of every retained item before optional aliases.
    primary = [values[0] for values in targets if values]
    aliases = [value for values in targets for value in values[1:]]
    return list(dict.fromkeys(primary + aliases))[:200]


def validate_summary(text, identifiers):
    if re.search(r'<\/?[A-Za-z_][\w:.-]*(?:\s[^<>]*|\s*)/?>|```\s*(?:xml|json)\b|\b(?:minOccurs|maxOccurs)\s*=', text, re.I) or text.lstrip().startswith(('{','[')) and not text.lstrip().startswith('[evidence:'):
        raise ValueError('Companion business answers must not contain XML, JSON or schema serialization')
    citations = re.findall(r'\[evidence:([^\]\n]+)\]', text)
    if not identifiers or not citations or any(value not in identifiers for value in citations):
        raise ValueError('Companion summary requires citations to supplied evidence identifiers')
    for line in text.splitlines():
        if line.strip().startswith('|') and not re.fullmatch(r'[| :\-]+',line.strip()) and not re.search(r'\[evidence:([^\]\n]+)\]',line):
            # A header is non-factual; data rows must cite their supporting record.
            lines=text.splitlines();index=lines.index(line)
            if index+1>=len(lines) or not re.fullmatch(r'[| :\-]+',lines[index+1].strip()):
                raise ValueError('Every summary table row requires evidence citations')
    # Match the supported UI grammar, including numbered/Unicode list items and
    # separately rendered name:value facts. Tables are checked row by row above.
    for paragraph in re.split(r'\n\s*\n|\n(?=\s*(?:[-*•◦▪]\s|\d+[.)]\s|[A-Za-z][A-Za-z0-9 _/-]{1,36}:\s|#{1,3}\s|\|))',text):
        if not paragraph.strip() or re.fullmatch(r'\s*#{1,3}\s+[^\n]+',paragraph):continue
        if all(line.strip().startswith('|') for line in paragraph.splitlines() if line.strip()):continue
        if re.fullmatch(r'\s*---+\s*', paragraph):continue
        if not re.search(r'\[evidence:([^\]\n]+)\]',paragraph):
            raise ValueError('Every summary paragraph or list item requires evidence citations')
    return text
