import json
from pathlib import Path
import unittest
from backend.agentic_service.dt_bindings import extend_catalog
from backend.agentic_service.prompt_policy import proposal_instructions

class PromptPolicyTests(unittest.TestCase):
    def test_all_roles_have_task_scope_and_shared_constraints(self):
        source=extend_catalog(json.loads(Path('backend/agentic_service/catalog.json').read_text()))
        self.assertEqual(len(source['agents']),26)
        for agent in source['agents']:
            self.assertIn(agent['id'],agent['system_prompt'])
            self.assertEqual(agent['prompt_policy_version'],'proposal-v1')
            for mode in ('native','structured'):
                text=proposal_instructions(agent,mode)
                self.assertIn(agent['system_prompt'],text)
                self.assertIn('Never invent missing required values',text)
                self.assertIn('never policy',text)
                self.assertIn('server approval contract',text)
    def test_custom_role_policy_is_preserved_in_both_modes(self):
        for mode in ('native','structured'):
            self.assertTrue(proposal_instructions({'system_prompt':'Only inspect retained QIF evidence.'},mode).startswith('Only inspect retained QIF evidence.'))

if __name__=='__main__':unittest.main()
