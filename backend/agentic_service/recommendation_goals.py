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


def bound_inputs(context):
    """User-selected read inputs are controller state, not model-generated text."""
    chosen = selection(context)
    if not chosen: raise ValueError('No recommendation was selected')
    result = {'change_name' if chosen['service'] == 'change-impact' else 'part_name': chosen['object'],
              'scope': chosen['scope']}
    if chosen['node_id']: result['node_id'] = chosen['node_id']
    if chosen['service'] == 'similar-parts': result['top_n'] = chosen['top_n']
    return result


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
            def names(key, eligible_only=False):
                rows = result.get(key)
                if not isinstance(rows, list):
                    return []
                if eligible_only:
                    rows = [row for row in rows if isinstance(row, dict) and not row.get('conflicts') and row.get('compatibility') != 'conflicting_evidence']
                return list(dict.fromkeys(str(row.get('name') or row.get('process_name') or '').strip()
                    for row in rows if isinstance(row, dict) and (row.get('name') or row.get('process_name'))))[:5]

            if selected['service'] == 'change-impact':
                affected = list(dict.fromkeys(names('assembly_impact') + names('process_impacts') + names('impacted_requirements') + names('impacted_parts')))
                if affected:
                    summary = 'CO recommendation: include ' + ', '.join(affected[:8]) + ' in the change review for ' + selected['object'] + '. Confirm the applicable revisions and effective configuration before release.'
                else:
                    summary = 'CO recommendation: hold release for ' + selected['object'] + '. No affected assembly, requirement or manufacturing operation was established. Resolve the source reference links and repeat the assessment before defining the CO scope.'
            elif selected['service'] == 'similar-parts':
                candidates = names('similar_parts', eligible_only=True)
                summary = ('Review ' + ', '.join(candidates) + ' as alternatives to ' + selected['object'] + '; verify dimensions, material and revision before adding a substitution to the CO.') if candidates else ('Do not propose a substitution for ' + selected['object'] + ': no supported alternative was identified.')
            else:
                processes = names('direct_processes')
                summary = ('Include ' + ', '.join(processes) + ' in the manufacturing review for ' + selected['object'] + '; confirm the operation and applicable revision before releasing the CO.') if processes else ('Hold the manufacturing release scope for ' + selected['object'] + ': no linked manufacturing operation was established. Confirm the source process association first.')
            if policy['status'] in {'blocked', 'unavailable'}:
                summary += ' Release checks require resolution.'
            return {'recommendation_observation_id': observation['id'],
                    'business_summary': summary,
                    **({'semantic_support': result['semantic_support']} if isinstance(result.get('semantic_support'), dict) else {}),
                    'decision_policy_status': policy['status'], 'advisory_only': True}
    raise ValueError('Complete only after citing selected recommendation evidence with a policy assessment')


def prompt_evidence(context, observation):
    """Project the typed verdict for model context; retain the full observation separately."""
    verdict = completion_evidence(context, [observation], [observation['id']])
    result = observation['result']
    compact = {'observation_id': observation['id'], 'business_summary': verdict['business_summary'],
        'decision_policy_status': verdict['decision_policy_status'], 'advisory_only': True,
        'coverage': result.get('coverage', {}), 'full_evidence_retained': True}
    for key in ('assembly_impact', 'process_impacts', 'impacted_requirements', 'impacted_parts', 'similar_parts', 'direct_processes'):
        rows = result.get(key)
        if isinstance(rows, list):
            compact[key + '_count'] = len(rows)
            compact[key] = [{field: row[field] for field in ('node_id', 'name', 'process_name', 'category', 'review_status', 'compatibility', 'conflicts', 'similarity_score', 'evidence_coverage') if field in row}
                for row in rows[:8] if isinstance(row, dict)]
    return compact
