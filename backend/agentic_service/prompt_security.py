"""Bounded credential redaction and reproducible prompt identity."""
import hashlib
import os
import re

SECRET_KEYS = {'authorization', 'api_key', 'admin_api_key', 'password', 'secret', 'access_token', 'approval_token', 'subscription_key', 'ocp_apim_subscription_key', 'depo_database_url', 'database_url', 'neo4j_pass'}


def secret_key(key):
    key = str(key).lower().replace('-', '_')
    return key in SECRET_KEYS or key.endswith(('_token', '_api_key', '_password', '_secret'))


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
            item = re.sub(r'(?i)(\b(?:[a-z0-9_]*(?:api_key|password|secret|token)|authorization)\s*[:=]\s*)([^\s,;]+)', r'\1[REDACTED]', item)
            item = re.sub(r'(\w+://[^:/\s]+:)([^@/\s]+)(@)', r'\1[REDACTED]\3', item)
            return item
        return item
    return walk(value)


def prompt_identity(system):
    return {'system_prompt_sha256': hashlib.sha256(system.encode('utf-8')).hexdigest()}


def evidence_ids(evidence):
    identifiers = set()
    def visit(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {'elementId', 'id', 'resource_id', 'iri', 'source_id', 'artifact_id', 'run_id'} and isinstance(child, str) and child and len(child) <= 2000:
                    identifiers.add(child)
                elif isinstance(child, (dict, list)):
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(evidence)
    return sorted(identifiers)[:200]


def validate_summary(text, identifiers):
    citations = re.findall(r'\[evidence:([^\]\n]+)\]', text)
    if not identifiers or not citations or any(value not in identifiers for value in citations):
        raise ValueError('Companion summary requires citations to supplied evidence identifiers')
    return text
