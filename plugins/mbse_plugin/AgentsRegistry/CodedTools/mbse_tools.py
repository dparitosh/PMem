"""IIF-callable HTTP tool; host registration is explicit."""


def invoke_mbse_tool(tool: str, payload: dict) -> dict:
    from mbse_plugin.registration import invoke
    return invoke(tool, payload)
