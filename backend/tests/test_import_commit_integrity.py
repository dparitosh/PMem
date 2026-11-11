import os, unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from backend.Services.import_commit_integrity import commit_operation,require_relationship_batch,scoped_merge_keys
from backend.depo_platform.operations import OperationContext,operation_scope,current_operation
from backend.depo_platform.execution_guard import guarded_execution

class CommitIntegrityTests(unittest.TestCase):
 def test_import_merge_keys_keep_task_isolation(self):
  original=['import_row_key']
  self.assertEqual(scoped_merge_keys(original),['import_row_key','import_id'])
  self.assertEqual(original,['import_row_key'])
  self.assertEqual(scoped_merge_keys(['id','import_id','id']),['id','import_id'])
 def test_direct_queued_job_has_independent_bounded_deadline(self):
  parent=OperationContext('http',(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat())
  with operation_scope(parent),patch.dict(os.environ,{'IMPORT_COMMIT_MAX_SECONDS':'120'}):
   with commit_operation('job') as job:
    self.assertEqual(job.operation_id,'job');self.assertGreater(job.timeout(100),90)
   self.assertIs(current_operation(),parent)
 def test_leased_workflow_deadline_and_guard_are_not_bypassed(self):
  parent=OperationContext('lease',(datetime.now(timezone.utc)+timedelta(seconds=10)).isoformat())
  with operation_scope(parent),guarded_execution(lambda:None):
   with commit_operation('job') as job:self.assertIs(job,parent)
 def test_partial_writes_and_errors_cannot_claim_complete(self):
  for result in ({'matched_rows':0},{'matched_rows':149},{'matched_rows':151},{'matched_rows':True},{'matched_rows':150,'errors':['timeout']}):
   with self.subTest(result=result),self.assertRaises(RuntimeError):require_relationship_batch(result,150,'MASTER_REF')
  self.assertEqual(require_relationship_batch({'matched_rows':150,'errors':[]},150,'MASTER_REF'),150)
class RelationshipWriterTests(unittest.TestCase):
 def run_writer(self, response):
  import re,textwrap
  from pathlib import Path
  from types import SimpleNamespace
  from typing import Dict,List,Any
  source=(Path(__file__).resolve().parents[1]/'Services/unified_data_import.py').read_text(encoding='utf-8')
  start=source.index("        xmi_rels = task.get('_xmi_relationships', [])",source.index('def _commit_sync'))
  end=source.index('        # ── STEP reference edges',start)
  calls=[]
  def execute(queries, rows, **kwargs):
   calls.extend(queries);return response
  scope=dict(__package__='backend.Services',task={'_xmi_relationships':[{'from_props':{'id':'a'},'to_props':{'id':'b'},'type':'MASTER_REF'}]},
   rows=[{'id':'a','element_type':'Part'},{'id':'b','element_type':'Revision'}],
   schema={'nodes':[{'label':'Part','_filter_key':'element_type','_filter_val':'Part'},{'label':'Revision','_filter_key':'element_type','_filter_val':'Revision'}]},
   task_id='import',result={'relationships_created':0,'relationships_skipped':0},_re=re,Dict=Dict,List=List,Any=Any,
   IMPORT_LINK_BATCH_SIZE=150,_sync_metrics=lambda *args:None,Neo4jImporter=SimpleNamespace(execute_cypher=execute))
  exec(textwrap.dedent(source[start:end]),scope)
  return calls,scope['result']
 def test_scopes_both_endpoint_labels_and_counts_success(self):
  calls,result=self.run_writer({'matched_rows':1,'errors':[]})
  self.assertIn('MATCH (a:`Part`',calls[0]);self.assertIn('MATCH (b:`Revision`',calls[0])
  self.assertIn('import_id: row.import_id',calls[0]);self.assertEqual(result['relationships_created'],1)
 def test_actual_writer_propagates_failed_or_incomplete_batch(self):
  for response in [{'matched_rows':0,'errors':[]},{'matched_rows':0,'errors':['timeout']}]:
   with self.subTest(response=response),self.assertRaises(RuntimeError):self.run_writer(response)

if __name__=='__main__':unittest.main()
