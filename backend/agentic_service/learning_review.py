"""Governed mapping feedback. Publication proof is not proof of business correctness.

PostgreSQL owns outcomes, lessons and the bounded approved index. Lessons are
revision-scoped review hints; they never change models, scores or permissions.
"""
import copy
from datetime import datetime, timezone
from backend.mesh_store import PostgresRegistry
from backend.depo_platform.bridge_contract import digest, BridgeConflict


def now():
    return datetime.now(timezone.utc).isoformat()


def pattern(row):
    return {key: row.get(key) for key in ('source_type', 'source_term', 'target_ontology_type',
                                        'target_ontology_iri', 'mapping_type')}


def index_key(ontology_id, revision):
    return 'approved:' + digest([ontology_id, revision])


def revision_key(revision):
    return digest(revision) if isinstance(revision,dict) else revision


def sealed(record):
    return {**record, 'record_digest': digest(record)}


def hints(store, ontology_id, revision, candidates=None):
    index = store.get(index_key(ontology_id, revision))
    entries = []
    if index is not None:
        if (index.get('record_digest') != digest({k:v for k,v in index.items() if k != 'record_digest'})
            or not isinstance(index.get('lessons'),list) or len(index['lessons']) > 20):
            raise BridgeConflict('Approved lesson index integrity check failed')
        entries = index['lessons']
    if candidates is not None:
        patterns = {digest(pattern(row)) for row in candidates}
        entries = [row for row in entries if digest(row['mapping_pattern']) in patterns]
    return {'status':'available','ontology_id':ontology_id,'ontology_snapshot':revision,
        'lessons':copy.deepcopy(entries),'advisory_only':True,'publication_authorized':False,'model_training_performed':False}


