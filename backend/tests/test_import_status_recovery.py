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

    def test_debug_snapshot_cannot_override_completed_task(self):
        done={**self.old,'status':'completed','committing':False}
        self.service._task_snapshot_path('task').write_text(json.dumps(done))
        (self.service.TASK_STORE_DIR/'task.json.writer_123_v1.json').write_text(json.dumps(self.old))
        self.assertEqual(self.service.list_tasks()[0]['status'],'completed')

if __name__=='__main__':unittest.main()
