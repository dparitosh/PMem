import ast,json,logging,tempfile,unittest
from pathlib import Path
from typing import Any,Dict,List,Optional
from types import SimpleNamespace
from backend.depo_platform.import_cleanup import cleared

SOURCE=Path(__file__).resolve().parents[1]/'Services/unified_data_import.py'
class ImportStatusRecoveryTests(unittest.TestCase):
    def setUp(self):
        methods={'_read_status_task','get_status','list_tasks'}
        tree=ast.parse(SOURCE.read_text(encoding='utf-8'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='UnifiedDataImportService')
        cls.body=[n for n in cls.body if getattr(n,'name','') in methods]
        cls.bases=[]
        self.cache={}
        scope=dict(Path=Path,Dict=Dict,Any=Any,List=List,Optional=Optional,json=json,import_tasks=self.cache,
                   logger=logging.getLogger(__name__),WorkflowArtifactService=SimpleNamespace(get_manifest=lambda _:{}), import_task_cleared=cleared)
        exec(compile(ast.Module(body=[cls],type_ignores=[]),str(SOURCE),'exec'),scope)
        self.service=scope[cls.name]
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.service.TASK_STORE_DIR=Path(self.temp.name)
        self.service._task_snapshot_path=lambda task_id:Path(self.temp.name)/(task_id+'.json')
        self.old=dict(task_id='task',filename='req.xml',file_type='xml',current_stage='ingest',progress=83,
                      status='processing',committing=True,message='Preparing',started_at='2026-01-01',stats={})
        self.cache['task']=self.old
    def test_completed_snapshot_supersedes_stale_cache_without_replacing_writer(self):
        done={**self.old,'status':'completed','progress':100,'committing':False,'result':{'nodes_created':22,'relationships_created':39},'artifact_manifest':{'task_id':'task'}}
        self.service._task_snapshot_path('task').write_text(json.dumps(done),encoding='utf-8')
        status=self.service.get_status('task')
        self.assertEqual(status['status'],'completed');self.assertEqual(status['result']['relationships_created'],39)
        self.assertEqual(self.service.list_tasks()[0]['status'],'completed')
        self.assertIs(self.cache['task'],self.old);self.assertEqual(self.old['progress'],83)
    def test_incomplete_or_missing_snapshot_falls_back_to_live_task(self):
        self.service._task_snapshot_path('task').write_text('{',encoding='utf-8')
        self.assertEqual(self.service.get_status('task')['progress'],83)
        self.assertIsNone(self.service.get_status('absent'))

    def test_deletion_receipt_hides_stale_process_cache(self):
        folder=self.service.TASK_STORE_DIR/'.cleared';folder.mkdir()
        (folder/'task').write_text('{}')
        self.assertIsNone(self.service.get_status('task'))
        self.assertEqual(self.service.list_tasks(),[])

    def test_persistence_warning_surfaces_without_overwriting_saved_state(self):
        self.service._task_snapshot_path('task').write_text(json.dumps(self.old))
        # Use the method's globals to exercise the same in-memory task store.
        store = self.service._read_status_task.__func__.__globals__['import_tasks']
        store['task']['_persistence_error'] = 'Status could not be saved'
        result = self.service.get_status('task')
        self.assertEqual(result['persistence_warning'], 'Status could not be saved')

    def test_debug_snapshot_cannot_override_completed_task(self):
        done={**self.old,'status':'completed','committing':False}
        self.service._task_snapshot_path('task').write_text(json.dumps(done))
        (self.service.TASK_STORE_DIR/'task.json.writer_123_v1.json').write_text(json.dumps(self.old))
        self.assertEqual(self.service.list_tasks()[0]['status'],'completed')

    def test_hashed_sidecars_do_not_break_registry_or_get_read_as_snapshots(self):
        from unittest.mock import patch
        from backend.Services.import_task_persistence import persist_task
        task={**self.old,'status':'completed','parsed_rows':[{'name':'Bearing'}],'shacl_report':{'conforms':True}}
        persist_task(self.service._task_snapshot_path('task'),task,dict)
        read=Path.read_text
        reads=[]
        def tracked(path,*args,**kwargs):
            reads.append(path.name)
            return read(path,*args,**kwargs)
        with patch.object(Path,'read_text',tracked):
            result=self.service.list_tasks()
        self.assertEqual([row['task_id'] for row in result],['task'])
        self.assertEqual(result[0]['status'],'completed')
        self.assertFalse(any('.parsed_rows.' in name or '.shacl_report.' in name for name in reads))

    def test_non_task_json_values_do_not_hide_valid_imports(self):
        self.service._task_snapshot_path('task').write_text(json.dumps(self.old))
        for index,data in enumerate([[],None,17,'text',False,{'message':'not a task'}]):
            (self.service.TASK_STORE_DIR/f'other-{index}.json').write_text(json.dumps(data))
        self.assertEqual([row['task_id'] for row in self.service.list_tasks()],['task'])

    def test_legacy_sidecar_arrays_are_still_excluded(self):
        self.service._task_snapshot_path('task').write_text(json.dumps(self.old))
        (self.service.TASK_STORE_DIR/'task.json.parsed_rows.json').write_text('[{}]')
        (self.service.TASK_STORE_DIR/'task.json.shacl_report.json').write_text('[]')
        self.assertEqual(len(self.service.list_tasks()),1)

    def test_import_tasks_endpoint_returns_history_with_new_sidecar_format(self):
        import sys
        from types import ModuleType
        from unittest.mock import patch
        from fastapi import FastAPI, HTTPException, Request
        from fastapi.testclient import TestClient
        from backend.Services.import_task_persistence import persist_task
        persist_task(self.service._task_snapshot_path('task'),{**self.old,'status':'completed','parsed_rows':[{'name':'Bearing'}]},dict)
        module=ModuleType('backend.Services.unified_data_import');module.UnifiedDataImportService=self.service
        source=SOURCE.parents[1]/'ingestion_service/router.py'
        tree=ast.parse(source.read_text(encoding='utf-8'))
        function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='import_tasks')
        function.decorator_list=[]
        scope={'HTTPException':HTTPException,'Request':Request,'__name__':__name__}
        exec(compile(ast.Module(body=[function],type_ignores=[]),str(source),'exec'),scope)
        app=FastAPI();app.add_api_route('/api/v1/import/tasks',scope['import_tasks'],methods=['GET'])
        with patch.dict(sys.modules,{'backend.Services.unified_data_import':module}):
            result=TestClient(app).get('/api/v1/import/tasks')
        self.assertEqual(result.status_code,200)
        response=result.json()
        self.assertEqual(response['total_tasks'],1)
        self.assertEqual(response['tasks'][0]['filename'],'req.xml')

if __name__=='__main__':unittest.main()
