"""Regression tests for Neo4j dialect compatibility and retained governance."""
import ast
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import re
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from backend.depo_platform import metadata_service
from backend.depo_platform.metadata_validation import validate_asset_state


class MetadataStateTests(unittest.TestCase):
    def asset(self, **updates):
        return dict(asset_id='asset', name='Pump', lifecycle_status='approved', steward='steward',
                    approval_evidence='review-42', effective_from='2026-01-01', effective_to='2027-01-01', **updates)

    def test_partial_updates_cannot_remove_approved_governance(self):
        for field in ('steward', 'approval_evidence'):
            for value in ('', '   ', None):
                with self.subTest(field=field,value=value):
                    repo=SimpleNamespace(get=lambda _: {**self.asset(),'revision':2},save=Mock())
                    with patch.object(metadata_service,'repository',return_value=repo),self.assertRaises(HTTPException) as error:
                        metadata_service.update('asset',{field:value},'verified',expected_revision=2)
                    self.assertEqual(error.exception.status_code,409)
                    repo.save.assert_not_called()

    def test_partial_date_update_compares_with_retained_other_endpoint(self):
        for update in ({'effective_to':'2025-01-01'},{'effective_to':'2027-01-01T00:00:00Z'}):
            repo=SimpleNamespace(get=lambda _: {**self.asset(),'revision':2},save=Mock())
            with patch.object(metadata_service,'repository',return_value=repo),self.assertRaises(HTTPException) as error:
                metadata_service.update('asset',update,'verified')
            self.assertEqual(error.exception.status_code,409)
            repo.save.assert_not_called()

    def test_valid_update_preserves_identity_actor_and_revision(self):
        repo=SimpleNamespace(get=lambda _: {**self.asset(),'revision':2},save=Mock(return_value={'revision':3,'publication_status':'pending'}))
        module=SimpleNamespace(MetadataConflict=type('MetadataConflict',(ValueError,),{}))
        with patch.object(metadata_service,'repository',return_value=repo),patch.dict(sys.modules,{'backend.depo_platform.metadata_repository':module}):
            result=metadata_service.update('asset',{'name':'Pump revised'},'verified',expected_revision=2)
        self.assertEqual(result['revision'],3)
        self.assertEqual(result['name'],'Pump revised')
        self.assertEqual(repo.save.call_args.kwargs['expected_revision'],2)
        self.assertEqual(repo.save.call_args.kwargs['actor'],'verified')
        self.assertEqual(repo.save.call_args.args[1]['steward'],'steward')

    def test_transitions_reject_whitespace_evidence_and_reason(self):
        for old,status,field in [('in_review','approved','approval_evidence'),('approved','deprecated','deprecation_reason')]:
            asset={**self.asset(),'lifecycle_status':old,'revision':2}
            if field=='approval_evidence':asset[field]=''
            payload=SimpleNamespace(status=status,approval_evidence='',deprecation_reason='',comment='review')
            setattr(payload,field,'   ')
            repo=SimpleNamespace(get=lambda _:asset,save=Mock())
            with patch.object(metadata_service,'repository',return_value=repo),self.assertRaises(HTTPException):
                metadata_service.transition('asset',payload,'verified')
            repo.save.assert_not_called()

    def test_valid_complete_states_and_dates(self):
        for state in ('draft','in_review','approved','deprecated','retired'):
            validate_asset_state({**self.asset(),'lifecycle_status':state,'deprecation_reason':'replaced'})
        validate_asset_state({**self.asset(),'effective_from':'2026-01-01T00:00:00Z','effective_to':'2026-01-01T02:00:00+02:00'})
        for value in ({**self.asset(),'lifecycle_status':'invalid'},{**self.asset(),'effective_to':'invalid'}):
            with self.assertRaises(ValueError): validate_asset_state(value)


class BridgeConstraintDialectTests(unittest.TestCase):
    def test_supported_uniqueness_dialects_and_wrong_definitions(self):
        node=next(n for n in ast.parse(Path('backend/graph_service/bridge_publication.py').read_text(encoding='utf-8')).body if getattr(n,'name','')=='publish')
        node.decorator_list=[]
        graph=Mock()
        graph.execute_write.return_value={'published':True}
        @contextmanager
        def session():yield graph
        scope={'digest':lambda _:'digest','session':session,'_bounded_query':lambda query:query,'_publish_transaction':Mock()}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<publish>','exec'),scope)
        command={'request_digest':'digest','rows':[{'candidate_id':'a','import_id':'i','import_row_key':'r','ontology_class_element_id':'t','target_ontology_type':'Class'}]}
        neo=ModuleType('neo4j');neo.unit_of_work=lambda **kwargs:lambda fn:fn
        for kind,entity,accepted in [('UNIQUENESS','NODE',True),('NODE_PROPERTY_UNIQUENESS','NODE',True),('RELATIONSHIP_PROPERTY_UNIQUENESS','RELATIONSHIP',False),('NODE_KEY','NODE',False)]:
            def run(query, **kwargs):
                kinds=ast.literal_eval(re.search(r'type IN (\[[^\]]+\])',query).group(1))
                self.assertIn("entityType = 'NODE'",query)
                self.assertIn("labelsOrTypes = ['DepoBridgePublication']",query)
                self.assertIn("properties = ['publication_id']",query)
                return SimpleNamespace(single=lambda:{'found':int(kind in kinds and entity=='NODE')})
            graph.run.side_effect=run;graph.execute_write.reset_mock()
            with self.subTest(kind=kind),patch.dict(sys.modules,{'neo4j':neo}):
                if accepted:self.assertEqual(scope['publish'](command),{'published':True})
                else:
                    with self.assertRaisesRegex(RuntimeError,'constraint is missing'):scope['publish'](command)
                    graph.execute_write.assert_not_called()


if __name__=='__main__':unittest.main()