class LearningReview:
    def __init__(self, jobs, store=None):
        self.jobs = jobs
        self.store = store if store is not None else PostgresRegistry('agentic_learning_reviews_v1')

    def _revision(self,ontology_id,import_task_id):
        reader=getattr(self.jobs.source,'model_revision',None)
        return reader(ontology_id) if callable(reader) else self.jobs.source.snapshot(ontology_id,import_task_id)['ontology']

    def get(self, identifier):
        if not isinstance(identifier, str) or not identifier.startswith(('outcome-', 'lesson-')):
            raise ValueError('Select a retained outcome or lesson')
        record = self.store.get(identifier)
        if record is None: raise KeyError(identifier)
        if record.get('record_digest') != digest({k:v for k,v in record.items() if k != 'record_digest'}):
            raise BridgeConflict('Learning review integrity check failed')
        return copy.deepcopy(record)

    def _publication(self, publication_id, candidate_id):
        job = self.jobs.get(publication_id)
        if job.get('kind') != 'publication' or job.get('status') != 'published' or candidate_id not in job.get('approved_ids', []):
            raise ValueError('Feedback requires a published mapping in the retained approval')
        receipt = self.jobs.graph.receipt(publication_id)
        if (not isinstance(receipt, dict) or receipt.get('publication_id') != publication_id
            or not job.get('request_digest') or receipt.get('request_digest') != job['request_digest']
            or receipt.get('approved_by') != job.get('approved_by')
            or receipt.get('applied_links') != len(job['approved_ids'])):
            raise BridgeConflict('Verify the publication receipt before recording or promoting feedback')
        preview = self.jobs.get(job['preview_id'])
        if preview.get('ontology_id') != job['ontology_id'] or preview.get('import_task_id') != job['import_task_id']:
            raise BridgeConflict('Publication and preview source identities differ')
        if preview.get('preview_digest') != digest({k:v for k,v in preview.items() if k != 'preview_digest'}):
            raise BridgeConflict('Retained mapping preview changed')
        row = next((row for row in preview.get('candidates', []) if row.get('candidate_id') == candidate_id), None)
        if row is None: raise ValueError('Mapping is absent from the retained preview')
        if not isinstance(row.get('target_ontology_iri'), str) or not row['target_ontology_iri'].startswith(('urn:','http://','https://')):
            raise ValueError('A reusable lesson requires an exact target IRI; restore target identity first')
        if not isinstance(row.get('source_term'),str) or not row['source_term'].strip():
            raise ValueError('A reusable lesson requires a descriptive source identity')
        return job, preview, row

    def outcome(self, publication_id, candidate_id, result, note, actor):
        if result not in {'confirmed', 'rejected', 'uncertain'}:
            raise ValueError('Choose confirmed, rejected or uncertain')
        if not isinstance(note, str) or not 1 <= len(note.strip()) <= 1000:
            raise ValueError('Record a review note of 1 to 1000 characters')
        job, preview, row = self._publication(publication_id, candidate_id)
        # Append-only assessment revisions. Only the current head may contribute
        # to a lesson, so changing a review does not inflate its sample count.
        review_key = digest([publication_id,candidate_id,actor])
        head_key = 'outcome-head:' + review_key
        identifier = 'outcome-' + digest([review_key,result,note.strip()])
        body = dict(kind='outcome', schema_version=1, outcome_id=identifier, publication_id=publication_id,
            candidate_id=candidate_id, result=result, note=note.strip(), reviewed_by=actor,
            ontology_id=job['ontology_id'], import_task_id=job['import_task_id'],
            snapshot=preview['snapshot'], mapping_pattern=pattern(row),
            ontology_revision=self._revision(job['ontology_id'],job['import_task_id']),
            review_key=review_key,
            publication_digest=job['request_digest'], publication_verified=True,
            correctness_basis='human_review_not_independent_engineering_verification')
        with self.store.advisory_lock(head_key) as acquired:
            if acquired is False: raise BridgeConflict('Feedback is being saved; refresh before retrying')
            previous = self.store.get(identifier)
            head = self.store.get(head_key) or {}
            if previous:
                retained = self.get(identifier)
                if head.get('outcome_id') != identifier:
                    raise BridgeConflict('This assessment was superseded; inspect the latest retained review')
                return retained
            record = sealed({**body, 'created_at': now(), 'supersedes':head.get('outcome_id')})
            key = index_key(body['ontology_id'],revision_key(body['ontology_revision']))
            with self.store.advisory_lock(key) as acquired:
                if acquired is False: raise BridgeConflict('Lesson scope is being reviewed; retry the same feedback')
                entries = hints(self.store,body['ontology_id'],revision_key(body['ontology_revision']))['lessons']
                removed = [entry for entry in entries if head.get('outcome_id') in entry.get('outcome_ids',[])]
                updates = {identifier:record,head_key:{'outcome_id':identifier}}
                if removed:
                    updates[key] = sealed({'kind':'approved_lesson_index','lessons':[entry for entry in entries if entry not in removed]})
                    for entry in removed:
                        old = self.get(entry['lesson_id'])
                        updates[entry['lesson_id']] = sealed({**{k:v for k,v in old.items() if k!='record_digest'},
                            'status':'superseded','superseded_by':identifier,'superseded_at':now()})
                self.store.put_many(updates)
            return record

    def prepare(self, outcome_ids, actor):
        if not isinstance(outcome_ids, list) or not 1 <= len(outcome_ids) <= 20 or any(not isinstance(item,str) for item in outcome_ids) or len(set(outcome_ids)) != len(outcome_ids):
            raise ValueError('Select 1 to 20 distinct retained outcomes')
        rows = [self.get(identifier) for identifier in sorted(outcome_ids)]
        if any(row.get('kind') != 'outcome' for row in rows): raise ValueError('Lessons require outcome records')
        for row in rows:self._current_outcome(row)
        if len({row['review_key'] for row in rows}) != len(rows):raise ValueError('Select one current assessment per mapping and reviewer')
        first = rows[0]
        scope = [first['ontology_id'], first['snapshot']['ontology'], first['ontology_revision'], first['mapping_pattern']]
        if any([row['ontology_id'], row['snapshot']['ontology'], row['ontology_revision'], row['mapping_pattern']] != scope for row in rows):
            raise ValueError('A lesson must concern one ontology revision and mapping pattern')
        if all(row['result'] == 'uncertain' for row in rows):
            raise ValueError('Uncertain observations alone cannot establish a reusable lesson')
        counts = {key:sum(row['result'] == key for row in rows) for key in ('confirmed','rejected','uncertain')}
        identifier = 'lesson-' + digest(sorted(outcome_ids))
        hint = ('A retained review rejected this mapping pattern. Inspect the source meaning and target definition before reuse.'
                if counts['rejected'] else 'Retained reviews confirmed this mapping pattern. Recheck current source context and validation before reuse.')
        body = dict(kind='lesson', schema_version=1, lesson_id=identifier, outcome_ids=sorted(outcome_ids), ontology_id=first['ontology_id'],
            ontology_snapshot=first['snapshot']['ontology'], mapping_pattern=first['mapping_pattern'],
            model_revision=first['ontology_revision'],
            measurements={**counts, 'assessments':len(rows), 'distinct_publications':len({r['publication_id'] for r in rows}),
                          'basis':'human_assessments_of_receipted_mappings_not_calibrated_accuracy'},
            review_hint=hint, advisory_only=True, model_training_performed=False,
            automatic_policy_change=False, status='pending_review', created_by=actor, created_at=now())
        with self.store.advisory_lock(identifier) as acquired:
            if acquired is False: raise BridgeConflict('Lesson preparation is active; refresh before retrying')
            if self.store.get(identifier): return self.get(identifier)
            record = sealed(body); self.store.create(identifier,record); return record

    def transition(self, identifier, action, actor, reason):
        if action not in {'approve', 'revoke'} or not isinstance(reason,str) or not 1 <= len(reason.strip()) <= 1000:
            raise ValueError('Choose approval/revocation and record the review reason')
        lesson = self.get(identifier)
        if lesson.get('kind') != 'lesson': raise ValueError('Select a retained lesson')
        key = index_key(lesson['ontology_id'],revision_key(lesson['model_revision']))
        with self.store.advisory_lock(key) as acquired:
            if acquired is False: raise BridgeConflict('Lesson scope is being updated; refresh before retrying')
            lesson = self.get(identifier)
            target = 'approved' if action == 'approve' else 'revoked'
            if lesson['status'] == target: return lesson
            if action == 'approve':
                if lesson['status'] != 'pending_review': raise ValueError('A revoked lesson requires a new review')
                for outcome_id in lesson['outcome_ids']:
                    row = self.get(outcome_id)
                    self._current_outcome(row)
                    if self._revision(row['ontology_id'],row['import_task_id']) != row['ontology_revision']:
                        raise BridgeConflict('Model revision changed; prepare a current review')
                    _, preview, _ = self._publication(row['publication_id'],row['candidate_id'])
                    if self.jobs.source.snapshot(row['ontology_id'],row['import_task_id']) != preview['snapshot']:
                        raise BridgeConflict('Source or ontology changed; collect and review current evidence')
            entries = [entry for entry in hints(self.store,lesson['ontology_id'],revision_key(lesson['model_revision']))['lessons'] if entry['lesson_id'] != identifier]
            if action == 'approve':
                if len(entries) >= 20: raise ValueError('This revision already has 20 active lessons; revoke superseded lessons first')
                entries.append({key:lesson[key] for key in ('lesson_id','outcome_ids','mapping_pattern','measurements','review_hint')})
            record = sealed({**{k:v for k,v in lesson.items() if k != 'record_digest'}, 'status':target,
                'reviewed_by':actor,'review_reason':reason.strip(),'reviewed_at':now()})
            # One PostgreSQL transaction updates the lesson and its lookup index.
            self.store.put_many({identifier:record,key:sealed({'kind':'approved_lesson_index','lessons':entries})})
            return record

    def _current_outcome(self,row):
        head=self.store.get('outcome-head:'+row['review_key'])
        if not head or head.get('outcome_id') != row['outcome_id']:
            raise BridgeConflict('Outcome was superseded; prepare a lesson from the current assessment')

    def support(self, ontology_id, import_task_id):
        revision=self._revision(ontology_id,import_task_id)
        return {**hints(self.store,ontology_id,revision_key(revision)), 'import_task_id':import_task_id,
                'model_revision':revision,'import_task_verified':False}
