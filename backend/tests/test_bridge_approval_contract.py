import ast
from pathlib import Path
import unittest
from pydantic import BaseModel, ConfigDict, Field
from backend.agentic_service.input_contracts import validate_operation

class BridgeApprovalContractTests(unittest.TestCase):
    def setUp(self):
        source=Path(__file__).resolve().parents[1]/'agentic_service/bridge_router.py'
        nodes=[n for n in ast.parse(source.read_text(encoding='utf-8')).body
               if isinstance(n,ast.ClassDef) and n.name in {'PreviewInput','ApprovalInput'}]
        scope=dict(BaseModel=BaseModel,ConfigDict=ConfigDict,Field=Field)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'),scope)
        self.models=scope
    def document(self, model):
        return {'paths':{'/api/v1/test':{'post':{'requestBody':{'required':True,'content':{
            'application/json':{'schema':{'$ref':'#/components/schemas/Body'}}}}}}},
            'components':{'schemas':{'Body':model.model_json_schema()}}}
    def test_actual_strict_bridge_preview_accepts_valid_input_without_injected_envelope(self):
        inputs={'ontology_id':'teamcenter','import_task_id':'retained-import','manual_mappings':[],'candidate_offset':0}
        before=dict(inputs)
        doc=self.document(self.models['PreviewInput'])
        tool={'id':'bridge.mapping.preview','path':'/test','method':'POST','mutates':True}
        validate_operation(doc,tool,inputs)
        self.assertEqual(inputs,before)
        for extra in ({'approved_by':'spoof'},{'approval_token':'secret'},{'unknown':1},{'candidate_offset':-1}):
            with self.subTest(extra=extra),self.assertRaises(ValueError):
                validate_operation(doc,tool,{**inputs,**extra})
    def test_publication_retains_declared_approval_body_and_required_candidate_validation(self):
        doc=self.document(self.models['ApprovalInput'])
        tool={'id':'bridge.mapping.publish','path':'/test','method':'POST','mutates':True}
        validate_operation(doc,tool,{'approved_candidate_ids':['candidate-1']})
        with self.assertRaises(ValueError):validate_operation(doc,tool,{'approved_candidate_ids':[]})
        with self.assertRaises(ValueError):validate_operation(doc,tool,{})
    def test_required_downstream_approval_is_still_modeled(self):
        doc=self.document(self.models['ApprovalInput'])
        schema=doc['components']['schemas']['Body']
        schema['required'] += ['approved_by','approval_token']
        tool={'id':'write','path':'/test','method':'POST','mutates':True}
        validate_operation(doc,tool,{'approved_candidate_ids':['candidate-1']})
        with self.assertRaises(ValueError):
            validate_operation(doc,{**tool,'mutates':False},{'approved_candidate_ids':['candidate-1']})

if __name__=='__main__':unittest.main()
