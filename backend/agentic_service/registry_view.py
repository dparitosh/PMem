"""Safe discovery projection of one validated catalog snapshot."""
import hashlib
import json

from .agent_usage import describe
from .prompt_security import protect


def registry_view(source):
    digest = hashlib.sha256(json.dumps(source, sort_keys=True, ensure_ascii=False,
                                      allow_nan=False, separators=(',', ':')).encode('utf-8')).hexdigest()
    tools = [{key: tool[key] for key in ('id', 'name', 'description', 'transport', 'service', 'method', 'path',
                                       'mutates', 'server_id', 'input_kind') if key in tool}
             for tool in source['tools']]
    servers = [{key: server[key] for key in ('id', 'name', 'description', 'transport') if key in server}
               for server in source['mcp_servers']]
    workflows = []
    for workflow in source['workflows']:
        public = {key: workflow[key] for key in ('id', 'name', 'description') if key in workflow}
        public['steps'] = [{key: step[key] for key in ('agent_id', 'tool_id', 'approval_required') if key in step}
                           for step in workflow['steps']]
        if isinstance(workflow.get('governance'), dict):
            public['governance'] = {key: workflow['governance'][key] for key in
                                    ('status', 'version', 'approved_by', 'evaluation_sha256') if key in workflow['governance']}
        workflows.append(public)
    return protect({'registry': {'schema_version': 1, 'revision': digest,
                                'source': 'validated deployment catalog', 'readiness': 'not_verified',
                                'agent_count': len(source['agents']), 'tool_count': len(tools),
                                'workflow_count': len(source['workflows'])},
                    'agents': describe(source), 'tools': tools,
                    'workflows': workflows, 'mcp_servers': servers})
