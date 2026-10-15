import pickle
import ast
import asyncio
import json
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.ontology_service.merge_preparation import prepare
from backend.ontology_service.merge_semantics import validate_merge


class MergePreparationDeadlineTests(unittest.TestCase):
    def test_reviewed_merge_queues_publication_and_returns_job_for_ui_tracking(self):
        tree = ast.parse(Path('backend/ontology_service/router.py').read_text(encoding='utf-8-sig'))
        method = next(item for item in tree.body if isinstance(item,ast.AsyncFunctionDef) and item.name == 'apply_merge')
        method.decorator_list = []
        calls = []
        async def thread(callback,*args,**kwargs): return callback(*args,**kwargs)
        async def publish(ontology_id,payload,request,**kwargs):
            calls.append((ontology_id,kwargs))
            return SimpleNamespace(body=json.dumps({'ontology_id':'merged','job_id':'job','status':'queued'}).encode())
        scope = dict(MergeApplyBody=dict,Request=object,json=json,approval_identity=lambda *args,**kwargs:'actor',
            run_in_threadpool=thread,merges=SimpleNamespace(apply=lambda *args:{'status':'merged','ontology':{'ontology_id':'merged'}}),
            catalog=SimpleNamespace(get=lambda _:{'ontology_id':'merged','lifecycle_status':'approved'}),publish_registered_ontology=publish,HTTPException=RuntimeError)
        exec(compile(ast.Module(body=[method],type_ignores=[]),'<merge-route>','exec'),scope)
        result = asyncio.run(scope['apply_merge']('preview',{'publish':True},object()))
        self.assertEqual(result['publication_status'],'queued')
        self.assertEqual(result['publication']['job_id'],'job')
        self.assertEqual(calls,[('merged',{'background':True})])

    def service(self):
        return SimpleNamespace(catalog=SimpleNamespace(get=lambda _: {}, read_artifact=lambda key: ({'ontology_name':key}, b'rdf')))

    def test_complete_preview_preparation_runs_in_one_terminable_worker(self):
        record = {'preview_id':'p','turtle':'rdf'}
        completed = SimpleNamespace(returncode=0,stdout=pickle.dumps({'record':record}))
        with patch('backend.ontology_service.merge_preparation.subprocess.run',return_value=completed) as run:
            self.assertEqual(prepare(self.service(),{'source_ontology_ids':[' a ','b']}),record)
        sources, payload = pickle.loads(run.call_args.kwargs['input'])
        self.assertEqual(set(sources),{'a','b'})
        self.assertEqual(payload['source_ontology_ids'],['a','b'])
        self.assertGreater(run.call_args.kwargs['timeout'],0)
        self.assertLessEqual(run.call_args.kwargs['timeout'],180)

    def test_timeout_terminates_preparation_without_saving_a_preview(self):
        with patch('backend.ontology_service.merge_preparation.subprocess.run',side_effect=subprocess.TimeoutExpired('worker',1)):
            with self.assertRaisesRegex(ValueError,'worker was terminated'):
                prepare(self.service(),{'source_ontology_ids':['a','b']})

    def test_combined_source_budget_is_checked_before_parsing(self):
        with patch('backend.depo_platform.upload_limits.ontology_upload_limit',return_value=5), patch('backend.ontology_service.merge_preparation.subprocess.run') as run:
            with self.assertRaisesRegex(ValueError,'Combined merge sources'):
                prepare(self.service(),{'source_ontology_ids':['a','b']})
        run.assert_not_called()

    def test_apply_and_policy_send_turtle_to_worker_instead_of_parsing_in_request_thread(self):
        completed = SimpleNamespace(returncode=0,stdout=pickle.dumps({'inferred_conflicts':[]}))
        with patch('subprocess.run',return_value=completed) as run:
            self.assertEqual(validate_merge('retained turtle',[],declarations_only=True),{'inferred_conflicts':[]})
        data = pickle.loads(run.call_args.kwargs['input'])
        self.assertEqual(data,('retained turtle',[],None,True))


if __name__ == '__main__': unittest.main()
