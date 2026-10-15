"""Ingestion-owned mapping source access; accessed through its private peer API."""
from backend.depo_platform.bridge_contract import digest, canonical_lookup, BridgeConflict


class LocalBridgeSource:
    def _read(self, ontology_id, import_id):
        from backend.Services.semantic_workflow_service import SemanticWorkflowService as service
        from backend.Services.unified_data_import import UnifiedDataImportService
        ontology_id = service._resolve_ontology_id(ontology_id)
        try:
            meta = service._ontology_metadata(ontology_id)
        except ValueError as exc:
            if 'Ontology not found' not in str(exc):
                raise
            # Graph-native records are sufficient for instance mapping, which
            # does not claim to perform RDF reasoning or ontology merging.
            meta = {'prefix': ontology_id}
        task = service._load_import_task({'task_id': import_id})
        lifecycle = {key: meta.get(key) for key in ('lifecycle_status', 'status')}
        if meta.get('lifecycle_status') in {'retired', 'deprecated'} or meta.get('status') == 'superseded':
            raise BridgeConflict('Selected ontology is inactive. Select a current ontology and create a new preview.')
        # Preserve the selected version identity; a prefix can name many versions.
        scope = ontology_id
        # Include live graph IDs/type metadata as well as retained ontology bytes.
        terms = service._load_ontology_term_lookup(scope)
        classes = UnifiedDataImportService._load_ontology_class_lookup(scope)
        if not terms and not classes:
            raise ValueError('No ontology terms are available for mapping. Check the selected ontology and graph projection.')
        snapshot = {'source': digest(task.get('parsed_rows') or []),
                    'ontology': digest([ontology_id, scope, lifecycle, service._read_ontology_file(meta), canonical_lookup(terms), canonical_lookup(classes)])}
        return service, task, scope, snapshot

    def snapshot(self, ontology_id, import_id):
        return self._read(ontology_id, import_id)[3]

    def preview(self, ontology_id, import_id):
        service, task, scope, snapshot = self._read(ontology_id, import_id)
        candidates = service._build_link_candidates(task.get('parsed_rows') or [], scope, import_id, import_task=task)
        if snapshot != self.snapshot(ontology_id, import_id):
            raise BridgeConflict('Source changed while previewing. Retry preview.')
        return snapshot, candidates

    def manual_candidates(self, ontology_id, import_id, mappings):
        if not isinstance(mappings, list) or len(mappings) > 2000:
            raise ValueError('Manual mappings must contain at most 2000 entries')
        service, task, scope, _ = self._read(ontology_id, import_id)
        from backend.Services.unified_data_import import UnifiedDataImportService
        lookup = service._load_ontology_term_lookup(scope)
        classes = UnifiedDataImportService._load_ontology_class_lookup(scope)
        terms = {}
        # Class lookup entries originate in Neo4j; other terms can be retained
        # RDF-only declarations and must explicitly carry graph provenance.
        graph_classes = [[{**term, 'graph_linkable': True} for term in values] for values in classes.values()]
        for values in [*graph_classes, *lookup.values()]:
            for term in values:
                identity = term.get('graph_element_id') or term.get('element_id')
                if identity:
                    key = (str(identity), term.get('target_ontology_type') or 'Class')
                    terms[key] = {**terms.get(key, {}), **term}
        candidates = []
        for mapping in mappings:
            if not isinstance(mapping, dict):
                raise ValueError('Manual mapping must be an object')
            target = str(mapping.get('target_term') or '')
            kind = mapping.get('target_ontology_type')
            matches = [term for term in terms.values() if (term.get('target_ontology_type') or 'Class') == kind and
                       target in {str(term.get(key) or '') for key in ('class_name', 'term_name', 'iri', 'uri', 'target_ontology_iri', 'element_id', 'graph_element_id')}]
            if len(matches) != 1:
                raise ValueError('Manual mapping target is missing or ambiguous; select a unique graph-backed ontology term')
            term = matches[0]
            graph_id = term.get('graph_element_id') or (term.get('element_id') if term.get('graph_linkable', False) else None)
            if not graph_id:
                raise ValueError('Manual mapping target is not published in the graph')
            rows = [row for row in task.get('parsed_rows') or [] if
                    service._candidate_display_value(row) == mapping.get('source_term') and
                    service._classify_source_row(row) == mapping.get('source_type')]
            if not rows:
                raise ValueError('Manual mapping source is not present in the selected imported instance')
            for row in rows:
                validation = service._validate_candidate_pair(mapping.get('source_type'), kind, term, row)
                row_key = row.get('import_row_key') or row.get('id')
                if not validation['is_valid'] or not row_key:
                    raise ValueError('Manual mapping source/target pair is invalid')
                candidates.append({'import_id': import_id, 'import_row_key': row_key,
                    'source_term': mapping['source_term'], 'source_type': mapping['source_type'],
                    'ontology_term': term.get('class_name') or term.get('term_name') or target,
                    'ontology_class_element_id': graph_id, 'target_ontology_type': kind,
                    'target_ontology_iri': term.get('target_ontology_iri') or term.get('iri') or term.get('uri'),
                    'mapping': scope, 'mapping_type': 'closeMatch', 'confidence': 1,
                    'validation_status': validation['status'], 'validation_errors': validation['errors'],
                    'validation_warnings': validation.get('warnings', []),
                    'evidence': ['user-selected mapping; server-resolved source and target']})
        return candidates

    def preview_partition(self, ontology_id, import_id, mappings=None, candidate_offset=0):
        if type(candidate_offset) is not int or candidate_offset < 0:
            raise ValueError('candidate_offset must be a nonnegative integer')
        snapshot, candidates = self.preview(ontology_id, import_id)
        if mappings:
            candidates.extend(self.manual_candidates(ontology_id, import_id, mappings))
            if snapshot != self.snapshot(ontology_id, import_id):
                raise BridgeConflict('Source changed while resolving manual mappings')
        total = len(candidates)
        if candidate_offset and candidate_offset >= total:
            raise ValueError('Candidate partition is unavailable; start a new preview')
        if total > 2000 or candidate_offset:
            candidates = sorted(candidates, key=digest)[candidate_offset:candidate_offset + 2000]
        return snapshot, candidates, {'offset':candidate_offset, 'total_candidates':total,
            'next_offset':candidate_offset + 2000 if candidate_offset + 2000 < total else None}
