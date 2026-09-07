"""Entry-point registration contract for hosts: register_tool(id, callable)."""
import os
import httpx

TOOLS = {
    'cameo.template': ('GET', '/cameo-mdk/template'),
    'cameo.validate': ('POST', '/cameo-mdk/validate'),
    'mbse.import': ('POST', '/imports'),
    'mbse.visualize': ('POST', '/visualization'),
    'smw.template': ('GET', '/teamcenter-smw/template'),
    'smw.preview': ('POST', '/teamcenter-smw/preview'),
}


def invoke(tool, payload):
    if tool not in TOOLS:
        raise ValueError('Unknown MBSE tool')
    method, path = TOOLS[tool]
    response = httpx.request(method, os.environ['MBSE_PLUGIN_URL'].rstrip('/') + path,
        **({'json': payload} if method == 'POST' else {}), headers={'Authorization': 'Bearer ' + os.environ['MBSE_PLUGIN_TOKEN']}, timeout=130)
    response.raise_for_status()
    return response.json()


def register(registry):
    from functools import partial
    for tool in TOOLS:
        registry.register_tool(tool, partial(invoke, tool))
