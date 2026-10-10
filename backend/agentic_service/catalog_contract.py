"""Reject ambiguous agent identities and broken execution references at load time."""
SERVICES = {'agentic', 'ontology', 'graph', 'ingestion', 'oslc', 'qif', 'catalog', 'data_products', 'ceim', 'data_pipeline'}


def validate_catalog(data):
    if not isinstance(data, dict):
        raise ValueError('Catalog must be an object')
    groups = {}
    for kind in ('agents', 'tools', 'mcp_servers', 'workflows'):
        values = data.get(kind)
        if not isinstance(values, list):
            raise ValueError(f'Catalog {kind} must be a list')
        identities = {}
        for value in values:
            if not isinstance(value, dict) or not isinstance(value.get('id'), str) or not value['id'].strip():
                raise ValueError(f'Catalog {kind} entries need non-empty string identities')
            if value['id'] in identities:
                raise ValueError(f'Duplicate {kind} identity: {value["id"]}')
            identities[value['id']] = value
        groups[kind] = identities
    for tool in groups['tools'].values():
        if tool.get('transport') == 'openapi':
            if tool.get('service') not in SERVICES or tool.get('method') not in {'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'}:
                raise ValueError(f'Invalid HTTP tool: {tool["id"]}')
            if not isinstance(tool.get('path'), str) or not tool['path'].startswith('/'):
                raise ValueError(f'Invalid tool path: {tool["id"]}')
        elif tool.get('transport') == 'mcp':
            server = tool.get('server_id')
            if not isinstance(server, str) or server not in groups['mcp_servers']:
                raise ValueError(f'Invalid MCP server reference: {tool["id"]}')
        else:
            raise ValueError(f'Unsupported tool transport: {tool["id"]}')
    for agent in groups['agents'].values():
        prompt = agent.get('system_prompt')
        if prompt is not None and (not isinstance(prompt, str) or not prompt.strip() or len(prompt.encode('utf-8')) > 16384):
            raise ValueError(f'Invalid system prompt: {agent["id"]}')
        allowed = agent.get('tools')
        if not isinstance(allowed, list) or any(not isinstance(t, str) or t not in groups['tools'] for t in allowed):
            raise ValueError(f'Agent references invalid tools: {agent["id"]}')
        if len(allowed) != len(set(allowed)):
            raise ValueError(f'Agent has duplicate tools: {agent["id"]}')
    for workflow in groups['workflows'].values():
        steps = workflow.get('steps')
        if not isinstance(steps, list) or not steps:
            raise ValueError(f'Workflow requires steps: {workflow["id"]}')
        for step in steps:
            if not isinstance(step, dict) or not isinstance(step.get('agent_id'), str) or not isinstance(step.get('tool_id'), str):
                raise ValueError(f'Workflow has invalid step identities: {workflow["id"]}')
            agent = groups['agents'].get(step['agent_id'])
            if agent is None or step.get('tool_id') not in agent['tools']:
                raise ValueError(f'Workflow has an invalid agent/tool binding: {workflow["id"]}')
    return data
