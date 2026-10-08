import unittest
from backend.ontology_service.inference_options import validate_options
class InferenceOptionsTests(unittest.TestCase):
 def test_defaults_and_boolean_flags(self):
  self.assertEqual(validate_options(None),({},250))
  self.assertEqual(validate_options({'rules':{'equivalence':False},'limit':25}),({'equivalence':False},25))
 def test_invalid_flags_and_limits_fail(self):
  for value in ({'rules':{'equivalence':'false'}},{'rules':{'unknown':True}},{'limit':True},{'limit':'250'},{'limit':0}):
   with self.assertRaises(ValueError):validate_options(value)
if __name__=='__main__':unittest.main()
