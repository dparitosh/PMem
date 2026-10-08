"""Describe registered roles and their real service boundaries, not model instances."""
PURPOSES = {
    'ontology-intake': 'Inspect retained RDF/OWL or engineering source evidence.',
    'ontology-structure-review': 'Review declared classes, properties and observable structural issues.',
    'semantic-bridge-planner': 'Prepare grounded mapping candidates and unresolved validation checks.',
    'ontology-export': 'Export an approved ontology through its service contract.',
    'ontology-orchestrator': 'Sequence deterministic intake, structure review and mapping planning.',
    'context-analyst': 'Search business context and update context objects after approval.',
    'ontology-governor': 'Review and authorize registration, lifecycle changes, merge and mapping publication.',
    'engineering-parser': 'Inspect engineering files and execute bounded source profiles.',
    'graph-analyst': 'Read ontology analytics, neighborhoods and graph-grounded evidence.',
    'oslc-link-agent': 'Read linked resources and synchronize approved remote OSLC data.',
    'schema-set-agent': 'Inspect schema sets and commit reviewed QIF tasks.',
    'data-product-governor': 'Preview, publish and revoke approved retained evidence packages.',
    'ceim-mapper': 'Normalize supplied records against the CEIM contract.',
    'data-quality-monitor': 'Inspect pipeline telemetry and request approved transformations.',
    'dt-intake': 'Inspect engineering inputs, register approved ontologies and discover configured data jobs.',
    'dt-domain-identifier': 'Read domain contracts and business context; produce a reviewable classification.',
    'dt-structure-review': 'Select approved profiling jobs and inspect their retained evidence.',
    'dt-semantic-bridge-planner': 'Normalize instance evidence before reviewed semantic alignment.',
    'dt-entity-conflict-review': 'Inspect merge conflicts and retained job evidence without applying a merge.',
    'dt-property-conflict-review': 'Request approved quality jobs and inspect property-validation evidence.',
    'dt-context-graph-conflict-review': 'Inspect where-used and neighborhood evidence for relationship conflicts.',
    'dt-data-product-interaction': 'Discover job definitions and catalog versions; inspect retained run evidence.',
    'dt-kg-interaction': 'Retrieve graph analytics and graph-grounded context.',
    'dt-export': 'Export ontology evidence through the existing ingestion service.',
    'dt-self-learning-review': 'Review retained evidence; never automatically promote lessons or change models.',
    'dt-orchestrator': 'Discover runs, jobs and catalog evidence for supervised workflow composition.',
}


def describe(source):
    tools = {tool['id']: tool for tool in source['tools']}
    rows = []
    for agent in source['agents']:
        allowed = agent.get('tools', [])
        if any(identifier not in tools for identifier in allowed):
            raise ValueError('Agent references a missing tool')
        rows.append({**agent, 'description': agent.get('description') or PURPOSES.get(agent['id'], agent.get('name', agent['id'])),
            'family': 'dt-service-role' if agent['id'].startswith('dt-') else 'platform-role',
            'registration_status': 'registered; live dependencies unverified',
            'execution_boundary': 'approved mutations use persisted workflows; reads are bounded operations',
            'workflow_ids': [workflow['id'] for workflow in source['workflows'] if any(step['agent_id'] == agent['id'] for step in workflow['steps'])],
            'mutating_tools': [identifier for identifier in allowed if tools[identifier].get('mutates')]})
    return rows


def architecture(source):
    agents = describe(source)
    return {'pattern': 'governed LLM-assisted workflows', 'agent_count': len(agents), 'tool_count': len(source['tools']),
        'workflow_count': len(source['workflows']), 'agents': agents,
        'local_role_execution': 'Independent of DT_AGENT_ENABLED; tool-specific authorization and dependencies still apply',
        'external_dt_execution': 'DT_AGENT_ENABLED controls the configured external DT gateway integration',
        'semantic_assurance': 'Structural evidence and cited review questions are not equivalence or consistency proofs',
        'mcp': 'Only explicitly configured allowlisted tools; discovery does not grant execution permission'}
