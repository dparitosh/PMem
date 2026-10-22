"""Small read-only projections of retained reviews, never RDF or credentials."""
import re


def search_terms(query):
    ignored = set('what which where why when how are is was were the there this that these those have has had do does did can could should would will please show find list check tell about between with from into onto available existing saved retained ontology ontologies mapping mappings map maps merge merged merging alignment consolidation source target status review reviews and for not'.split())
    return sorted({word for word in re.findall(r'[a-z0-9]+', query.lower()) if len(word) >= 3 and word not in ignored})[:12]


def retained_mapping_evidence(registry, query, *, ontology_id='', ontology_prefix=''):
    """Filter before LIMIT and project in SQL so large Turtle never leaves DB."""
    terms = search_terms(query)
    where = ["p.namespace='ontology_merge_previews'"]
    args = []
    for term in terms:
        where.append("COALESCE(p.value->'sources','[]'::jsonb)::text ILIKE %s")
        args.append('%'+term+'%')
    if ontology_id:
        where.append("p.value->'source_ontology_ids' ? %s")
        args.append(ontology_id)
    if ontology_prefix:
        where.append("EXISTS (SELECT 1 FROM depo_registry c WHERE c.namespace='ontology_catalog' AND c.value->>'prefix'=%s AND p.value->'source_ontology_ids' ? c.key)")
        args.append(ontology_prefix)
    sql = """SELECT p.key, jsonb_build_object(
      'created_at',p.value->'created_at', 'sources',p.value->'sources',
      'candidates',jsonb_array_length(COALESCE(p.value->'entity_suggestions','[]'::jsonb)),
      'ambiguous',(SELECT count(*) FROM jsonb_array_elements(COALESCE(p.value->'entity_suggestions','[]'::jsonb)) x WHERE x->>'ambiguous'='true'),
      'selected',jsonb_array_length(COALESCE(p.value->'changes'->'entity_mappings','[]'::jsonb)),
      'shacl_conforms',p.value->'semantic_checks'->'shacl_conforms',
      'owl_rl_performed',p.value->'semantic_checks'->'owl_rl_performed',
      'matching_policy',p.value->'matching_report'->'policy',
      'truncated',p.value->'matching_report'->'truncated',
      'merged_ontology_id',p.value->'applied_result'->'ontology'->'ontology_id',
      'missing_source_ids',(SELECT COALESCE(jsonb_agg(s.id),'[]'::jsonb) FROM jsonb_array_elements_text(COALESCE(p.value->'source_ontology_ids','[]'::jsonb)) s(id)
         WHERE NOT EXISTS (SELECT 1 FROM depo_registry c WHERE c.namespace='ontology_catalog' AND c.key=s.id))
      ) FROM depo_registry p WHERE """ + ' AND '.join(where) + " ORDER BY p.value->>'created_at' DESC,p.key DESC LIMIT 6"
    with registry._connect() as db, db.cursor() as cursor:
        cursor.execute(sql,args)
        rows = cursor.fetchall()
    evidence=[]
    for identifier, value in rows:
        names = [str(s.get('ontology_name') or s.get('ontology_id') or 'Unnamed source')[:180] for s in (value.get('sources') or [])[:4]]
        shacl = 'passed' if value.get('shacl_conforms') is True else 'failed' if value.get('shacl_conforms') is False else 'pending'
        text = (f"Saved mapping review: {' → '.join(names)}. "
                f"Proposals: {value['candidates']}; ambiguous: {value['ambiguous']}; selected consolidations: {value['selected']}. "
                f"SHACL: {shacl}; OWL-RL completed: {value.get('owl_rl_performed') is True}. "
                f"Matching policy: {value.get('matching_policy') or 'not recorded'}.")
        if value.get('truncated'): text += ' Candidate search was bounded/truncated; this is not an exhaustive alignment.'
        if value['selected'] == 0: text += ' No identity mapping pairs were selected; a union draft does not establish semantic mappings.'
        if value.get('merged_ontology_id'): text += f" Recorded merged artifact: {value['merged_ontology_id']}."
        text += ' Current Neo4j publication is not verified by this historical review.'
        if value.get('missing_source_ids'): text += ' Source registrations are currently missing. Restore or re-import the sources, then regenerate and review a new plan.'
        evidence.append({'evidence_type':'mapping_review','resource_id':str(identifier),
                         'label':' → '.join(names),'description':text,'created_at':value.get('created_at'),
                         'source':'ontology-service:retained-merge-review'})
    return {'evidence':evidence, 'coverage':'Latest six matching retained reviews; graph publication not verified', 'limit':6}
