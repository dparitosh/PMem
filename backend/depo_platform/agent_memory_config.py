"""Shared, dependency-free validation for optional agent memory."""
import os
import re


def enabled():
    flag = os.getenv('AGENT_MEMORY_ENABLED', 'false').strip().lower()
    if flag not in {'true', 'false'}:
        raise ValueError('AGENT_MEMORY_ENABLED')
    return flag == 'true'


def scope():
    value = os.getenv('AGENT_MEMORY_SCOPE', '').strip()
    if not value:
        tenant = os.getenv('DEPO_TENANT_ID', '').strip()
        project = os.getenv('DEPO_PROJECT_ID', '').strip()
        if tenant and project:
            if not all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', part) for part in (tenant, project)):
                raise ValueError('AGENT_MEMORY_SCOPE')
            value = f'{tenant}:{project}'
        elif enabled():
            raise ValueError('AGENT_MEMORY_SCOPE')
        else:
            return 'default:project'
    if len(value) > 256 or any(char in value for char in '<>') or any(ord(char) < 32 for char in value):
        raise ValueError('AGENT_MEMORY_SCOPE')
    return value


def query_timeout():
    try:
        value = int(os.getenv('AGENT_MEMORY_QUERY_TIMEOUT', '5'))
    except ValueError:
        raise ValueError('AGENT_MEMORY_QUERY_TIMEOUT') from None
    if not 1 <= value <= 30:
        raise ValueError('AGENT_MEMORY_QUERY_TIMEOUT')
    return value
