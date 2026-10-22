"""Bind recommendation investigations to the existing read-goal controller."""
TOOLS = {'change-impact': 'recommendation.change_impact',
         'similar-parts': 'recommendation.similar_parts',
         'manufacturing': 'recommendation.manufacturing'}
POLICY_STATES = {'not_configured', 'not_applicable', 'passed', 'blocked', 'unavailable'}


def selection(context):
    if 'recommendation_service' not in context:
        return None
    service = context['recommendation_service']
    name = context.get('recommendation_object')
    limit = context.get('recommendation_top_n', 10)
    if not isinstance(service, str) or service not in TOOLS:
        raise ValueError('Unknown recommendation analysis')
    if not isinstance(name, str) or not name.strip() or len(name) > 500:
        raise ValueError('Select a bounded recommendation object')
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError('Recommendation result limit must be 1 to 50')
    scope = {key: context[key] for key in ('ontology_id', 'ontology_prefix') if context.get(key)}
    if any(not isinstance(value, str) or len(value) > 256 for value in scope.values()):
        raise ValueError('Invalid recommendation scope')
    node = context.get('node_id', '')
    if not isinstance(node, str) or len(node) > 256:
        raise ValueError('Invalid recommendation identity')
    return {'service': service, 'tool_id': TOOLS[service], 'object': name.strip(),
            'top_n': limit, 'scope': scope, 'node_id': node}


def validate_read(context, tool_id, inputs):
    selected = selection(context)
    if not selected or not tool_id.startswith('recommendation.'):
        return
    key = 'change_name' if selected['service'] == 'change-impact' else 'part_name'
    if (tool_id != selected['tool_id'] or inputs.get(key) != selected['object']
            or inputs.get('scope', {}) != selected['scope']
            or inputs.get('node_id', '') != selected['node_id'] or inputs.get('element_id')):
        raise ValueError('Recommendation action changed the selected analysis, object or scope')
    if selected['service'] == 'similar-parts' and inputs.get('top_n', 10) != selected['top_n']:
        raise ValueError('Recommendation action changed the selected result limit')


def completion_evidence(context, observations, evidence_steps):
    selected = selection(context)
    if not selected:
        return None
    for observation in observations:
        result = observation.get('result')
        if (observation.get('id') not in evidence_steps or observation.get('status') != 'completed'
                or observation.get('tool_id') != selected['tool_id'] or not isinstance(result, dict)
                or result.get('truncated')):
            continue
        validate_read(context, observation['tool_id'], observation.get('inputs', {}))
        policy = result.get('decision_policy')
        if isinstance(policy, dict) and policy.get('status') in POLICY_STATES:
            return {'recommendation_observation_id': observation['id'],
                    'decision_policy_status': policy['status'], 'advisory_only': True}
    raise ValueError('Complete only after citing selected recommendation evidence with a policy assessment')
